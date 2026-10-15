"""High-level hardware controller and configuration manager for Fevell Z1."""

import logging
from typing import List, Optional, Tuple

from mcontrol.core.constants import (
    Command,
    DPI_MAX,
    DPI_MIN,
    DPI_STEP,
    DEBOUNCE_MAX_MS,
    DEBOUNCE_MIN_MS,
    DONGLE_INTERFACE,
    DONGLE_PID,
    DONGLE_VID,
    FlashAddr,
    LOD_1MM,
    LOD_2MM,
    MAX_DPI_STAGES,
    MAX_PAYLOAD_LEN,
    POLLING_RATE_MAP,
    POLLING_RATE_REVERSE_MAP,
    REPORT_ID_CMD,
    SUPPORTED_DEVICES,
    WIRED_INTERFACE,
    WIRED_PID,
    WIRED_VID,
)
from mcontrol.core.protocol import (
    BatteryStatus,
    MouseSettings,
    build_command_packet,
    decode_dpi_color,
    decode_dpi_stage,
    decode_register_2byte,
    encode_dpi_color,
    encode_dpi_stage,
    encode_register_2byte,
    parse_battery_response,
    verify_checksum,
)

logger = logging.getLogger(__name__)


class DeviceError(Exception):
    """Base exception for device-related errors."""
    pass


class DeviceNotFoundError(DeviceError):
    """Raised when the Fevell Z1 mouse or receiver cannot be found."""
    pass


class DeviceCommunicationError(DeviceError):
    """Raised when an HID packet exchange fails or times out."""
    pass


class FevellDevice:
    """
    High-level hardware controller for the Fevell Z1 gaming mouse.
    
    # Protocol: Beken BK3633 / PixArt PAW3395 Architecture (2026-10-15)
    Supports wired mode (04F3:026E) and 2.4GHz wireless dongle mode (32C2:0018).
    """

    def __init__(self, hid_device=None, mode: Optional[str] = None):
        """
        Initialize the device controller.
        
        # Protocol: Device abstraction initialization (2026-10-15)
        If hid_device is provided (e.g. MockHIDDevice), it is used directly.
        """
        self._dev = hid_device
        self._mode = mode
        self._path: Optional[bytes] = None

    @property
    def is_connected(self) -> bool:
        """Check if an active HID connection exists."""
        if self._dev is None:
            return False
        if hasattr(self._dev, "is_open"):
            return bool(self._dev.is_open)
        return True

    @property
    def mode(self) -> Optional[str]:
        """Return the current connection mode ('wired', 'dongle', or None)."""
        return self._mode if self.is_connected else None

    # Protocol: USB HID device discovery and connection (2026-10-15)
    def connect(self, hid_device=None, mode: Optional[str] = None) -> bool:
        """
        Connect to Fevell Z1 hardware or an injected HID implementation.
        
        # Protocol: Interface enumeration standard (2026-10-15)
        Target interfaces:
        - Wired (04F3:026E): Interface 1 (Vendor Control EP2)
        - Dongle (32C2:0018): Interface 2 (Vendor Control)
        """
        if self.is_connected and hid_device is None:
            return True

        if hid_device is not None:
            self._dev = hid_device
            self._mode = mode or "wired"
            if hasattr(self._dev, "open") and not getattr(self._dev, "is_open", False):
                self._dev.open(WIRED_VID, WIRED_PID)
            return True

        try:
            import hid
        except ImportError:
            raise DeviceError("hidapi is required for physical hardware communication.")

        # 1. First probe for wired connection (04F3:026E, Interface 1)
        wired_infos = hid.enumerate(WIRED_VID, WIRED_PID)
        for info in wired_infos:
            if info.get("interface_number") == WIRED_INTERFACE:
                dev = hid.device()
                dev.open_path(info["path"])
                self._dev = dev
                self._mode = "wired"
                self._path = info["path"]
                logger.info(f"Connected to Fevell Z1 via wired interface ({info['path']})")
                return True

        # 2. Probe for 2.4GHz wireless dongle (32C2:0018, Interface 2)
        dongle_infos = hid.enumerate(DONGLE_VID, DONGLE_PID)
        for info in dongle_infos:
            if info.get("interface_number") == DONGLE_INTERFACE:
                dev = hid.device()
                dev.open_path(info["path"])
                self._dev = dev
                self._mode = "dongle"
                self._path = info["path"]
                logger.info(f"Connected to Fevell Z1 2.4G Receiver ({info['path']})")
                # Wake RF link and check if mouse is awake
                self.send_heartbeat()
                return True

        return False

    # Protocol: Clean HID connection teardown (2026-10-15)
    def disconnect(self):
        """Disconnect and release the HID device handle."""
        if self._dev is not None:
            try:
                self._dev.close()
            except Exception as e:
                logger.warning(f"Error while closing HID device: {e}")
            finally:
                self._dev = None
                self._mode = None
                self._path = None

    # Protocol: 16-byte command exchange via Report ID 0x08 (2026-10-15)
    def _exchange(self, packet: bytes, timeout_ms: int = 500) -> bytes:
        """
        Send a 16-byte command packet and read the 16-byte response.
        
        # Protocol: BK3633 command packet exchange (2026-10-15)
        """
        if not self.is_connected:
            raise DeviceError("Device is not connected.")

        # Outgoing buffer prepends the Report ID (REPORT_ID_CMD = 0x08)
        out_buf = bytes([REPORT_ID_CMD]) + packet
        bytes_written = self._dev.write(out_buf)
        if bytes_written <= 0:
            raise DeviceCommunicationError("Failed to write HID command packet.")

        # Read 17 bytes (Report ID + 16 payload bytes)
        raw_resp = self._dev.read(17, timeout_ms)
        if not raw_resp:
            raise DeviceCommunicationError("Device read timed out with no response.")

        resp_bytes = bytes(raw_resp)
        report_id = resp_bytes[0]
        payload = resp_bytes[1:]

        if not verify_checksum(report_id, payload):
            raise DeviceCommunicationError(
                f"Checksum verification failed on response packet: {payload.hex()}"
            )

        return payload

    # Protocol: Heartbeat keep-alive to wake wireless RF link (2026-10-15)
    def send_heartbeat(self) -> bool:
        """
        Send a heartbeat packet (Command 0x02) to awaken or maintain RF link.
        
        # Protocol: PC Driver Status command 0x02 (2026-10-15)
        """
        packet = build_command_packet(Command.PC_DRIVER_STATUS)
        resp = self._exchange(packet)
        return resp[0] == Command.PC_DRIVER_STATUS

    # Protocol: Query device reachability / online state (2026-10-15)
    def is_device_online(self) -> bool:
        """
        Check if the mouse hardware is awake and communicating.
        
        # Protocol: Device Online query command 0x03 (2026-10-15)
        """
        packet = build_command_packet(Command.DEVICE_ONLINE)
        try:
            resp = self._exchange(packet)
            return resp[5] == 0x01
        except DeviceCommunicationError:
            return False

    # Protocol: Query battery state and voltage (2026-10-15)
    def read_battery(self) -> BatteryStatus:
        """
        Query battery percentage, charging state, and millivolts.
        
        # Protocol: Battery query command 0x04 (2026-10-15)
        """
        packet = build_command_packet(Command.BATTERY_LEVEL)
        resp = self._exchange(packet)
        return parse_battery_response(resp)

    # Protocol: Read registers from onboard flash (2026-10-15)
    def read_flash_register(self, addr: int, length: int) -> bytes:
        """
        Read up to 'length' bytes from flash starting at 'addr'.
        
        # Protocol: Flash read command 0x08 (2026-10-15)
        Chunks requests so length does not exceed MAX_PAYLOAD_LEN (10 bytes).
        """
        result = bytearray()
        bytes_left = length
        curr_addr = addr

        while bytes_left > 0:
            chunk_len = min(bytes_left, MAX_PAYLOAD_LEN)
            packet = build_command_packet(Command.READ_FLASH, addr=curr_addr, length=chunk_len)
            resp = self._exchange(packet)
            # Response payload begins at index 5
            chunk_data = resp[5 : 5 + chunk_len]
            result.extend(chunk_data)
            curr_addr += chunk_len
            bytes_left -= chunk_len

        return bytes(result)

    # Protocol: Write registers to onboard flash (2026-10-15)
    def write_flash_register(self, addr: int, data: bytes) -> bool:
        """
        Write data bytes to onboard flash starting at 'addr'.
        
        # Protocol: Flash write command 0x07 (2026-10-15)
        Follows hardware safety rules: chunks <= 10 bytes and validates boundaries.
        """
        bytes_left = len(data)
        curr_addr = addr
        offset = 0

        while bytes_left > 0:
            chunk_len = min(bytes_left, MAX_PAYLOAD_LEN)
            chunk_data = data[offset : offset + chunk_len]
            packet = build_command_packet(
                Command.WRITE_FLASH,
                addr=curr_addr,
                length=chunk_len,
                payload=chunk_data,
            )
            self._exchange(packet)
            curr_addr += chunk_len
            offset += chunk_len
            bytes_left -= chunk_len

        return True

    # Protocol: Polling rate register query (2026-10-15)
    def get_polling_rate(self) -> int:
        """
        Get current polling rate in Hz (125, 250, 500, 1000).
        
        # Protocol: FlashAddr.POLLING_RATE (0x00) query (2026-10-15)
        """
        raw = self.read_flash_register(FlashAddr.POLLING_RATE, 2)
        reg_val = decode_register_2byte(raw, default=1)
        return POLLING_RATE_REVERSE_MAP.get(reg_val, 1000)

    # Protocol: Polling rate register update (2026-10-15)
    def set_polling_rate(self, hz: int) -> bool:
        """
        Set polling rate in Hz (125, 250, 500, 1000).
        
        # Protocol: FlashAddr.POLLING_RATE (0x00) update (2026-10-15)
        """
        if hz not in POLLING_RATE_MAP:
            allowed = list(POLLING_RATE_MAP.keys())
            raise ValueError(f"Invalid polling rate: {hz}. Allowed rates: {allowed}")

        val = POLLING_RATE_MAP[hz]
        data = encode_register_2byte(val)
        return self.write_flash_register(FlashAddr.POLLING_RATE, data)

    # Protocol: Debounce time query (2026-10-15)
    def get_debounce(self) -> int:
        """
        Get switch debounce time in milliseconds (1-20 ms).
        
        # Protocol: FlashAddr.DEBOUNCE (0xA9) query (2026-10-15)
        """
        raw = self.read_flash_register(FlashAddr.DEBOUNCE, 2)
        return decode_register_2byte(raw, default=4)

    # Protocol: Debounce time update (2026-10-15)
    def set_debounce(self, ms: int) -> bool:
        """
        Set switch debounce time in milliseconds (1-20 ms).
        
        # Protocol: FlashAddr.DEBOUNCE (0xA9) update (2026-10-15)
        """
        if not (DEBOUNCE_MIN_MS <= ms <= DEBOUNCE_MAX_MS):
            raise ValueError(
                f"Debounce must be between {DEBOUNCE_MIN_MS} and {DEBOUNCE_MAX_MS} ms."
            )
        data = encode_register_2byte(ms)
        return self.write_flash_register(FlashAddr.DEBOUNCE, data)

    # Protocol: Lift-off distance query (2026-10-15)
    def get_lod(self) -> int:
        """
        Get Lift-Off Distance level (1 = 1mm, 2 = 2mm).
        
        # Protocol: FlashAddr.LIFT_OFF (0x0A) query (2026-10-15)
        """
        raw = self.read_flash_register(FlashAddr.LIFT_OFF, 2)
        return decode_register_2byte(raw, default=1)

    # Protocol: Lift-off distance update (2026-10-15)
    def set_lod(self, level: int) -> bool:
        """
        Set Lift-Off Distance level (1 = 1mm, 2 = 2mm).
        
        # Protocol: FlashAddr.LIFT_OFF (0x0A) update (2026-10-15)
        """
        if level not in (LOD_1MM, LOD_2MM):
            raise ValueError(f"Invalid LOD level: {level}. Must be 1 (1mm) or 2 (2mm).")
        data = encode_register_2byte(level)
        return self.write_flash_register(FlashAddr.LIFT_OFF, data)

    # Protocol: Active DPI stage index query (2026-10-15)
    def get_active_dpi_stage(self) -> int:
        """
        Get 0-based index of the currently active DPI stage.
        
        # Protocol: FlashAddr.ACTIVE_STAGE (0x04) query (2026-10-15)
        """
        raw = self.read_flash_register(FlashAddr.ACTIVE_STAGE, 2)
        return decode_register_2byte(raw, default=0)

    # Protocol: Active DPI stage index update (2026-10-15)
    def set_active_dpi_stage(self, stage_index: int) -> bool:
        """
        Set active DPI stage index (0 to 7).
        
        # Protocol: FlashAddr.ACTIVE_STAGE (0x04) update (2026-10-15)
        """
        if not (0 <= stage_index < MAX_DPI_STAGES):
            raise ValueError(f"Stage index must be between 0 and {MAX_DPI_STAGES - 1}.")
        data = encode_register_2byte(stage_index)
        return self.write_flash_register(FlashAddr.ACTIVE_STAGE, data)

    # Protocol: DPI stage count query (2026-10-15)
    def get_dpi_stage_count(self) -> int:
        """
        Get the number of active DPI stages (1-8).
        
        # Protocol: FlashAddr.STAGE_COUNT (0x02) query (2026-10-15)
        """
        raw = self.read_flash_register(FlashAddr.STAGE_COUNT, 2)
        return decode_register_2byte(raw, default=5)

    # Protocol: DPI stage count update (2026-10-15)
    def set_dpi_stage_count(self, count: int) -> bool:
        """
        Set the number of active DPI stages (1-8).
        
        # Protocol: FlashAddr.STAGE_COUNT (0x02) update (2026-10-15)
        """
        if not (1 <= count <= MAX_DPI_STAGES):
            raise ValueError(f"Stage count must be between 1 and {MAX_DPI_STAGES}.")
        data = encode_register_2byte(count)
        return self.write_flash_register(FlashAddr.STAGE_COUNT, data)

    # Protocol: DPI stages array query (2026-10-15)
    def get_dpi_stages(self, count: Optional[int] = None) -> List[int]:
        """
        Get list of DPI values for configured stages.
        
        # Protocol: FlashAddr.DPI_STAGES (0x0C) query (2026-10-15)
        """
        if count is None:
            count = self.get_dpi_stage_count()
        count = max(1, min(MAX_DPI_STAGES, count))

        stages = []
        for i in range(count):
            addr = FlashAddr.DPI_STAGES + (i * 4)
            raw = self.read_flash_register(addr, 4)
            stages.append(decode_dpi_stage(raw))
        return stages

    # Protocol: Single DPI stage update (2026-10-15)
    def set_dpi_stage(self, stage_index: int, dpi: int) -> bool:
        """
        Set DPI value for a specific stage index (0-7).
        
        # Protocol: FlashAddr.DPI_STAGES (0x0C) update (2026-10-15)
        """
        if not (0 <= stage_index < MAX_DPI_STAGES):
            raise ValueError(f"Stage index must be between 0 and {MAX_DPI_STAGES - 1}.")
        if not (DPI_MIN <= dpi <= DPI_MAX):
            raise ValueError(f"DPI must be between {DPI_MIN} and {DPI_MAX}.")

        addr = FlashAddr.DPI_STAGES + (stage_index * 4)
        data = encode_dpi_stage(dpi)
        return self.write_flash_register(addr, data)

    # Protocol: DPI stage color query (2026-10-15)
    def get_dpi_color(self, stage_index: int) -> Tuple[int, int, int]:
        """
        Get RGB LED color for a specific DPI stage index (0-7).
        
        # Protocol: FlashAddr.DPI_COLORS (0x2C) query (2026-10-15)
        """
        if not (0 <= stage_index < MAX_DPI_STAGES):
            raise ValueError(f"Stage index must be between 0 and {MAX_DPI_STAGES - 1}.")
        addr = FlashAddr.DPI_COLORS + (stage_index * 4)
        raw = self.read_flash_register(addr, 4)
        return decode_dpi_color(raw)

    # Protocol: DPI stage color update (2026-10-15)
    def set_dpi_color(self, stage_index: int, r: int, g: int, b: int) -> bool:
        """
        Set RGB LED color for a specific DPI stage index (0-7).
        
        # Protocol: FlashAddr.DPI_COLORS (0x2C) update (2026-10-15)
        """
        if not (0 <= stage_index < MAX_DPI_STAGES):
            raise ValueError(f"Stage index must be between 0 and {MAX_DPI_STAGES - 1}.")
        addr = FlashAddr.DPI_COLORS + (stage_index * 4)
        data = encode_dpi_color(r, g, b)
        return self.write_flash_register(addr, data)

    # Protocol: Read full configuration profile (2026-10-15)
    def read_settings(self) -> MouseSettings:
        """
        Read all current configuration parameters into a MouseSettings object.
        
        # Protocol: Read-Modify-Write integrity standard (2026-10-15)
        """
        polling_rate = self.get_polling_rate()
        debounce_ms = self.get_debounce()
        lod = self.get_lod()
        active_stage = self.get_active_dpi_stage()
        stage_count = self.get_dpi_stage_count()
        dpi_stages = self.get_dpi_stages(stage_count)

        return MouseSettings(
            polling_rate=polling_rate,
            debounce_ms=debounce_ms,
            lod=lod,
            active_stage=active_stage,
            stage_count=stage_count,
            dpi_stages=dpi_stages,
        )

    # Protocol: Apply full configuration profile (2026-10-15)
    def apply_settings(self, settings: MouseSettings) -> bool:
        """
        Apply a complete MouseSettings object to the device registers.
        
        # Protocol: Batch configuration application (2026-10-15)
        """
        self.set_polling_rate(settings.polling_rate)
        self.set_debounce(settings.debounce_ms)
        self.set_lod(settings.lod)
        self.set_dpi_stage_count(settings.stage_count)

        if settings.dpi_stages:
            for idx, dpi in enumerate(settings.dpi_stages[: settings.stage_count]):
                self.set_dpi_stage(idx, dpi)

        self.set_active_dpi_stage(settings.active_stage)
        return True

    def __enter__(self):
        if not self.is_connected:
            self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
