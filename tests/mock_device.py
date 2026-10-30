"""Mock HID device implementation for safe offline protocol testing without physical hardware."""

from typing import List
from mcontrol.core.constants import (
    Command,
    DEFAULT_BUTTON_KEYS,
    DEFAULT_DPI_STAGE_COLORS,
    DEFAULT_DPI_STAGES,
    FlashAddr,
    PACKET_LEN_CMD,
    REPORT_ID_CMD,
)
from mcontrol.core.protocol import (
    calculate_checksum,
    decode_dpi_step,
    encode_dpi_color,
    encode_dpi_stage,
    encode_register_2byte,
    verify_checksum,
)


class MockHIDDevice:
    """
    Simulated Fevell Z1 HID hardware device.
    
    # Protocol: Mock implementation for Hardware Safety Rule #1 (2026-10-29)
    Guarantees no invalid or dangerous packets ever touch the physical mouse.
    """

    def __init__(self, mode: str = "wired", initial_battery: int = 85, is_charging: bool = False):
        self.mode = mode
        self.is_open = False
        self.battery_pct = initial_battery
        self.is_charging = is_charging
        self.voltage_mv = 3980

        # Simulated on-board flash memory (6912 bytes = 0x1B00)
        self.flash = bytearray(0x1B00)
        self.angle_snap = False
        self.motion_sync = True
        self.ripple_control = False
        self.sleep_timeout_code = 10
        self.move_light_off = True
        self.lighting_mode = 1
        self.button_keys = list(DEFAULT_BUTTON_KEYS)
        self._init_default_flash()

        # Packet history for assertions in tests
        self.sent_packets: List[bytes] = []
        self.pending_responses: List[bytes] = []

    def _init_default_flash(self):
        """Populate default flash memory registers."""
        # Polling rate: 1000Hz (val = 1)
        self.flash[FlashAddr.POLLING_RATE : FlashAddr.POLLING_RATE + 2] = encode_register_2byte(1)
        # Stage count: 5
        self.flash[FlashAddr.STAGE_COUNT : FlashAddr.STAGE_COUNT + 2] = encode_register_2byte(5)
        # Active stage: 1 (second stage, 800 DPI)
        self.flash[FlashAddr.ACTIVE_STAGE : FlashAddr.ACTIVE_STAGE + 2] = encode_register_2byte(1)
        # LOD: 1mm
        self.flash[FlashAddr.LIFT_OFF : FlashAddr.LIFT_OFF + 2] = encode_register_2byte(1)
        # Debounce: 4ms
        self.flash[FlashAddr.DEBOUNCE : FlashAddr.DEBOUNCE + 2] = encode_register_2byte(4)

        # Default DPI stages: 400, 800, 1600, 3200, 6400, 12000
        default_dpis = [400, 800, 1600, 3200, 6400, 12000, 800, 800]
        for i, dpi in enumerate(default_dpis):
            offset = FlashAddr.DPI_STAGES + (i * 4)
            self.flash[offset : offset + 4] = encode_dpi_stage(dpi)

        # Default DPI colors
        for i, (r, g, b) in enumerate(DEFAULT_DPI_STAGE_COLORS):
            offset = FlashAddr.DPI_COLORS + (i * 4)
            self.flash[offset : offset + 4] = encode_dpi_color(r, g, b)

    def open(self, vid: int, pid: int):
        self.is_open = True

    def close(self):
        self.is_open = False

    def write(self, data: bytes) -> int:
        """Simulate writing an output report to the device."""
        if not self.is_open:
            raise IOError("Device not open")

        self.sent_packets.append(bytes(data))
        report_id = data[0]
        packet = data[1:] if len(data) == PACKET_LEN_CMD + 1 else data

        if not verify_checksum(report_id, packet):
            raise ValueError(f"MockDevice: Invalid checksum in packet: {packet.hex()}")

        cmd = packet[0]
        self._process_command(report_id, cmd, packet)
        return len(data)

    def read(self, max_length: int, timeout_ms: int = 1000) -> List[int]:
        """Simulate reading an input report from the device."""
        if not self.is_open:
            raise IOError("Device not open")
        if self.pending_responses:
            resp = self.pending_responses.pop(0)
            return list(resp[:max_length])
        return []

    def queue_input_status_report(
        self,
        active_stage: int = 1,
        polling_rate_idx: int = 3,
        battery_pct: int = 85,
        is_charging: bool = False,
        lod_flag: int = 1,
    ) -> None:
        """
        Queue a simulated 32-byte Input Report 0x04 (e.g. physical DPI button press).
        
        # Protocol: GamingMS.exe Input Report 0x04 @ 0x00432c30 (2026-10-29)
        """
        pkt = bytearray(32)
        pkt[0] = 0x04
        pkt[1] = 0x04
        pkt[2] = active_stage & 0xFF
        pkt[3] = polling_rate_idx & 0xFF
        pkt[4] = battery_pct & 0xFF
        pkt[5] = 1 if is_charging else 0
        pkt[6] = lod_flag & 0xFF
        self.pending_responses.append(bytes(pkt))

    def send_feature_report(self, data: bytes) -> int:
        """
        Simulate sending a feature report.
        
        # Protocol: GamingMS.exe / Fevell Z1 Feature Protocol (2026-10-29)
        Handles Report 0xBC (wake) and Report 0x06 (32-byte commands).
        """
        if not self.is_open:
            raise IOError("Device not open")

        data_bytes = bytes(data)
        self.sent_packets.append(data_bytes)
        report_id = data_bytes[0]

        if report_id == 0xBC:
            return len(data)

        if report_id == 0x06:
            cmd = data_bytes[1]
            if cmd == 0x02:  # DPI settings (6 stages, 0-based step encoding)
                active_stage = data_bytes[5]
                self.flash[FlashAddr.ACTIVE_STAGE : FlashAddr.ACTIVE_STAGE + 2] = encode_register_2byte(active_stage)
                mask = data_bytes[6] & 0x3F
                stage_count = bin(mask).count("1") if mask else 1
                self.flash[FlashAddr.STAGE_COUNT : FlashAddr.STAGE_COUNT + 2] = encode_register_2byte(stage_count)
                for i in range(6):
                    raw_step = data_bytes[7 + i * 2] | (data_bytes[8 + i * 2] << 8)
                    dpi = decode_dpi_step(raw_step)
                    offset = FlashAddr.DPI_STAGES + (i * 4)
                    self.flash[offset : offset + 4] = encode_dpi_stage(dpi)
            elif cmd == 0x03:  # DPI stage colors (8 x RGB)
                for i in range(8):
                    r = data_bytes[5 + i * 3]
                    g = data_bytes[6 + i * 3]
                    b = data_bytes[7 + i * 3]
                    offset = FlashAddr.DPI_COLORS + (i * 4)
                    self.flash[offset : offset + 4] = encode_dpi_color(r, g, b)
            elif cmd == 0x04:  # Polling rate
                rate_code = data_bytes[5]
                self.flash[FlashAddr.POLLING_RATE : FlashAddr.POLLING_RATE + 2] = encode_register_2byte(rate_code)
            elif cmd == 0x05:  # LOD
                lod_val = data_bytes[5]
                self.flash[FlashAddr.LIFT_OFF : FlashAddr.LIFT_OFF + 2] = encode_register_2byte(lod_val)
            elif cmd == 0x06:  # Lighting
                self.lighting_mode = data_bytes[6]
            elif cmd == 0x07:  # Power sleep & move light off
                self.sleep_timeout_code = data_bytes[5]
                self.move_light_off = bool(data_bytes[6])
            elif cmd == 0x08:  # Sensor advanced
                self.angle_snap = bool(data_bytes[5])
                self.motion_sync = bool(data_bytes[6])
                self.ripple_control = bool(data_bytes[7])
            elif cmd == 0x0F:  # Factory reset
                self._init_default_flash()
            return len(data)

        return self.write(data_bytes)

    def get_feature_report(self, report_id: int, length: int) -> bytes:
        """
        Simulate getting a feature report.
        
        # Protocol: GamingMS.exe / Fevell Z1 Feature Protocol (2026-10-29)
        """
        buf = bytearray(length)
        buf[0] = report_id

        if report_id == 0x05:
            buf[1:5] = b"1010"
            buf[5] = 0x01 if self.mode in ("wired", "dongle", "dongle_4k") else 0x00
            buf[6] = 0x01  # 1000Hz receiver capability
            buf[7] = self.battery_pct
            return bytes(buf)
        elif report_id == 0x06:
            buf[1] = 0x01  # Command ACK
            return bytes(buf)
        elif report_id == 0xBC:
            buf[1] = 0x01
            return bytes(buf)
        elif report_id == 0xBD:
            buf[1] = 0x88
            return bytes(buf)

        return bytes(buf)

    def _process_command(self, report_id: int, cmd: int, packet: bytes):
        """Build simulated hardware response for legacy 16-byte protocol."""
        resp = bytearray(PACKET_LEN_CMD)
        resp[0] = cmd

        if cmd == Command.DEVICE_ONLINE:
            resp[5] = 0x01
        elif cmd == Command.BATTERY_LEVEL:
            resp[5] = self.battery_pct
            resp[6] = 1 if self.is_charging else 0
            resp[7] = (self.voltage_mv >> 8) & 0xFF
            resp[8] = self.voltage_mv & 0xFF
        elif cmd == Command.READ_FLASH:
            addr = (packet[2] << 8) | packet[3]
            length = min(10, packet[4])
            resp[2] = packet[2]
            resp[3] = packet[3]
            resp[4] = length
            resp[5 : 5 + length] = self.flash[addr : addr + length]
        elif cmd == Command.WRITE_FLASH:
            addr = (packet[2] << 8) | packet[3]
            length = min(10, packet[4])
            self.flash[addr : addr + length] = packet[5 : 5 + length]
            resp[2] = packet[2]
            resp[3] = packet[3]
            resp[4] = length
        elif cmd == Command.PC_DRIVER_STATUS:
            resp[5] = 0x01

        resp[15] = calculate_checksum(report_id, bytes(resp))
        self.pending_responses.append(bytes([report_id] + list(resp)))
