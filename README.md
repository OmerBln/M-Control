# M-Control

Native Linux configuration utility, driver, and management software for the **Fevell Z1 (Furylevel Z1)** gaming mouse.

Built specifically for Linux (CachyOS, Arch, Fedora, Debian/Ubuntu) with direct hardware communication over USB HID — **no Wine or Windows emulation required**.

## Features

- **Direct Hardware Detection**: Automatically detects Fevell Z1 in both Wired USB (`04f3:026e`) and 2.4GHz Wireless Receiver (`32c2:0018`) modes.
- **Battery & Link Status**: Live battery percentage, voltage, and charging indicator.
- **DPI Control**: Independent DPI stages (50 to 26,000 DPI) with custom LED color assignments.
- **Polling Rate**: Configurable polling rates (125 Hz, 250 Hz, 500 Hz, 1000 Hz).
- **Sensor Parameters**: Debounce time adjustment, Lift-Off Distance (LOD: 1mm / 2mm), Motion Sync, and Angle Snapping.
- **Button Mapping & Profiles**: Onboard memory profile saving and persistence.
- **Native GUI & Tray**: Modern Qt6 (PyQt6) dark-themed interface with KDE Plasma / Wayland system tray integration.
- **CLI Support**: Full-featured command-line interface for scripts, headless setups, and game-specific profiles.

## Hardware Support

- **Device**: Fevell Z1 / Furylevel Z1 Wireless Gaming Mouse
- **Sensor**: PixArt PAW3395
- **MCU**: Beken BK3633 / Compx reference design
- **Wired VID:PID**: `04F3:026E` (Elan Microelectronics Corp.)
- **2.4GHz Dongle VID:PID**: `32C2:0018` (HS6209 Receiver)

## Installation & Setup

### 1. udev Rules (Non-Root Hardware Access)

Copy the provided udev rules to allow non-root users to communicate with the mouse:

```bash
sudo cp 70-m-control.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### 2. Environment & Installation

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e .
```

## Usage

### CLI

```bash
mcontrol status
mcontrol battery
mcontrol set-dpi 1600
mcontrol set-rate 1000
```

### GUI

```bash
mcontrol-gui
```

## License

MIT License

## Disclaimer

M-Control is an independent, community-driven open-source project and is not affiliated, associated, authorized, endorsed by, or in any way officially connected with Furylevel, Fevell, Elan Microelectronics, or any of their subsidiaries.

All product names, logos, brands, trademarks, and registered trademarks are property of their respective owners. Their use in this software and documentation is strictly for identification and hardware compatibility reference purposes only under nominative fair use.
