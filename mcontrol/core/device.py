"""Core hardware driver and HID communication controller for Fevell Z1."""

import fcntl
import glob
import json
import os
import select
import time
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Tuple, Type

from mcontrol.core.base import BaseMouseDriver, DeviceCapabilities
from mcontrol.core.constants import (
    BUTTON_ACTIONS,
    Command,
    COMPX_DONGLE_PID,
    COMPX_VENDOR_ID,
    COMPX_WIRED_PID,
    DEBOUNCE_MAX_MS,
    DEBOUNCE_MIN_MS,
    DEFAULT_BUTTON_KEYS,
    DEFAULT_DEBOUNCE_MS,
    DEFAULT_DPI_STAGE_COLORS,
    DEFAULT_DPI_STAGES,
    DPI_MAX,
    DPI_MIN,
    DPI_STEP,
    FEVELL_DONGLE_4K_PID,
    FEVELL_DONGLE_PID,
    FEVELL_SUPPORTED_PIDS,
    FEVELL_VENDOR_ID,
    FEVELL_WIRED_PID,
    FlashAddr,
    LOD_1MM,
    LOD_2MM,
    MAX_DPI_STAGES,
    MAX_PAYLOAD_LEN,
    PACKET_LEN_CMD,
    PACKET_LEN_FEATURE_CMD,
    PACKET_LEN_STATE_READ,
    PACKET_LEN_WAKE,
    POLLING_RATE_MAP,
    POLLING_RATE_REVERSE_MAP,
    REPORT_ID_CMD,
    REPORT_ID_FEATURE_CMD,
    REPORT_ID_STATE_READ,
    REPORT_ID_STATUS,
    REPORT_ID_WAKE,
    VALID_LOD_VALUES,
    VENDOR_INTERFACE_NUMBER,
    VENDOR_USAGE_PAGE,
)
from mcontrol.core.protocol import (
    BatteryStatus,
    MouseSettings,
    build_command_packet,
    build_feature_dpi_colors_packet,
    build_feature_dpi_packet,
    build_feature_factory_reset_packet,
    build_feature_key_mapping_packet,
    build_feature_lighting_packet,
    build_feature_lod_packet,
    build_feature_polling_packet,
    build_feature_power_sleep_packet,
    build_feature_sensor_advanced_packet,
    decode_dpi_color,
    decode_dpi_stage,
    decode_register_2byte,
    encode_dpi_color,
    encode_dpi_stage,
    encode_register_2byte,
    parse_battery_response,
    parse_input_status_report,
    parse_state_report_bd,
    verify_checksum,
)


class HIDTransport(Protocol):
    """Protocol interface for real hidapi, LinuxHidrawDevice, or MockHIDDevice."""
    def open(self, vid: int, pid: int) -> None: ...
    def close(self) -> None: ...
    def write(self, data: bytes) -> int: ...
    def read(self, max_length: int, timeout_ms: int = 1000) -> List[int]: ...


class DeviceError(Exception):
    """Raised when mouse communication or discovery fails."""


class DeviceNotFoundError(DeviceError):
    """Raised when no supported mouse device is found."""


class DevicePermissionError(DeviceError):
    """Raised when Linux udev permissions block access to /dev/hidraw*."""


class DeviceCommunicationError(DeviceError):
    """Raised when a packet write/read fails or returns an invalid checksum."""


def _hidiocsfeature(length: int) -> int:
    """
    Compute Linux ioctl request code for HIDIOCSFEATURE(len).
    # Protocol: Linux kernel <linux/hidraw.h> _IOC(_IOC_WRITE|_IOC_READ, 'H', 0x06, len) (2026-10-29)
    """
    return (3 << 30) | (length << 16) | (ord("H") << 8) | 0x06


def _hidiocgfeature(length: int) -> int:
    """
    Compute Linux ioctl request code for HIDIOCGFEATURE(len).
    # Protocol: Linux kernel <linux/hidraw.h> _IOC(_IOC_WRITE|_IOC_READ, 'H', 0x07, len) (2026-10-29)
    """
    return (3 << 30) | (length << 16) | (ord("H") << 8) | 0x07


class LinuxHidrawDevice:
    """
    Direct Linux /dev/hidrawN transport supporting both Feature Reports (ioctl)
    and non-blocking Input Report 0x04 reads.
    
    # Protocol: Linux hidraw ioctl & GamingMS.exe HID transport (2026-10-29)
    """

    def __init__(self, path: str):
        self.path = path
        self.fd: Optional[int] = None

    def open_path(self) -> None:
        if self.fd is None:
            self.fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)

    def open(self, vid: int, pid: int) -> None:
        self.open_path()

    def close(self) -> None:
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

    def send_feature_report(self, data: bytes) -> int:
        """
        Send a HID Feature Report via HIDIOCSFEATURE ioctl.
        # Protocol: GamingMS.exe HidD_SetFeature equivalent on Linux (2026-10-29)
        """
        if self.fd is None:
            raise OSError("Hidraw device is not open")
        buf = bytearray(data)
        fcntl.ioctl(self.fd, _hidiocsfeature(len(buf)), buf, True)
        return len(buf)

    def get_feature_report(self, report_id: int, length: int) -> bytes:
        """
        Read a HID Feature Report via HIDIOCGFEATURE ioctl.
        # Protocol: GamingMS.exe HidD_GetFeature equivalent on Linux (2026-10-29)
        """
        if self.fd is None:
            raise OSError("Hidraw device is not open")
        buf = bytearray(length)
        buf[0] = report_id & 0xFF
        fcntl.ioctl(self.fd, _hidiocgfeature(length), buf, True)
        return bytes(buf)

    def write(self, data: bytes) -> int:
        """
        Write output or feature report to /dev/hidrawN.
        # Protocol: Linux hidraw transport (2026-10-29)
        """
        if self.fd is None:
            raise OSError("Hidraw device is not open")
        if data and data[0] in (REPORT_ID_FEATURE_CMD, REPORT_ID_WAKE, REPORT_ID_STATUS, REPORT_ID_STATE_READ):
            return self.send_feature_report(data)
        try:
            return os.write(self.fd, data)
        except OSError:
            return self.send_feature_report(data)

    def read(self, max_length: int, timeout_ms: int = 1000) -> List[int]:
        """
        Read an input report (such as Input Report 0x04 on physical DPI button press).
        # Protocol: GamingMS.exe Input Report 0x04 reader @ 0x00432c30 (2026-10-29)
        """
        if self.fd is None:
            raise OSError("Hidraw device is not open")
        if timeout_ms <= 0:
            try:
                data = os.read(self.fd, max_length)
                return list(data)
            except BlockingIOError:
                return []
            except OSError:
                return []

        rlist, _, _ = select.select([self.fd], [], [], timeout_ms / 1000.0)
        if not rlist:
            return []
        try:
            data = os.read(self.fd, max_length)
            return list(data)
        except OSError:
            return []


def _probe_hidraw_online_status(path: str) -> Tuple[bool, int]:
    """
    Probe Feature Report 0x05 on a /dev/hidrawN node to check if the mouse link is active.
    
    # Protocol: Reverse-engineered from GamingMS.exe @ 0x00438150..0x00438314 (2026-10-29)
    Returns (is_online, receiver_max_khz) where:
      buf[0] == 0x05 and buf[1:5] == b"1010":
      buf[5] != 0 -> mouse is online on this interface
      buf[6] -> 1 (1000Hz), 4 (4000Hz), or 8 (8000Hz)
    """
    try:
        dev = LinuxHidrawDevice(path)
        dev.open_path()
        try:
            r5 = dev.get_feature_report(REPORT_ID_STATUS, PACKET_LEN_FEATURE_CMD)
            if len(r5) >= 7 and r5[0] == REPORT_ID_STATUS and r5[1:5] == b"1010":
                is_online = bool(r5[5])
                rate_khz = r5[6] if r5[6] in (1, 4, 8) else 1
                return is_online, rate_khz
        finally:
            dev.close()
    except OSError:
        pass
    return False, 1


def _scan_sysfs_hidraw_devices() -> List[dict]:
    """
    Scan /sys/class/hidraw/hidraw* to discover Fevell Z1 interfaces and check online status.
    
    # Protocol: Linux sysfs hidraw enumeration + GamingMS.exe Report 0x05 probe (2026-10-29)
    """
    results: List[dict] = []
    for sys_path in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        uevent_path = os.path.join(sys_path, "device", "uevent")
        if not os.path.exists(uevent_path):
            continue
        try:
            with open(uevent_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError:
            continue

        vid = 0
        pid = 0
        iface = -1
        for line in content.splitlines():
            if line.startswith("HID_ID="):
                parts = line.split("=")[1].split(":")
                if len(parts) == 3:
                    vid = int(parts[1], 16)
                    pid = int(parts[2], 16)
            elif line.startswith("HID_PHYS="):
                if "/input" in line:
                    try:
                        iface = int(line.rsplit("/input", 1)[1].strip())
                    except ValueError:
                        iface = -1

        if (vid, pid) in (
            (FEVELL_VENDOR_ID, FEVELL_WIRED_PID),
            (FEVELL_VENDOR_ID, FEVELL_DONGLE_PID),
            (FEVELL_VENDOR_ID, FEVELL_DONGLE_4K_PID),
            (COMPX_VENDOR_ID, COMPX_WIRED_PID),
            (COMPX_VENDOR_ID, COMPX_DONGLE_PID),
        ):
            dev_node = os.path.join("/dev", os.path.basename(sys_path))
            mode = FEVELL_SUPPORTED_PIDS.get(
                pid,
                "wired" if pid in (FEVELL_WIRED_PID, COMPX_WIRED_PID) else "dongle",
            )
            is_online = False
            rate_khz = 1
            if iface == VENDOR_INTERFACE_NUMBER:
                is_online, rate_khz = _probe_hidraw_online_status(dev_node)
            results.append(
                {
                    "vendor_id": vid,
                    "product_id": pid,
                    "interface_number": iface,
                    "usage_page": VENDOR_USAGE_PAGE if iface == VENDOR_INTERFACE_NUMBER else 0x0001,
                    "path": dev_node.encode("utf-8"),
                    "mode": mode,
                    "is_online": is_online,
                    "receiver_rate_khz": rate_khz,
                }
            )
    return results


def discover_fevell_devices() -> List[dict]:
    """
    Enumerate connected USB/HID devices and return matching Fevell Z1 interfaces.
    Prioritizes:
      1. Vendor configuration interfaces (Interface 1 / Usage Page 0xFF00) that report `is_online=True` in Report 0x05
      2. Wired USB interface (04F3:026E) over Wireless Dongle (04F3:026F / 04F3:026D)
    
    # Protocol: Reverse-engineered from GamingMS.exe @ 0x00432000..0x00432690 & 0x00438150 (2026-10-29)
    """
    sysfs_matches = _scan_sysfs_hidraw_devices()

    if not sysfs_matches:
        try:
            import hid
            all_devs = hid.enumerate()
        except Exception:
            all_devs = []

        target_pairs = [
            (FEVELL_VENDOR_ID, FEVELL_WIRED_PID, "wired"),
            (FEVELL_VENDOR_ID, FEVELL_DONGLE_PID, "dongle"),
            (FEVELL_VENDOR_ID, FEVELL_DONGLE_4K_PID, "dongle_4k"),
            (COMPX_VENDOR_ID, COMPX_WIRED_PID, "wired"),
            (COMPX_VENDOR_ID, COMPX_DONGLE_PID, "dongle"),
        ]
        for d in all_devs:
            vid = d.get("vendor_id")
            pid = d.get("product_id")
            for t_vid, t_pid, mode in target_pairs:
                if vid == t_vid and pid == t_pid:
                    info = dict(d)
                    info["mode"] = mode
                    raw_path = info.get("path", b"")
                    path_str = raw_path.decode("utf-8", errors="ignore") if isinstance(raw_path, bytes) else str(raw_path)
                    is_vendor = info.get("usage_page") == VENDOR_USAGE_PAGE or info.get("interface_number") == VENDOR_INTERFACE_NUMBER
                    is_online, rate_khz = _probe_hidraw_online_status(path_str) if (is_vendor and path_str.startswith("/dev/hidraw")) else (False, 1)
                    info["is_online"] = is_online
                    info["receiver_rate_khz"] = rate_khz
                    sysfs_matches.append(info)

    def _priority(dev_info: dict) -> Tuple[int, int, int]:
        is_vendor_iface = (
            dev_info.get("usage_page") == VENDOR_USAGE_PAGE
            or dev_info.get("interface_number") == VENDOR_INTERFACE_NUMBER
        )
        is_online = bool(dev_info.get("is_online", False))
        is_wired = dev_info.get("product_id") == FEVELL_WIRED_PID
        return (
            0 if is_vendor_iface else 1,
            0 if is_online else 1,
            0 if is_wired else 1,
        )

    sysfs_matches.sort(key=_priority)
    return sysfs_matches


class FevellDevice(BaseMouseDriver):
    """
    High-level controller for the Fevell Z1 (Furylevel Z1) gaming mouse.
    
    Supports:
    1. Native 32-byte Feature Report 0x06 protocol (reverse-engineered from GamingMS.exe)
    2. Live Input Report 0x04 polling (physical DPI button presses, live battery & charging updates)
    3. Multi-interface synchronization when both Wired USB (04F3:026E) and 2.4GHz Receiver (04F3:026F) are connected
    4. Legacy 16-byte Flash/Register protocol fallback (used by MockHIDDevice unit tests)
    """

    @property
    def capabilities(self) -> DeviceCapabilities:
        return DeviceCapabilities(
            name="Fevell Z1",
            min_dpi=DPI_MIN,
            max_dpi=DPI_MAX,
            dpi_step=DPI_STEP,
            max_dpi_stages=MAX_DPI_STAGES,
            supported_polling_rates=[125, 250, 500, 1000],
            supports_lod=True,
            supports_debounce=True,
            supports_battery_read=True,
            supports_profiles=True,
        )

    def __init__(
        self,
        hid_device: Optional[HIDTransport] = None,
        profile_path: Optional[Path] = None,
    ):
        self._dev: Optional[HIDTransport] = hid_device
        self._secondary_devs: List[LinuxHidrawDevice] = []
        self._mode: Optional[str] = None
        self._connected: bool = False
        self._seq: int = 1
        self._vid: int = FEVELL_VENDOR_ID
        self._pid: int = FEVELL_WIRED_PID
        self._hidraw_path: str = "/dev/hidraw?"
        self._firmware_str: str = "1010"
        self._receiver_rate_khz: int = 1
        self._live_battery_pct: Optional[int] = None
        self._live_is_charging: Optional[bool] = None
        self._profile_path: Path = profile_path or (
            Path.home() / ".config" / "mcontrol" / "fevell_z1_profile.json"
        )
        self._cached_settings: MouseSettings = MouseSettings(
            polling_rate=1000,
            debounce_ms=4,
            lod=1,
            active_stage=1,
            stage_count=5,
            stage_enable_mask=0x1F,
            dpi_stages=[400, 800, 1600, 3200, 6400, 12000],
            dpi_colors=list(DEFAULT_DPI_STAGE_COLORS[:MAX_DPI_STAGES]),
        )

    @property
    def is_connected(self) -> bool:
        return self._connected and self._dev is not None

    @property
    def mode(self) -> Optional[str]:
        return self._mode

    def _is_feature_protocol(self) -> bool:
        return hasattr(self._dev, "send_feature_report") and hasattr(self._dev, "get_feature_report")

    def _is_real_hardware(self) -> bool:
        return isinstance(self._dev, LinuxHidrawDevice)

    def _next_seq(self) -> int:
        seq = self._seq & 0xFF
        self._seq = (self._seq + 1) & 0xFF
        return seq

    def _load_persisted_profile(self) -> None:
        """
        Load saved MouseSettings from ~/.config/mcontrol/fevell_z1_profile.json
        (equivalent to GamingMS.exe's config/default0.psf persistence).
        
        # Protocol: GamingMS.exe profile state persistence @ 0x00442f60 (2026-10-29)
        """
        if not self._is_real_hardware() or not self._profile_path.exists():
            return
        try:
            data = json.loads(self._profile_path.read_text(encoding="utf-8"))
            stages = [int(x) for x in data.get("dpi_stages", DEFAULT_DPI_STAGES)][:MAX_DPI_STAGES]
            while len(stages) < MAX_DPI_STAGES:
                stages.append(DEFAULT_DPI_STAGES[len(stages)])
            raw_colors = data.get("dpi_colors", DEFAULT_DPI_STAGE_COLORS[:MAX_DPI_STAGES])
            colors = [
                (int(c[0]) & 0xFF, int(c[1]) & 0xFF, int(c[2]) & 0xFF)
                for c in raw_colors[:MAX_DPI_STAGES]
            ]
            while len(colors) < MAX_DPI_STAGES:
                colors.append(DEFAULT_DPI_STAGE_COLORS[len(colors)])

            stage_count = max(1, min(MAX_DPI_STAGES, int(data.get("stage_count", 4))))
            enable_mask = int(data.get("stage_enable_mask", (1 << stage_count) - 1)) & 0x3F
            if enable_mask == 0:
                enable_mask = (1 << stage_count) - 1

            self._cached_settings = MouseSettings(
                polling_rate=int(data.get("polling_rate", 1000)),
                debounce_ms=int(data.get("debounce_ms", DEFAULT_DEBOUNCE_MS)),
                lod=int(data.get("lod", LOD_1MM)),
                active_stage=max(0, min(MAX_DPI_STAGES - 1, int(data.get("active_stage", 1)))),
                stage_count=stage_count,
                stage_enable_mask=enable_mask,
                dpi_stages=stages,
                dpi_colors=colors,
                angle_snap=bool(data.get("angle_snap", False)),
                motion_sync=bool(data.get("motion_sync", True)),
                ripple_control=bool(data.get("ripple_control", False)),
                sleep_timeout_min=int(data.get("sleep_timeout_min", 1)),
                move_light_off=bool(data.get("move_light_off", True)),
                lighting_mode=int(data.get("lighting_mode", 1)),
                lighting_brightness=int(data.get("lighting_brightness", 3)),
                lighting_speed=int(data.get("lighting_speed", 2)),
                button_mappings=list(data.get("button_mappings", DEFAULT_BUTTON_KEYS))[:6],
            )
        except Exception:
            pass

    def _save_persisted_profile(self) -> None:
        """
        Save current MouseSettings to ~/.config/mcontrol/fevell_z1_profile.json.
        
        # Protocol: GamingMS.exe profile state persistence @ 0x00442d10 (2026-10-29)
        """
        if not self._is_real_hardware():
            return
        try:
            self._profile_path.parent.mkdir(parents=True, exist_ok=True)
            s = self._cached_settings
            payload = {
                "polling_rate": s.polling_rate,
                "debounce_ms": s.debounce_ms,
                "lod": s.lod,
                "active_stage": s.active_stage,
                "stage_count": s.stage_count,
                "stage_enable_mask": s.stage_enable_mask,
                "dpi_stages": list(s.dpi_stages[:MAX_DPI_STAGES]),
                "dpi_colors": [list(c) for c in s.dpi_colors[:MAX_DPI_STAGES]],
                "angle_snap": s.angle_snap,
                "motion_sync": s.motion_sync,
                "ripple_control": s.ripple_control,
                "sleep_timeout_min": s.sleep_timeout_min,
                "move_light_off": s.move_light_off,
                "lighting_mode": s.lighting_mode,
                "lighting_brightness": s.lighting_brightness,
                "lighting_speed": s.lighting_speed,
                "button_mappings": list(s.button_mappings[:6]),
            }
            self._profile_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def connect(self, hid_device: Optional[HIDTransport] = None, mode: str = "wired") -> bool:
        """
        Open connection to the Fevell Z1 mouse.
        If `hid_device` is provided (e.g., `MockHIDDevice`), uses it directly.
        Otherwise discovers physical USB/dongle interfaces via sysfs/hidraw.
        
        # Protocol: GamingMS.exe Device Discovery & Handshake @ 0x00432000..0x00432690 (2026-10-29)
        """
        if hid_device is not None:
            if hasattr(hid_device, "is_open") and not getattr(hid_device, "is_open"):
                hid_device.open(self._vid, self._pid)
            self._dev = hid_device
            self._mode = mode
            self._connected = True
            return True

        matches = discover_fevell_devices()
        if not matches:
            raise DeviceError(
                "Fevell Z1 fare bulunamadı. Lütfen USB kablosunun veya 2.4GHz alıcısının takılı olduğundan emin olun."
            )

        vendor_Candidates = [
            m for m in matches
            if m.get("interface_number") == VENDOR_INTERFACE_NUMBER
            or m.get("usage_page") == VENDOR_USAGE_PAGE
        ]
        if not vendor_Candidates:
            vendor_Candidates = matches

        target = vendor_Candidates[0]
        raw_path = target.get("path", b"")
        path_str = raw_path.decode("utf-8", errors="ignore") if isinstance(raw_path, bytes) else str(raw_path)

        try:
            if path_str.startswith("/dev/hidraw"):
                dev = LinuxHidrawDevice(path_str)
                dev.open_path()
                self._dev = dev
                self._hidraw_path = path_str
            else:
                import hid
                dev = hid.device()
                if "path" in target and target["path"]:
                    dev.open_path(target["path"])
                else:
                    dev.open(target["vendor_id"], target["product_id"])
                self._dev = dev
                self._hidraw_path = path_str or "hidapi"

            self._mode = target.get("mode", "wired")
            self._vid = target.get("vendor_id", FEVELL_VENDOR_ID)
            self._pid = target.get("product_id", FEVELL_WIRED_PID)
            self._receiver_rate_khz = int(target.get("receiver_rate_khz", 1))
            self._connected = True

            # Also open any secondary vendor interfaces (e.g. when both wired and wireless dongle are plugged in)
            self._secondary_devs = []
            for extra in vendor_Candidates[1:]:
                extra_raw = extra.get("path", b"")
                extra_path = extra_raw.decode("utf-8", errors="ignore") if isinstance(extra_raw, bytes) else str(extra_raw)
                if extra_path.startswith("/dev/hidraw") and extra_path != path_str:
                    try:
                        sec_dev = LinuxHidrawDevice(extra_path)
                        sec_dev.open_path()
                        self._secondary_devs.append((sec_dev, extra))
                    except OSError:
                        pass

            self._load_persisted_profile()

            if self._is_feature_protocol():
                try:
                    self._dev.send_feature_report(bytes([REPORT_ID_WAKE] + [0x00] * 7))
                except Exception:
                    pass
                try:
                    r5 = self._dev.get_feature_report(REPORT_ID_STATUS, PACKET_LEN_FEATURE_CMD)
                    if len(r5) >= 7 and r5[1:5] == b"1010":
                        self._firmware_str = "1010 (v1.0.1.0)"
                        if r5[6] in (1, 4, 8):
                            self._receiver_rate_khz = r5[6]
                except Exception:
                    pass
                # Drain any queued Input Report 0x04 notifications
                self.poll_input_report()

            return True
        except OSError as exc:
            self._connected = False
            raise DevicePermissionError(
                f"Fareye erişim izni reddedildi ({exc}). Lütfen udev kurallarını kontrol edin: "
                "sudo cp 70-m-control.rules /etc/udev/rules.d/ && sudo udevadm control --reload-rules && sudo udevadm trigger"
            ) from exc

    def disconnect(self) -> None:
        """Close the underlying HID transport."""
        for sec_dev, _ in self._secondary_devs:
            try:
                sec_dev.close()
            except Exception:
                pass
        self._secondary_devs = []

        if self._dev is not None:
            try:
                self._dev.close()
            except Exception:
                pass
        self._dev = None
        self._mode = None
        self._connected = False

    def close(self) -> None:
        """Close the active HID handle (BaseMouseDriver contract)."""
        self.disconnect()

    def __enter__(self) -> "FevellDevice":
        if not self.is_connected:
            self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()

    def _ensure_connected(self) -> None:
        if not self.is_connected or self._dev is None:
            raise DeviceError("Fare bağlı değil.")

    def _refresh_active_interface(self) -> None:
        """
        Check if user switched between Wired USB (04F3:026E) and Wireless 2.4GHz (04F3:026F)
        and promote the online interface to `self._dev`.
        
        # Protocol: GamingMS.exe multi-handle priority @ 0x00438150 (2026-10-29)
        """
        if not self._is_real_hardware() or not self._secondary_devs:
            return
        try:
            r5 = self._dev.get_feature_report(REPORT_ID_STATUS, PACKET_LEN_FEATURE_CMD)
            if len(r5) >= 6 and r5[5] != 0:
                return
        except Exception:
            pass

        for idx, (sec_dev, meta) in enumerate(self._secondary_devs):
            try:
                r5_sec = sec_dev.get_feature_report(REPORT_ID_STATUS, PACKET_LEN_FEATURE_CMD)
                if len(r5_sec) >= 6 and r5_sec[5] != 0:
                    old_dev = self._dev
                    old_meta = {
                        "vendor_id": self._vid,
                        "product_id": self._pid,
                        "mode": self._mode,
                        "path": self._hidraw_path.encode("utf-8"),
                    }
                    self._dev = sec_dev
                    self._vid = meta.get("vendor_id", FEVELL_VENDOR_ID)
                    self._pid = meta.get("product_id", FEVELL_WIRED_PID)
                    self._mode = meta.get("mode", "wired")
                    raw_p = meta.get("path", b"")
                    self._hidraw_path = raw_p.decode("utf-8", errors="ignore") if isinstance(raw_p, bytes) else str(raw_p)
                    if isinstance(old_dev, LinuxHidrawDevice):
                        self._secondary_devs[idx] = (old_dev, old_meta)
                    return
            except Exception:
                continue

    def poll_input_report(self) -> Optional[Dict[str, int]]:
        """
        Poll non-blocking Input Report 0x04 from the mouse to detect physical DPI button
        presses and live battery/charging telemetry updates.
        
        # Protocol: Reverse-engineered from GamingMS.exe Input Report 0x04 thread @ 0x00432c30 (2026-10-29)
        """
        self._ensure_connected()
        self._refresh_active_interface()
        latest_update: Optional[Dict[str, int]] = None

        devices_to_poll: List[HIDTransport] = [self._dev]  # type: ignore[list-item]
        for sec_dev, _ in self._secondary_devs:
            devices_to_poll.append(sec_dev)

        for transport in devices_to_poll:
            for _ in range(8):
                try:
                    raw = transport.read(PACKET_LEN_FEATURE_CMD, timeout_ms=0)
                except Exception:
                    break
                if not raw:
                    break
                parsed = parse_input_status_report(bytes(raw))
                if parsed is not None:
                    self._cached_settings.active_stage = parsed["active_stage"]
                    self._cached_settings.polling_rate = parsed["polling_rate"]
                    self._cached_settings.lod = parsed["lod"]
                    self._live_battery_pct = parsed["battery_pct"]
                    self._live_is_charging = bool(parsed["is_charging"])
                    latest_update = parsed

        if latest_update is not None:
            self._save_persisted_profile()
        return latest_update

    def _send_feature_command(self, packet: bytes) -> bool:
        """
        Send a 32-byte Feature Report 0x06 command and verify hardware ACK.
         Follows GamingMS.exe's exact timing (60ms sleep + up to 3 retries if ACK byte[1] == 0).
        
        # Protocol: Reverse-engineered from GamingMS.exe @ 0x00436470..0x0043650b (2026-10-29)
        """
        self._ensure_connected()
        if not self._is_feature_protocol():
            return False

        self._refresh_active_interface()
        is_real = self._is_real_hardware()
        delay_s = 0.055 if is_real else 0.001

        try:
            for attempt in range(3):
                self._dev.send_feature_report(packet)  # type: ignore[union-attr]
                time.sleep(delay_s)
                ack = self._dev.get_feature_report(REPORT_ID_FEATURE_CMD, PACKET_LEN_FEATURE_CMD)  # type: ignore[union-attr]
                if len(ack) >= 2 and ack[1] != 0x00:
                    break
            else:
                # Even if ack[1] stayed 0 on a sleeping wireless link, also try any online secondary interface
                pass

            # Also forward to any secondary Fevell Z1 interface that reports online in Report 0x05
            for sec_dev, _ in self._secondary_devs:
                try:
                    r5 = sec_dev.get_feature_report(REPORT_ID_STATUS, PACKET_LEN_FEATURE_CMD)
                    if len(r5) >= 6 and r5[5] != 0:
                        sec_dev.send_feature_report(packet)
                        time.sleep(0.03)
                        sec_dev.get_feature_report(REPORT_ID_FEATURE_CMD, PACKET_LEN_FEATURE_CMD)
                except Exception:
                    pass

            return True
        except Exception as exc:
            raise DeviceCommunicationError(f"Özellik raporu gönderilemedi: {exc}") from exc

    def _transceive(self, packet: bytes, timeout_ms: int = 1000) -> bytes:
        """
        Send a 16-byte command packet (prepended with Report ID) and read the 17-byte response.
        
        # Protocol: Compx / BK3633 Command-Response Exchange (2026-10-15)
        """
        self._ensure_connected()
        out_data = bytes([REPORT_ID_CMD]) + packet
        try:
            self._dev.write(out_data)  # type: ignore[union-attr]
            raw_resp = self._dev.read(PACKET_LEN_CMD + 1, timeout_ms=timeout_ms)  # type: ignore[union-attr]
        except Exception as exc:
            raise DeviceCommunicationError(f"HID iletişim hatası: {exc}") from exc

        if not raw_resp or len(raw_resp) < PACKET_LEN_CMD:
            raise DeviceCommunicationError("Fareden yanıt alınamadı (zaman aşımı).")

        resp_bytes = bytes(raw_resp)
        if len(resp_bytes) == PACKET_LEN_CMD + 1:
            report_id = resp_bytes[0]
            payload = resp_bytes[1:]
        else:
            report_id = REPORT_ID_CMD
            payload = resp_bytes[:PACKET_LEN_CMD]

        if not verify_checksum(report_id, payload):
            raise DeviceCommunicationError(f"Geçersiz yanıt sağlama toplamı (checksum): {payload.hex()}")

        return payload

    def send_heartbeat(self) -> bool:
        """
        Send PC driver status heartbeat (Command 0x02 or Feature Report 0xBC).
        # Protocol: GamingMS.exe Wake / Status Check (2026-10-29)
        """
        self._ensure_connected()
        if self._is_feature_protocol():
            try:
                self._dev.send_feature_report(bytes([REPORT_ID_WAKE] + [0x00] * 7))  # type: ignore[union-attr]
                r5 = self._dev.get_feature_report(REPORT_ID_STATUS, PACKET_LEN_FEATURE_CMD)  # type: ignore[union-attr]
                return len(r5) >= 5 and r5[0] == REPORT_ID_STATUS
            except Exception:
                return False

        pkt = build_command_packet(Command.PC_DRIVER_STATUS, payload=b"\x01")
        resp = self._transceive(pkt)
        return resp[0] == Command.PC_DRIVER_STATUS

    def is_device_online(self) -> bool:
        """
        Check if the wireless dongle or wired mouse is actively responding.
        # Protocol: GamingMS.exe Report 0x05 byte[5] check @ 0x00438263 (2026-10-29)
        """
        self._ensure_connected()
        if self._is_feature_protocol():
            try:
                r5 = self._dev.get_feature_report(REPORT_ID_STATUS, PACKET_LEN_FEATURE_CMD)  # type: ignore[union-attr]
                if len(r5) >= 6 and r5[1:5] == b"1010":
                    return bool(r5[5]) or self._mode == "wired"
                return True
            except Exception:
                return False

        pkt = build_command_packet(Command.DEVICE_ONLINE)
        resp = self._transceive(pkt)
        return bool(resp[5])

    def read_battery(self) -> BatteryStatus:
        """
        Query current battery percentage, charging status, and voltage.
        # Protocol: GamingMS.exe Input Report 0x04 & Report 0x05 Telemetry (2026-10-29)
        """
        self._ensure_connected()
        if not isinstance(self._dev, LinuxHidrawDevice):
            try:
                pkt = build_command_packet(Command.BATTERY_LEVEL)
                resp = self._transceive(pkt)
                return parse_battery_response(resp)
            except Exception:
                pass

        if self._is_feature_protocol():
            self.poll_input_report()
            try:
                r5 = self._dev.get_feature_report(REPORT_ID_STATUS, PACKET_LEN_FEATURE_CMD)  # type: ignore[union-attr]
                pct = self._live_battery_pct if self._live_battery_pct is not None else (
                    r5[7] if (len(r5) > 7 and 0 < r5[7] <= 100) else 100
                )
                is_charging = (
                    self._live_is_charging
                    if self._live_is_charging is not None
                    else (self._mode == "wired")
                )
                voltage_mv = 4200 if is_charging else int(3400 + (pct / 100.0) * 750)
                return BatteryStatus(percentage=pct, is_charging=is_charging, voltage_mv=voltage_mv)
            except Exception:
                pass

        return BatteryStatus(percentage=100, is_charging=(self._mode == "wired"), voltage_mv=4150)

    def read_flash_register(self, addr: int, length: int) -> bytes:
        """
        Read `length` bytes from mouse Flash/EEPROM starting at `addr`.
        # Protocol: Command 0x08 (ReadFlash) (2026-10-15)
        """
        self._ensure_connected()
        result = bytearray()
        offset = 0
        while offset < length:
            chunk_len = min(MAX_PAYLOAD_LEN, length - offset)
            pkt = build_command_packet(Command.READ_FLASH, addr=addr + offset, length=chunk_len)
            resp = self._transceive(pkt)
            result.extend(resp[5 : 5 + chunk_len])
            offset += chunk_len
        return bytes(result)

    def write_flash_register(self, addr: int, data: bytes) -> bool:
        """
        Write `data` bytes to mouse Flash/EEPROM starting at `addr`.
        # Protocol: Command 0x07 (WriteFlash) (2026-10-15)
        """
        self._ensure_connected()
        offset = 0
        total = len(data)
        while offset < total:
            chunk = data[offset : offset + MAX_PAYLOAD_LEN]
            pkt = build_command_packet(
                Command.WRITE_FLASH,
                addr=addr + offset,
                length=len(chunk),
                payload=chunk,
            )
            resp = self._transceive(pkt)
            if resp[0] != Command.WRITE_FLASH:
                return False
            offset += len(chunk)
        return True

    def get_polling_rate(self) -> int:
        """
        Read current polling rate in Hz (125, 250, 500, 1000).
        # Protocol: FlashAddr.POLLING_RATE / Cached Profile State (2026-10-29)
        """
        if not isinstance(self._dev, LinuxHidrawDevice):
            try:
                raw = self.read_flash_register(FlashAddr.POLLING_RATE, 2)
                encoded = decode_register_2byte(raw, 0, default=1)
                return POLLING_RATE_REVERSE_MAP.get(encoded, 1000)
            except Exception:
                pass
        return self._cached_settings.polling_rate

    def set_polling_rate(self, rate_hz: int) -> bool:
        """
        Set mouse polling rate in Hz (125, 250, 500, 1000).
        # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x04 @ 0x00436764 (2026-10-29)
        """
        if rate_hz not in POLLING_RATE_MAP:
            raise ValueError(f"Desteklenmeyen polling rate: {rate_hz} Hz. Geçerli değerler: {list(POLLING_RATE_MAP.keys())}")

        if self._is_feature_protocol():
            pkt = build_feature_polling_packet(self._next_seq(), rate_hz)
            self._send_feature_command(pkt)
            self._cached_settings.polling_rate = rate_hz
            self._save_persisted_profile()
            return True

        encoded = encode_register_2byte(POLLING_RATE_MAP[rate_hz])
        return self.write_flash_register(FlashAddr.POLLING_RATE, encoded)

    def get_debounce(self) -> int:
        """
        Read button debounce time in ms.
        # Protocol: FlashAddr.DEBOUNCE / Cached Profile State (2026-10-29)
        """
        if not isinstance(self._dev, LinuxHidrawDevice):
            try:
                raw = self.read_flash_register(FlashAddr.DEBOUNCE, 2)
                return decode_register_2byte(raw, 0, default=DEFAULT_DEBOUNCE_MS)
            except Exception:
                pass
        return self._cached_settings.debounce_ms

    def set_debounce(self, ms: int) -> bool:
        """
        Set button debounce time in ms (0 - 30 ms).
        # Protocol: GamingMS.exe KeyDebounce @ 0x00435ed4 (2026-10-29)
        """
        if not (DEBOUNCE_MIN_MS <= ms <= DEBOUNCE_MAX_MS):
            raise ValueError(f"Debounce süresi {DEBOUNCE_MIN_MS}-{DEBOUNCE_MAX_MS} ms aralığında olmalıdır.")

        if not isinstance(self._dev, LinuxHidrawDevice):
            try:
                encoded = encode_register_2byte(ms)
                self.write_flash_register(FlashAddr.DEBOUNCE, encoded)
            except Exception:
                pass

        if self._is_feature_protocol():
            self._cached_settings.debounce_ms = ms
            self._save_persisted_profile()
            return True

        encoded = encode_register_2byte(ms)
        return self.write_flash_register(FlashAddr.DEBOUNCE, encoded)

    def get_lod(self) -> int:
        """
        Read sensor Lift-Off Distance in mm (1 or 2).
        # Protocol: FlashAddr.LIFT_OFF / Cached Profile State (2026-10-29)
        """
        if not isinstance(self._dev, LinuxHidrawDevice):
            try:
                raw = self.read_flash_register(FlashAddr.LIFT_OFF, 2)
                val = decode_register_2byte(raw, 0, default=LOD_1MM)
                return val if val in VALID_LOD_VALUES else LOD_1MM
            except Exception:
                pass
        return self._cached_settings.lod

    def set_lod(self, lod_mm: int) -> bool:
        """
        Set sensor Lift-Off Distance in mm (1 or 2).
        # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x05 @ 0x00436881 (2026-10-29)
        """
        if lod_mm not in VALID_LOD_VALUES:
            raise ValueError(f"Geçersiz LOD değeri: {lod_mm} mm. Sadece 1 veya 2 mm desteklenir.")

        if self._is_feature_protocol():
            pkt = build_feature_lod_packet(self._next_seq(), lod_mm)
            self._send_feature_command(pkt)
            self._cached_settings.lod = lod_mm
            self._save_persisted_profile()
            return True

        encoded = encode_register_2byte(lod_mm)
        return self.write_flash_register(FlashAddr.LIFT_OFF, encoded)

    def get_active_dpi_stage(self) -> int:
        """
        Get the active DPI stage index (0-based).
        # Protocol: FlashAddr.ACTIVE_STAGE / Cached Profile State (2026-10-29)
        """
        if not isinstance(self._dev, LinuxHidrawDevice):
            try:
                raw = self.read_flash_register(FlashAddr.ACTIVE_STAGE, 2)
                stage = decode_register_2byte(raw, 0, default=1)
                return max(0, min(MAX_DPI_STAGES - 1, stage))
            except Exception:
                pass
        return self._cached_settings.active_stage

    def set_active_dpi_stage(self, stage_index: int) -> bool:
        """
        Set the active DPI stage index (0 to 5).
        # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x02 @ 0x00436314 (2026-10-29)
        """
        if not (0 <= stage_index < MAX_DPI_STAGES):
            raise ValueError(f"DPI kademe indeksi 0 ile {MAX_DPI_STAGES - 1} arasında olmalıdır.")

        if self._is_feature_protocol():
            self._cached_settings.active_stage = stage_index
            pkt = build_feature_dpi_packet(
                self._next_seq(),
                stages=self._cached_settings.dpi_stages[:MAX_DPI_STAGES],
                active_stage=stage_index,
                enable_mask=self._cached_settings.stage_enable_mask,
                debounce_ms=self._cached_settings.debounce_ms,
            )
            self._send_feature_command(pkt)
            self._save_persisted_profile()
            return True

        encoded = encode_register_2byte(stage_index)
        return self.write_flash_register(FlashAddr.ACTIVE_STAGE, encoded)

    def get_dpi_stage_count(self) -> int:
        """
        Get number of enabled DPI stages (1 to 6).
        # Protocol: FlashAddr.STAGE_COUNT / Cached Profile State (2026-10-29)
        """
        if not isinstance(self._dev, LinuxHidrawDevice):
            try:
                raw = self.read_flash_register(FlashAddr.STAGE_COUNT, 2)
                count = decode_register_2byte(raw, 0, default=5)
                return max(1, min(MAX_DPI_STAGES, count))
            except Exception:
                pass
        return self._cached_settings.stage_count

    def set_dpi_stage_count(self, count: int) -> bool:
        """
        Set number of enabled DPI stages (1 to 6).
        # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x02 @ 0x00436314 (2026-10-29)
        """
        if not (1 <= count <= MAX_DPI_STAGES):
            raise ValueError(f"DPI kademe sayısı 1 ile {MAX_DPI_STAGES} arasında olmalıdır.")

        if self._is_feature_protocol():
            self._cached_settings.stage_count = count
            self._cached_settings.stage_enable_mask = (1 << count) - 1
            if self._cached_settings.active_stage >= count:
                self._cached_settings.active_stage = count - 1
            pkt = build_feature_dpi_packet(
                self._next_seq(),
                stages=self._cached_settings.dpi_stages[:MAX_DPI_STAGES],
                active_stage=self._cached_settings.active_stage,
                enable_mask=self._cached_settings.stage_enable_mask,
                debounce_ms=self._cached_settings.debounce_ms,
            )
            self._send_feature_command(pkt)
            self._save_persisted_profile()
            return True

        encoded = encode_register_2byte(count)
        return self.write_flash_register(FlashAddr.STAGE_COUNT, encoded)

    def get_dpi_stages(self, count: Optional[int] = None) -> List[int]:
        """
        Read DPI values for each stage.
        # Protocol: FlashAddr.DPI_STAGES / Cached Profile State (2026-10-29)
        """
        if count is None:
            count = self.get_dpi_stage_count()

        if not isinstance(self._dev, LinuxHidrawDevice):
            try:
                raw = self.read_flash_register(FlashAddr.DPI_STAGES, count * 4)
                stages = []
                for i in range(count):
                    stages.append(decode_dpi_stage(raw, offset=i * 4))
                return stages
            except Exception:
                pass

        return list(self._cached_settings.dpi_stages[:count])

    def set_dpi_stage(self, stage_index: int, dpi: int) -> bool:
        """
        Set the DPI value (50 - 26000, step 50) for a specific stage index (0-based).
        # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x02 @ 0x00436314 (2026-10-29)
        """
        if not (0 <= stage_index < MAX_DPI_STAGES):
            raise ValueError(f"Geçersiz DPI kademe indeksi: {stage_index}")
        if not (DPI_MIN <= dpi <= DPI_MAX):
            raise ValueError(f"DPI değeri {DPI_MIN} ile {DPI_MAX} arasında olmalıdır.")

        rounded_dpi = max(DPI_MIN, min(DPI_MAX, round(dpi / DPI_STEP) * DPI_STEP))

        if self._is_feature_protocol():
            while len(self._cached_settings.dpi_stages) <= stage_index:
                self._cached_settings.dpi_stages.append(800)
            self._cached_settings.dpi_stages[stage_index] = rounded_dpi
            pkt = build_feature_dpi_packet(
                self._next_seq(),
                stages=self._cached_settings.dpi_stages[:MAX_DPI_STAGES],
                active_stage=self._cached_settings.active_stage,
                enable_mask=self._cached_settings.stage_enable_mask,
                debounce_ms=self._cached_settings.debounce_ms,
            )
            self._send_feature_command(pkt)
            self._save_persisted_profile()
            return True

        encoded = encode_dpi_stage(rounded_dpi)
        addr = FlashAddr.DPI_STAGES + (stage_index * 4)
        return self.write_flash_register(addr, encoded)

    def set_dpi_configuration(
        self,
        stages: List[int],
        active_stage: int = 0,
        stage_count: Optional[int] = None,
        enable_mask: Optional[int] = None,
        colors: Optional[List[Tuple[int, int, int]]] = None,
    ) -> bool:
        """
        Update all DPI stages, active stage index, stage enable mask, and optional stage RGB colors.
        
        # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x02 & Cmd 0x03 @ 0x00436314..0x0043675a (2026-10-29)
        """
        if not stages:
            raise ValueError("En az bir DPI kademesi belirtilmelidir.")
        count = stage_count if stage_count is not None else len(stages)
        if not (1 <= count <= MAX_DPI_STAGES):
            raise ValueError(f"DPI kademe sayısı 1 ile {MAX_DPI_STAGES} arasında olmalıdır.")
        if not (0 <= active_stage < MAX_DPI_STAGES):
            raise ValueError(f"Aktif kademe indeksi 0 ile {MAX_DPI_STAGES - 1} arasında olmalıdır.")

        normalized_stages: List[int] = []
        for dpi in stages[:MAX_DPI_STAGES]:
            if not (DPI_MIN <= dpi <= DPI_MAX):
                raise ValueError(f"DPI değeri {DPI_MIN} ile {DPI_MAX} arasında olmalıdır.")
            normalized_stages.append(max(DPI_MIN, min(DPI_MAX, round(dpi / DPI_STEP) * DPI_STEP)))

        while len(normalized_stages) < MAX_DPI_STAGES:
            idx = len(normalized_stages)
            fallback = (
                self._cached_settings.dpi_stages[idx]
                if idx < len(self._cached_settings.dpi_stages)
                else DEFAULT_DPI_STAGES[idx]
            )
            normalized_stages.append(fallback)

        if enable_mask is None:
            mask = (1 << count) - 1
        else:
            mask = enable_mask & 0x3F
            if mask == 0:
                mask = (1 << count) - 1
            count = bin(mask).count("1")

        self._cached_settings.dpi_stages = normalized_stages
        self._cached_settings.stage_count = count
        self._cached_settings.stage_enable_mask = mask
        self._cached_settings.active_stage = active_stage

        if colors is not None:
            norm_colors = list(colors[:MAX_DPI_STAGES])
            while len(norm_colors) < MAX_DPI_STAGES:
                norm_colors.append(DEFAULT_DPI_STAGE_COLORS[len(norm_colors)])
            self._cached_settings.dpi_colors = norm_colors

        if self._is_feature_protocol():
            pkt = build_feature_dpi_packet(
                self._next_seq(),
                stages=normalized_stages,
                active_stage=active_stage,
                enable_mask=mask,
                debounce_ms=self._cached_settings.debounce_ms,
            )
            self._send_feature_command(pkt)
            if colors is not None:
                color_pkt = build_feature_dpi_colors_packet(self._next_seq(), self._cached_settings.dpi_colors)
                self._send_feature_command(color_pkt)
            self._save_persisted_profile()
            return True

        self.set_dpi_stage_count(count)
        for idx, dpi_val in enumerate(normalized_stages[:count]):
            self.set_dpi_stage(idx, dpi_val)
        self.set_active_dpi_stage(active_stage)
        return True

    def set_dpi(self, dpi: int, stage_index: Optional[int] = None) -> bool:
        """
        Convenience method to set the specified or currently active stage's DPI immediately.
        # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x02 @ 0x00436314 (2026-10-29)
        """
        target_idx = stage_index if stage_index is not None else self.get_active_dpi_stage()
        return self.set_dpi_stage(target_idx, dpi)

    def get_dpi_color(self, stage_index: int) -> Tuple[int, int, int]:
        """
        Read RGB color tuple for a DPI stage.
        # Protocol: FlashAddr.DPI_COLORS / Cached Profile State (2026-10-29)
        """
        if not (0 <= stage_index < MAX_DPI_STAGES):
            raise ValueError(f"Geçersiz DPI kademe indeksi: {stage_index}")
        if not isinstance(self._dev, LinuxHidrawDevice):
            try:
                addr = FlashAddr.DPI_COLORS + (stage_index * 4)
                raw = self.read_flash_register(addr, 4)
                return decode_dpi_color(raw, 0)
            except Exception:
                pass
        if stage_index < len(self._cached_settings.dpi_colors):
            return self._cached_settings.dpi_colors[stage_index]
        return DEFAULT_DPI_STAGE_COLORS[stage_index]

    def set_dpi_color(self, stage_index: int, r: int, g: int, b: int) -> bool:
        """
        Set RGB indicator color for a DPI stage.
        # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x03 @ 0x00436515 (2026-10-29)
        """
        if not (0 <= stage_index < MAX_DPI_STAGES):
            raise ValueError(f"Geçersiz DPI kademe indeksi: {stage_index}")

        color_tuple = (r & 0xFF, g & 0xFF, b & 0xFF)
        while len(self._cached_settings.dpi_colors) <= stage_index:
            self._cached_settings.dpi_colors.append(
                DEFAULT_DPI_STAGE_COLORS[len(self._cached_settings.dpi_colors)]
            )
        self._cached_settings.dpi_colors[stage_index] = color_tuple

        if not isinstance(self._dev, LinuxHidrawDevice):
            try:
                encoded = encode_dpi_color(r, g, b)
                addr = FlashAddr.DPI_COLORS + (stage_index * 4)
                self.write_flash_register(addr, encoded)
            except Exception:
                pass

        if self._is_feature_protocol():
            pkt = build_feature_dpi_colors_packet(self._next_seq(), self._cached_settings.dpi_colors)
            self._send_feature_command(pkt)
            self._save_persisted_profile()
            return True

        encoded = encode_dpi_color(r, g, b)
        addr = FlashAddr.DPI_COLORS + (stage_index * 4)
        return self.write_flash_register(addr, encoded)

    def set_sensor_advanced(
        self,
        angle_snap: bool = False,
        motion_sync: bool = True,
        ripple_control: bool = False,
    ) -> bool:
        """
        Configure PAW3395 advanced sensor features (Angle Snapping, Motion Sync, Ripple Control).
        # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x08 @ 0x00436da0..0x00437029 (2026-10-29)
        """
        self._cached_settings.angle_snap = bool(angle_snap)
        self._cached_settings.motion_sync = bool(motion_sync)
        self._cached_settings.ripple_control = bool(ripple_control)

        if self._is_feature_protocol():
            pkt = build_feature_sensor_advanced_packet(
                self._next_seq(),
                angle_snap=angle_snap,
                motion_sync=motion_sync,
                ripple_control=ripple_control,
            )
            self._send_feature_command(pkt)
            self._save_persisted_profile()
            return True
        return True

    def set_power_sleep(
        self,
        sleep_timeout_min: int = 1,
        move_light_off: bool = True,
    ) -> bool:
        """
        Configure wireless sleep timeout and LED off-on-movement power saving mode.
        # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x07 @ 0x00436ae0..0x00436d42 (2026-10-29)
        """
        self._cached_settings.sleep_timeout_min = max(1, min(30, sleep_timeout_min))
        self._cached_settings.move_light_off = bool(move_light_off)

        if self._is_feature_protocol():
            pkt = build_feature_power_sleep_packet(
                self._next_seq(),
                sleep_timeout_min=self._cached_settings.sleep_timeout_min,
                move_light_off=self._cached_settings.move_light_off,
            )
            self._send_feature_command(pkt)
            self._save_persisted_profile()
            return True
        return True

    def set_lighting(
        self,
        mode: int = 1,
        brightness: int = 3,
        speed: int = 2,
        color: Tuple[int, int, int] = (255, 0, 0),
    ) -> bool:
        """
        Configure mouse lighting effect mode, brightness, and speed.
        # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x06 @ 0x004369a4..0x00436ad3 (2026-10-29)
        """
        self._cached_settings.lighting_mode = max(0, min(9, mode))
        self._cached_settings.lighting_brightness = max(1, min(4, brightness))
        self._cached_settings.lighting_speed = max(1, min(4, speed))

        if self._is_feature_protocol():
            pkt = build_feature_lighting_packet(
                self._next_seq(),
                mode=self._cached_settings.lighting_mode,
                brightness=self._cached_settings.lighting_brightness,
                speed=self._cached_settings.lighting_speed,
                color=color,
            )
            self._send_feature_command(pkt)
            self._save_persisted_profile()
            return True
        return True

    def set_button_mappings(self, button_keys: List[str]) -> bool:
        """
        Configure 6-button assignments on the Fevell Z1 mouse.
        # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x01 @ 0x004358b6..0x00435c60 (2026-10-29)
        """
        if len(button_keys) < 6:
            raise ValueError("6 adet tuş ataması belirtilmelidir.")
        for k in button_keys[:6]:
            if k not in BUTTON_ACTIONS:
                raise ValueError(f"Geçersiz tuş eylemi: {k}")

        self._cached_settings.button_mappings = list(button_keys[:6])
        if self._is_feature_protocol():
            pkt = build_feature_key_mapping_packet(self._next_seq(), self._cached_settings.button_mappings)
            self._send_feature_command(pkt)
            self._save_persisted_profile()
            return True
        return True

    def factory_reset(self) -> bool:
        """
        Restore the mouse hardware and local profile to factory defaults.
        
        # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x0F @ 0x00437f60 & 0x0041b3c1 (2026-10-29)
        """
        self._ensure_connected()
        default_settings = MouseSettings(
            polling_rate=1000,
            debounce_ms=DEFAULT_DEBOUNCE_MS,
            lod=LOD_1MM,
            active_stage=1,
            stage_count=4,
            stage_enable_mask=0x0F,
            dpi_stages=list(DEFAULT_DPI_STAGES),
            dpi_colors=list(DEFAULT_DPI_STAGE_COLORS[:MAX_DPI_STAGES]),
            angle_snap=False,
            motion_sync=True,
            ripple_control=False,
            sleep_timeout_min=1,
            move_light_off=True,
            lighting_mode=1,
            lighting_brightness=3,
            lighting_speed=2,
            button_mappings=list(DEFAULT_BUTTON_KEYS),
        )
        self._cached_settings = default_settings
        if self._is_feature_protocol():
            pkt_reset = build_feature_factory_reset_packet(self._next_seq())
            self._send_feature_command(pkt_reset)
            self.apply_settings(default_settings)
            return True

        self._save_persisted_profile()
        return True

    def read_settings(self) -> MouseSettings:
        """
        Read a complete snapshot of current mouse settings.
        # Protocol: GamingMS.exe State & Input Report 0x04 Sync (2026-10-29)
        """
        self._ensure_connected()
        if not isinstance(self._dev, LinuxHidrawDevice):
            try:
                stage_count = self.get_dpi_stage_count()
                active_stage = self.get_active_dpi_stage()
                stages = self.get_dpi_stages(count=stage_count)
                colors = [self.get_dpi_color(i) for i in range(MAX_DPI_STAGES)]
                return MouseSettings(
                    polling_rate=self.get_polling_rate(),
                    debounce_ms=self.get_debounce(),
                    lod=self.get_lod(),
                    active_stage=min(active_stage, stage_count - 1),
                    stage_count=stage_count,
                    stage_enable_mask=(1 << stage_count) - 1,
                    dpi_stages=stages,
                    dpi_colors=colors,
                    angle_snap=self._cached_settings.angle_snap,
                    motion_sync=self._cached_settings.motion_sync,
                    ripple_control=self._cached_settings.ripple_control,
                    sleep_timeout_min=self._cached_settings.sleep_timeout_min,
                    move_light_off=self._cached_settings.move_light_off,
                    lighting_mode=self._cached_settings.lighting_mode,
                    lighting_brightness=self._cached_settings.lighting_brightness,
                    lighting_speed=self._cached_settings.lighting_speed,
                    button_mappings=list(self._cached_settings.button_mappings),
                )
            except Exception:
                pass

        self.poll_input_report()
        return MouseSettings(
            polling_rate=self._cached_settings.polling_rate,
            debounce_ms=self._cached_settings.debounce_ms,
            lod=self._cached_settings.lod,
            active_stage=self._cached_settings.active_stage,
            stage_count=self._cached_settings.stage_count,
            stage_enable_mask=self._cached_settings.stage_enable_mask,
            dpi_stages=list(self._cached_settings.dpi_stages),
            dpi_colors=list(self._cached_settings.dpi_colors),
            angle_snap=self._cached_settings.angle_snap,
            motion_sync=self._cached_settings.motion_sync,
            ripple_control=self._cached_settings.ripple_control,
            sleep_timeout_min=self._cached_settings.sleep_timeout_min,
            move_light_off=self._cached_settings.move_light_off,
            lighting_mode=self._cached_settings.lighting_mode,
            lighting_brightness=self._cached_settings.lighting_brightness,
            lighting_speed=self._cached_settings.lighting_speed,
            button_mappings=list(self._cached_settings.button_mappings),
        )

    def apply_settings(self, settings: MouseSettings) -> bool:
        """
        Write a complete MouseSettings configuration to the mouse hardware.
        Sends verified Feature Report 0x06 commands without triggering Factory Reset (0x0F).
        
        # Protocol: Reverse-engineered from GamingMS.exe @ 0x00435870..0x00437029 (2026-10-29)
        """
        self._ensure_connected()
        mask = (1 << settings.stage_count) - 1
        if settings.stage_enable_mask and bin(settings.stage_enable_mask).count("1") == settings.stage_count:
            mask = settings.stage_enable_mask
        self.set_debounce(settings.debounce_ms)
        self.set_dpi_configuration(
            stages=settings.dpi_stages,
            active_stage=settings.active_stage,
            stage_count=settings.stage_count,
            enable_mask=mask,
            colors=settings.dpi_colors if settings.dpi_colors else None,
        )
        self.set_polling_rate(settings.polling_rate)
        self.set_lod(settings.lod)
        self.set_sensor_advanced(
            angle_snap=settings.angle_snap,
            motion_sync=settings.motion_sync,
            ripple_control=settings.ripple_control,
        )
        self.set_power_sleep(
            sleep_timeout_min=settings.sleep_timeout_min,
            move_light_off=settings.move_light_off,
        )
        self.set_lighting(
            mode=settings.lighting_mode,
            brightness=settings.lighting_brightness,
            speed=settings.lighting_speed,
        )
        if settings.button_mappings and len(settings.button_mappings) >= 6:
            self.set_button_mappings(settings.button_mappings)
        self._save_persisted_profile()
        return True

    def get_hardware_info(self) -> Dict[str, str]:
        """
        Return comprehensive hardware, sensor, MCU, and protocol diagnostics.
        
        # Protocol: Hardware & Descriptor Inspection (2026-10-29)
        """
        self._ensure_connected()
        r5_hex = "N/A"
        rbc_hex = "N/A"
        online_flag = "Aktif"

        if self._is_feature_protocol():
            try:
                r5 = self._dev.get_feature_report(REPORT_ID_STATUS, PACKET_LEN_FEATURE_CMD)  # type: ignore[union-attr]
                r5_hex = r5[:8].hex(" ").upper()
                if len(r5) >= 6 and r5[1:5] == b"1010":
                    self._firmware_str = "1010 (v1.0.1.0)"
                    online_flag = "Çevrimiçi (0x01)" if r5[5] else "Uyku / Beklemede (0x00)"
            except Exception:
                pass
            try:
                rbc = self._dev.get_feature_report(REPORT_ID_WAKE, PACKET_LEN_WAKE)  # type: ignore[union-attr]
                rbc_hex = rbc.hex(" ").upper()
            except Exception:
                pass

        conn_label = (
            "USB Kablolu (04F3:026E)"
            if self._mode == "wired"
            else (
                "4K/8K Kablosuz Alıcı (04F3:026D)"
                if self._mode == "dongle_4k"
                else "2.4 GHz Kablosuz Alıcı (04F3:026F)"
            )
        )

        return {
            "model_name": "Fevell Z1 / Furylevel Z1",
            "sensor_model": "PixArt PAW3395 (26.000 DPI, 650 IPS, 50G)",
            "mcu_model": "Beken BK3633 (Tri-Mode 2.4GHz / BT / USB-C)",
            "vendor_id": f"0x{self._vid:04X}",
            "product_id": f"0x{self._pid:04X}",
            "connection_type": conn_label,
            "hidraw_node": self._hidraw_path,
            "usb_interface": f"Interface {VENDOR_INTERFACE_NUMBER} (Usage Page 0x{VENDOR_USAGE_PAGE:04X})",
            "firmware_handshake": f"{self._firmware_str} — {online_flag}",
            "status_report_05": r5_hex,
            "wake_report_bc": rbc_hex,
            "driver_version": "M-Control v0.3.0 (Native Linux HID Driver — GamingMS.exe Protocol)",
        }


DRIVER_REGISTRY: List[Type[BaseMouseDriver]] = [FevellDevice]


def discover_mouse() -> Optional[BaseMouseDriver]:
    """
    Iterate over registered mouse drivers and return the first connected instance.
    # Protocol: Multi-driver auto-discovery (2026-10-29)
    """
    for driver_cls in DRIVER_REGISTRY:
        try:
            driver = driver_cls()
            if driver.connect():
                return driver
        except Exception:
            continue
    return None
