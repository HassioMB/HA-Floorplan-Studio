# HA Floorplan Studio

**Version 1.0.0**

HA Floorplan Studio is a visual editor for creating interactive Home Assistant floorplans.

It allows you to design your floorplan visually, connect Home Assistant entities, create lighting effects and deploy the finished floorplan directly to Home Assistant.

## Features

- Visual drag-and-drop editor
- Live Home Assistant entity connection
- Interactive entity controls
- Room lighting effects
- Spotlights and uplights
- LED strips and light spill
- Generic 0–100% level indicators
- Background image support
- Live preview
- Save and load projects
- SVG, YAML and CSS export
- Automatic SSH key setup
- Automatic Home Assistant deployment detection
- SFTP / SSH shell deployment
- macOS support
- Windows support

## Requirements

- Python 3
- A modern web browser
- Home Assistant accessible on your local network

For live Home Assistant entities you need a Long-Lived Access Token.

SSH is only required for automatic deployment.

## macOS

1. Download and extract the release.
2. Open the HA Floorplan Studio folder.
3. Double-click:

   `Start on macOS.command`

4. The first launch creates a local Python environment automatically.
5. Your browser will open at:

   `http://127.0.0.1:8088`

Keep the Terminal window open while using HA Floorplan Studio.

If macOS blocks the launcher, right-click it and choose **Open**.

## Windows

1. Download and extract the release.
2. Open the HA Floorplan Studio folder.
3. Double-click:

   `Start on Windows.bat`

4. The first launch creates a local Python environment automatically.
5. Your browser will open at:

   `http://127.0.0.1:8088`

If Python is not installed, install Python 3 and enable **Add Python to PATH** during installation.

## Connecting to Home Assistant

Enter your:

- Home Assistant URL
- Long-Lived Access Token

Example:

`http://192.168.1.100:8123`

Then click **Connect / Refresh**.

Your token stays local and should never be published or shared.

## Automatic SSH Setup

HA Floorplan Studio can create a dedicated SSH key automatically.

Use:

**Set Up SSH Automatically**

The private key remains on your computer.

Only the generated public key should be added to your Home Assistant SSH add-on.

The editor can automatically detect:

- SSH connectivity
- SFTP availability
- SSH shell transfer
- common Home Assistant configuration paths
- writable deployment directories
- existing passwordless sudo access

The editor will automatically choose the available deployment method whenever possible.

## Exported Files

HA Floorplan Studio can generate:

- `floorplan.svg`
- `floorplan.css`
- `floorplan.yaml`
- `card.yaml`
- `floorplan-project.json`

## Security

Never publish:

- Home Assistant access tokens
- SSH private keys
- passwords
- private credentials

Only public SSH keys are safe to share with the Home Assistant system they are intended for.

## Contact

Questions, feedback, bug reports or suggestions:

📧 **hassio@tutamail.com**

## ❤️ Support the project

HA Floorplan Studio is free to use.

If you find the project useful and would like to support continued development:

💳 **Revolut:** https://revolut.me/markoob03

Every contribution helps with development, testing and future features.

Thank you for supporting HA Floorplan Studio.

## Disclaimer

HA Floorplan Studio is an independent community project.

It is not affiliated with, sponsored by or endorsed by Home Assistant or Nabu Casa.

Always keep backups of important Home Assistant configuration files before making changes.
