#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from pathlib import Path
import json, os, shutil, sys, tempfile
import posixpath
import shlex

try:
    import paramiko
except ImportError:
    paramiko = None

ROOT = Path(__file__).resolve().parent
EXPORTS = ROOT / 'exports'
EXPORTS.mkdir(exist_ok=True)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self):
        if self.path == '/api/ha/states':
            return self.ha_states()
        if self.path == '/api/ha/service':
            return self.ha_service()
        if self.path == '/api/export':
            return self.export_files()
        if self.path == '/api/ssh/setup':
            return self.ssh_setup()
        if self.path == '/api/ssh/test':
            return self.ssh_test()
        self.send_error(404)


    def managed_ssh_key_path(self):
        return Path.home() / '.ssh' / 'ha_floorplan_studio'

    def read_managed_public_key(self):
        private_path = self.managed_ssh_key_path()
        public_path = Path(str(private_path) + '.pub')

        if public_path.exists():
            return public_path.read_text(
                encoding='utf-8'
            ).strip()

        return ''

    def ssh_setup(self):
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

            key_dir = Path.home() / '.ssh'
            key_dir.mkdir(
                parents=True,
                exist_ok=True
            )

            try:
                os.chmod(key_dir, 0o700)
            except Exception:
                pass

            private_path = self.managed_ssh_key_path()
            public_path = Path(
                str(private_path) + '.pub'
            )

            created = False

            if not private_path.exists():

                private_key = Ed25519PrivateKey.generate()

                private_bytes = private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.OpenSSH,
                    encryption_algorithm=serialization.NoEncryption()
                )

                public_bytes = private_key.public_key().public_bytes(
                    encoding=serialization.Encoding.OpenSSH,
                    format=serialization.PublicFormat.OpenSSH
                )

                private_path.write_bytes(
                    private_bytes
                )

                public_text = (
                    public_bytes.decode('utf-8')
                    + ' ha-floorplan-studio'
                )

                public_path.write_text(
                    public_text + '\n',
                    encoding='utf-8'
                )

                try:
                    os.chmod(
                        private_path,
                        0o600
                    )

                    os.chmod(
                        public_path,
                        0o644
                    )
                except Exception:
                    pass

                created = True

            public_key = self.read_managed_public_key()

            if not public_key:
                raise RuntimeError(
                    'The SSH key exists, but its public key could not be read.'
                )

            self._json(
                200,
                {
                    'ok': True,
                    'created': created,
                    'private_key_path': str(private_path),
                    'public_key': public_key,
                    'message':
                        'SSH key created successfully.'
                        if created
                        else
                        'Existing HA Floorplan Studio SSH key found.'
                }
            )

        except Exception as e:
            self._json(
                500,
                {
                    'ok': False,
                    'error': str(e)
                }
            )

    def ssh_exec(self, client, command, timeout=15, data=None):
        stdin, stdout, stderr = client.exec_command(
            command,
            timeout=timeout
        )

        if data is not None:
            if isinstance(data, str):
                data = data.encode('utf-8')

            stdin.write(data)
            stdin.flush()
            stdin.channel.shutdown_write()

        out = stdout.read().decode(
            'utf-8',
            'replace'
        )

        err = stderr.read().decode(
            'utf-8',
            'replace'
        )

        status = stdout.channel.recv_exit_status()

        return status, out, err


    def detect_ssh_deployment(self, client, requested_path=''):
        """
        Detects:
        - writable Home Assistant web directory
        - SFTP availability
        - normal SSH shell write access
        - passwordless sudo fallback

        This does NOT change sudo configuration.
        """

        requested_path = str(
            requested_path or ''
        ).strip()

        candidates = []

        # Custom path entered by advanced users gets priority.
        if requested_path:
            candidates.append(requested_path)

        # Common Home Assistant layouts.
        candidates += [
            '/config/www/floorplan',
            '/homeassistant/www/floorplan',
        ]

        # Remove duplicates while preserving order.
        unique = []

        for path in candidates:
            if path not in unique:
                unique.append(path)

        selected = None
        needs_sudo = False
        errors = []

        # ----------------------------------------------------
        # FIND A WRITABLE TARGET
        # ----------------------------------------------------

        for target in unique:

            if not target.startswith('/'):
                continue

            probe = posixpath.join(
                target,
                '.ha-floorplan-write-test'
            )

            qt = shlex.quote(target)
            qp = shlex.quote(probe)

            # First try as the logged-in SSH user.
            command = (
                f"mkdir -p {qt} && "
                f"touch {qp} && "
                f"rm -f {qp}"
            )

            status, out, err = self.ssh_exec(
                client,
                command
            )

            if status == 0:
                selected = target
                needs_sudo = False
                break

            errors.append(
                f'{target}: {(err or out).strip()[:180]}'
            )

            # Then try existing passwordless sudo.
            command = (
                f"sudo -n mkdir -p {qt} && "
                f"sudo -n touch {qp} && "
                f"sudo -n rm -f {qp}"
            )

            status, out, err = self.ssh_exec(
                client,
                command
            )

            if status == 0:
                selected = target
                needs_sudo = True
                break

        if not selected:
            return {
                'ok': False,
                'stage': 'permissions',
                'message':
                    'SSH login works, but no writable Home Assistant web directory was found.',
                'detail':
                    ' | '.join(errors)[-800:],
                'candidates': unique
            }

        # ----------------------------------------------------
        # CHECK SFTP
        # ----------------------------------------------------

        sftp_ok = False

        if not needs_sudo:
            try:
                sftp = client.open_sftp()

                probe = posixpath.join(
                    selected,
                    '.ha-floorplan-sftp-test'
                )

                with sftp.file(probe, 'w') as f:
                    f.write('ok')

                sftp.remove(probe)
                sftp.close()

                sftp_ok = True

            except Exception:
                sftp_ok = False

        if sftp_ok:
            method = 'sftp'
        elif needs_sudo:
            method = 'shell_sudo'
        else:
            method = 'shell'

        return {
            'ok': True,
            'stage': 'ready',
            'method': method,
            'path': selected,
            'sudo': needs_sudo,
            'sftp': sftp_ok
        }


    def ssh_test(self):
        import socket

        try:
            if paramiko is None:
                raise RuntimeError(
                    'Paramiko is not installed.'
                )

            b = self.body()

            host = str(
                b.get('host', '')
            ).strip()

            port = int(
                b.get('port') or 22
            )

            user = str(
                b.get('user', '')
            ).strip()

            key = str(
                b.get('key', '')
            ).strip()

            requested_path = str(
                b.get('path', '')
            ).strip()

            if not key:
                key = str(
                    self.managed_ssh_key_path()
                )

            key = os.path.expanduser(key)

            if not host:
                raise ValueError(
                    'Enter the Home Assistant host or IP address.'
                )

            if not user:
                raise ValueError(
                    'Enter the SSH username.'
                )

            if not Path(key).exists():
                self._json(200, {
                    'ok': False,
                    'stage': 'key',
                    'message':
                        'No SSH key was found. Create one first.'
                })
                return

            # Test TCP connectivity first.
            try:
                sock = socket.create_connection(
                    (host, port),
                    timeout=5
                )
                sock.close()

            except Exception:
                self._json(200, {
                    'ok': False,
                    'stage': 'network',
                    'message':
                        f'Cannot reach SSH on {host}:{port}.'
                })
                return

            client = paramiko.SSHClient()

            client.set_missing_host_key_policy(
                paramiko.AutoAddPolicy()
            )

            try:
                client.connect(
                    hostname=host,
                    port=port,
                    username=user,
                    key_filename=key,
                    timeout=8,
                    banner_timeout=8,
                    auth_timeout=8,
                    look_for_keys=False,
                    allow_agent=False
                )

            except paramiko.AuthenticationException:
                self._json(200, {
                    'ok': False,
                    'stage': 'authentication',
                    'message':
                        'SSH is reachable, but this key is not authorized.',
                    'public_key':
                        self.read_managed_public_key()
                })
                return

            except Exception as e:
                self._json(200, {
                    'ok': False,
                    'stage': 'ssh',
                    'message':
                        'SSH connection failed.',
                    'detail': str(e)
                })
                return

            result = self.detect_ssh_deployment(
                client,
                requested_path
            )

            client.close()

            if not result.get('ok'):
                self._json(
                    200,
                    result
                )
                return

            method = result['method']

            if method == 'sftp':
                message = (
                    'Direct deployment is ready using SFTP.'
                )

            elif method == 'shell_sudo':
                message = (
                    'Direct deployment is ready using SSH shell with passwordless sudo.'
                )

            else:
                message = (
                    'Direct deployment is ready using SSH shell transfer.'
                )

            self._json(200, {
                **result,
                'message': message,
                'private_key_path': key
            })

        except Exception as e:
            self._json(500, {
                'ok': False,
                'error': str(e)
            })

    def body(self):
        length = int(self.headers.get('Content-Length', '0'))
        return json.loads(self.rfile.read(length) or b'{}')

    def ha_request(self, base, token, path, data=None):
        base = str(base or '').strip().rstrip('/')
        token = str(token or '').strip()
        if not base.startswith(('http://','https://')) or not token:
            raise ValueError('Enter a valid Home Assistant URL and access token')
        payload = None if data is None else json.dumps(data).encode('utf-8')
        req = Request(base + path, data=payload, headers={
            'Authorization': 'Bearer ' + token,
            'Content-Type': 'application/json',
            'User-Agent': 'HA-Floorplan-Studio/1.0.0'
        })
        with urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return json.loads(raw or b'[]')

    def ha_states(self):
        try:
            b = self.body()
            data = self.ha_request(b.get('url'), b.get('token'), '/api/states')
            self._json(200, data)
        except HTTPError as e:
            self._json(e.code, {'error': self.http_error(e)})
        except URLError as e:
            self._json(502, {'error': f'Unable to connect to Home Assistant: {e.reason}'})
        except Exception as e:
            self._json(500, {'error': str(e)})

    def ha_service(self):
        try:
            b = self.body()
            service = str(b.get('service','')).strip()
            if '.' not in service:
                raise ValueError('Service must use the format domain.service')
            domain, name = service.split('.',1)
            data = {}
            if b.get('entity_id'):
                data['entity_id'] = str(b['entity_id']).strip()
            result = self.ha_request(b.get('url'), b.get('token'), f'/api/services/{domain}/{name}', data)
            self._json(200, {'ok': True, 'result': result})
        except HTTPError as e:
            self._json(e.code, {'error': self.http_error(e)})
        except URLError as e:
            self._json(502, {'error': f'Unable to connect to Home Assistant: {e.reason}'})
        except Exception as e:
            self._json(500, {'error': str(e)})

    def export_files(self):
        try:
            b = self.body()

            files = b.get('files') or {}

            allowed = {
                'floorplan.svg',
                'floorplan.css',
                'floorplan.yaml',
                'card.yaml',
                'floorplan-project.json'
            }

            files = {
                k: str(v)
                for k, v in files.items()
                if k in allowed
            }

            if not files:
                raise ValueError(
                    'No files were provided for export.'
                )

            # Always keep a local copy.
            for name, content in files.items():
                (EXPORTS / name).write_text(
                    content,
                    encoding='utf-8'
                )

            mode = b.get('mode', 'ssh')
            test = bool(b.get('test'))

            # ==================================================
            # LOCAL EXPORT
            # ==================================================

            if mode == 'local':
                local = b.get('local') or {}

                target_text = str(
                    local.get('path', '')
                ).strip()

                if not target_text:
                    raise ValueError(
                        'Enter a local destination folder.'
                    )

                target = Path(
                    os.path.expanduser(target_text)
                )

                target.mkdir(
                    parents=True,
                    exist_ok=True
                )

                probe = target / '.floorplan-write-test'

                probe.write_text(
                    'ok',
                    encoding='utf-8'
                )

                probe.unlink(
                    missing_ok=True
                )

                if not test:
                    for name in files:
                        shutil.copy2(
                            EXPORTS / name,
                            target / name
                        )

                self._json(
                    200,
                    {
                        'ok': True,
                        'message':
                            'Local folder is writable'
                            if test
                            else f'Exported to {target}'
                    }
                )
                return

            if mode != 'ssh':
                raise ValueError(
                    'Unknown deployment mode.'
                )

            if paramiko is None:
                raise RuntimeError(
                    'Paramiko is not installed.'
                )

            # ==================================================
            # SSH SETTINGS
            # ==================================================

            ssh = b.get('ssh') or {}

            host = str(
                ssh.get('host', '')
            ).strip()

            user = str(
                ssh.get('user', '')
            ).strip()

            port = int(
                ssh.get('port') or 22
            )

            remote = str(
                ssh.get(
                    'path',
                    '/config/www/floorplan'
                )
            ).strip()

            key = os.path.expanduser(
                str(
                    ssh.get('key', '')
                ).strip()
            )

            password = str(
                ssh.get('password', '')
            )

            if not host:
                raise ValueError(
                    'Enter the Home Assistant SSH host.'
                )

            if not user:
                raise ValueError(
                    'Enter the SSH username.'
                )

            if not remote.startswith('/'):
                raise ValueError(
                    'The remote directory must be an absolute path.'
                )

            if not key:
                key = str(
                    self.managed_ssh_key_path()
                )

            if not Path(key).exists():
                raise ValueError(
                    f'SSH private key does not exist: {key}'
                )

            client = paramiko.SSHClient()

            client.set_missing_host_key_policy(
                paramiko.AutoAddPolicy()
            )

            connect_args = {
                'hostname': host,
                'port': port,
                'username': user,
                'timeout': 10,
                'banner_timeout': 10,
                'auth_timeout': 10,
                'key_filename': key,
                'look_for_keys': False,
                'allow_agent': False
            }

            if password:
                connect_args['password'] = password

            client.connect(
                **connect_args
            )

            detected = self.detect_ssh_deployment(
                client,
                remote
            )

            if not detected.get('ok'):
                raise RuntimeError(
                    detected.get(
                        'message',
                        'No writable Home Assistant target directory found.'
                    )
                    + (
                        ': ' + detected.get('detail','')
                        if detected.get('detail')
                        else ''
                    )
                )

            remote = detected['path']
            transfer_method = detected['method']

            # ==================================================
            # SFTP
            # ==================================================

            if transfer_method == 'sftp':
                sftp = client.open_sftp()

                def ensure_remote_dir(path):
                    path = posixpath.normpath(path)

                    current = ''

                    for part in path.strip('/').split('/'):
                        if not part:
                            continue

                        current += '/' + part

                        try:
                            sftp.stat(current)
                        except IOError:
                            sftp.mkdir(current)

                ensure_remote_dir(remote)

                probe = posixpath.join(
                    remote,
                    '.floorplan-write-test'
                )

                with sftp.file(probe, 'w') as f:
                    f.write('ok')

                sftp.remove(probe)

                if test:
                    sftp.close()
                    client.close()

                    self._json(
                        200,
                        {
                            'ok': True,
                            'method': 'sftp',
                            'message':
                                'SSH/SFTP connection successful'
                        }
                    )
                    return

                backup_dir = posixpath.join(
                    remote,
                    '.backup'
                )

                ensure_remote_dir(
                    backup_dir
                )

                for name in files:
                    local_file = EXPORTS / name

                    remote_file = posixpath.join(
                        remote,
                        name
                    )

                    backup_file = posixpath.join(
                        backup_dir,
                        name + '.previous'
                    )

                    try:
                        sftp.stat(remote_file)

                        try:
                            sftp.remove(
                                backup_file
                            )
                        except IOError:
                            pass

                        sftp.rename(
                            remote_file,
                            backup_file
                        )

                    except IOError:
                        pass

                    temp_remote = (
                        remote_file +
                        '.uploading'
                    )

                    try:
                        sftp.remove(
                            temp_remote
                        )
                    except IOError:
                        pass

                    sftp.put(
                        str(local_file),
                        temp_remote
                    )

                    sftp.rename(
                        temp_remote,
                        remote_file
                    )

                sftp.close()
                client.close()

                self._json(
                    200,
                    {
                        'ok': True,
                        'method': 'sftp',
                        'message':
                            f'Deployed to {user}@{host}:{remote}'
                    }
                )
                return

            # ==================================================
            # SSH SHELL FALLBACK
            # ==================================================

            use_sudo = (
                transfer_method == 'shell_sudo'
            )

            def exec_checked(command):
                if use_sudo:
                    command = 'sudo -n sh -c ' + shlex.quote(command)
                stdin, stdout, stderr = client.exec_command(
                    command,
                    timeout=15
                )

                out = stdout.read().decode(
                    'utf-8',
                    'replace'
                )

                err = stderr.read().decode(
                    'utf-8',
                    'replace'
                )

                status = stdout.channel.recv_exit_status()

                if status != 0:
                    raise RuntimeError(
                        err.strip()
                        or out.strip()
                        or f'Remote command failed with status {status}'
                    )

                return out

            qremote = shlex.quote(remote)

            backup_dir = posixpath.join(
                remote,
                '.backup'
            )

            qbackup = shlex.quote(
                backup_dir
            )

            exec_checked(
                f"mkdir -p {qremote} {qbackup}"
            )

            probe = posixpath.join(
                remote,
                '.floorplan-write-test'
            )

            qprobe = shlex.quote(
                probe
            )

            exec_checked(
                f"touch {qprobe} && rm -f {qprobe}"
            )

            if test:
                client.close()

                self._json(
                    200,
                    {
                        'ok': True,
                        'method': 'shell',
                        'message':
                            'SSH connection successful (shell transfer mode)'
                    }
                )
                return

            for name in files:
                local_file = EXPORTS / name

                remote_file = posixpath.join(
                    remote,
                    name
                )

                temp_remote = (
                    remote_file +
                    '.uploading'
                )

                backup_file = posixpath.join(
                    backup_dir,
                    name + '.previous'
                )

                qremote_file = shlex.quote(
                    remote_file
                )

                qtemp = shlex.quote(
                    temp_remote
                )

                qbackup_file = shlex.quote(
                    backup_file
                )

                # Keep previous version as backup.
                exec_checked(
                    f"if [ -f {qremote_file} ]; then "
                    f"cp {qremote_file} {qbackup_file}; "
                    f"fi; "
                    f"rm -f {qtemp}"
                )

                # Send file contents directly through SSH stdin.
                channel = (
                    client.get_transport()
                    .open_session()
                )

                if use_sudo:
                    channel.exec_command(
                        f"sudo -n tee {qtemp} >/dev/null"
                    )
                else:
                    channel.exec_command(
                        f"cat > {qtemp}"
                    )

                data = local_file.read_bytes()

                channel.sendall(
                    data
                )

                channel.shutdown_write()

                status = (
                    channel.recv_exit_status()
                )

                if status != 0:
                    raise RuntimeError(
                        f'Failed to upload {name} over SSH.'
                    )

                exec_checked(
                    f"mv {qtemp} {qremote_file}"
                )

            client.close()

            self._json(
                200,
                {
                    'ok': True,
                    'method': 'shell',
                    'message':
                        f'Deployed to {user}@{host}:{remote} using SSH shell transfer'
                }
            )

        except Exception as e:
            self._json(
                500,
                {
                    'error': str(e)
                }
            )

    def http_error(self, e):
        try: msg=e.read().decode('utf-8','replace')
        except Exception: msg=str(e)
        return f'Home Assistant HTTP {e.code}: {msg[:300]}'

    def _json(self, code, obj):
        data=json.dumps(obj,ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        sys.stderr.write('%s - %s\n' % (self.address_string(), fmt%args))

if __name__ == '__main__':
    port = int(os.environ.get('PORT','8088'))
    print(f'HA Floorplan Studio v1.0.0: http://0.0.0.0:{port}/')
    print('Open the address above in your browser.')
    print('Press Ctrl+C to stop.')
    ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()
