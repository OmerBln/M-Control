"""Mock HID device implementation for safe offline protocol testing without physical hardware."""

from typing import List, Optional
from mcontrol.core.constants import (
    Command,
    FlashAddr,
    PACKET_LEN_CMD,
    POLLING_RATE_MAP,
    REPORT_ID_CMD,
    REPORT_ID_FEATURE_SHORT,
)
from mcontrol.core.protocol import (
    calculate_checksum,
    encode_dpi_stage,
    encode_register_2byte,
    verify_checksum,
)


class MockHIDDevice:
    """
    Simulated Fevell Z1 HID hardware device.
    
    # Protocol: Mock implementation for Hardware Safety Rule #1 (2026-10-15)
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

        # Default DPI stages: 400, 800, 1600, 3200, 6400
        default_dpis = [400, 800, 1600, 3200, 6400, 800, 800, 800]
        for i, dpi in enumerate(default_dpis):
            offset = FlashAddr.DPI_STAGES + (i * 4)
            self.flash[offset : offset + 4] = encode_dpi_stage(dpi)

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

        # Verify packet integrity
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

    def send_feature_report(self, data: bytes) -> int:
        """Simulate sending a feature report."""
        return self.write(data)

    def get_feature_report(self, report_id: int, length: int) -> bytes:
        """Simulate getting a feature report."""
        if report_id == REPORT_ID_FEATURE_SHORT:
            buf = bytearray(length)
            buf[0] = report_id
            buf[1] = self.battery_pct
            return bytes(buf)
        return bytes([report_id] + [0] * (length - 1))

    def _process_command(self, report_id: int, cmd: int, packet: bytes):
        """Build simulated hardware response."""
        resp = bytearray(PACKET_LEN_CMD)
        resp[0] = cmd  # Echo back command

        if cmd == Command.DEVICE_ONLINE:
            resp[5] = 0x01  # Device is reachable and connected
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
            resp[5] = 0x01  # Heartbeat acknowledged

        # Calculate checksum for response
        resp[15] = calculate_checksum(report_id, bytes(resp))
        # Prepend report ID in response
        self.pending_responses.append(bytes([report_id] + list(resp)))
