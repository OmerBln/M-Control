"""Protocol packet encoding, decoding, checksum verification, and register packing."""

from dataclasses import dataclass
from typing import List, Optional, Tuple
from mcontrol.core.constants import (
    Command,
    DPI_MAX,
    DPI_MIN,
    DPI_STEP,
    MAX_DPI_STAGES,
    MAX_PAYLOAD_LEN,
    PACKET_LEN_CMD,
    POLLING_RATE_MAP,
    POLLING_RATE_REVERSE_MAP,
    REPORT_ID_CMD,
)


@dataclass
class BatteryStatus:
    """Represents the battery and charging state of the mouse."""
    percentage: int
    is_charging: bool
    voltage_mv: int

    def __str__(self) -> str:
        state = "Şarj Oluyor" if self.is_charging else "Pilde"
        return f"%{self.percentage} ({self.voltage_mv} mV) - {state}"


@dataclass
class DpiStage:
    """Represents a single DPI stage configuration."""
    dpi: int
    color_rgb: Tuple[int, int, int]  # (R, G, B) 0-255


def calculate_checksum(report_id: int, packet_bytes: bytes) -> int:
    """
    Calculate the protocol checksum byte.
    
    # Protocol: BK3633/Compx standard (2026-10-15)
    Formula: The sum of report ID plus all 16 packet bytes must equal 0x55 (mod 256).
    Therefore: checksum = (0x55 - (report_id + sum(packet[0..14]))) & 0xFF
    """
    total = report_id + sum(packet_bytes[:15])
    return (0x55 - total) & 0xFF


def verify_checksum(report_id: int, packet_bytes: bytes) -> bool:
    """
    Verify if a 16-byte response packet has a valid checksum.
    
    # Protocol: BK3633/Compx standard (2026-10-15)
    """
    if len(packet_bytes) != PACKET_LEN_CMD:
        return False
    total = report_id + sum(packet_bytes)
    return (total & 0xFF) == 0x55


def build_command_packet(
    cmd: int,
    addr: int = 0,
    length: int = 0,
    payload: Optional[bytes] = None,
    report_id: int = REPORT_ID_CMD,
) -> bytes:
    """
    Build a 16-byte command packet with correct checksum.
    
    # Protocol: BK3633/Compx standard (2026-10-15)
    Layout: [cmd, sub_cmd/0, addr_hi, addr_lo, length, payload[10], checksum]
    """
    if payload is None:
        payload = b""
    if len(payload) > MAX_PAYLOAD_LEN:
        raise ValueError(f"Payload length cannot exceed {MAX_PAYLOAD_LEN} bytes.")

    packet = bytearray(PACKET_LEN_CMD)
    packet[0] = cmd & 0xFF
    packet[1] = 0x00  # Sub-command or zero
    packet[2] = (addr >> 8) & 0xFF  # Addr high
    packet[3] = addr & 0xFF         # Addr low
    packet[4] = length & 0xFF

    # Copy payload up to MAX_PAYLOAD_LEN
    for i, b in enumerate(payload):
        packet[5 + i] = b & 0xFF

    # Calculate checksum and place at index 15
    packet[15] = calculate_checksum(report_id, bytes(packet))
    return bytes(packet)


def parse_battery_response(packet: bytes) -> BatteryStatus:
    """
    Parse a battery query response packet (Command 0x04).
    
    # Protocol: Compx battery response structure (2026-10-15)
    Response payload at index 5: [percentage, charging_flag, mv_hi, mv_lo]
    """
    if len(packet) < PACKET_LEN_CMD:
        raise ValueError("Packet too short to parse battery status.")

    percentage = max(0, min(100, packet[5]))
    is_charging = bool(packet[6] & 0x01)
    voltage_mv = (packet[7] << 8) | packet[8]

    # Sanity check voltage (PAW3395 Li-ion battery operates between 3.0V and 4.2V)
    if voltage_mv < 2500 or voltage_mv > 4500:
        voltage_mv = 3700  # Default nominal 3.7V if raw value is uncalibrated

    return BatteryStatus(
        percentage=percentage,
        is_charging=is_charging,
        voltage_mv=voltage_mv,
    )


def encode_register_2byte(value: int) -> bytes:
    """
    Encode a single register into 2 bytes: [value, 0x55 - value].
    
    # Protocol: Compx register checksum rule (2026-10-15)
    """
    val = value & 0xFF
    chk = (0x55 - val) & 0xFF
    return bytes([val, chk])


def decode_register_2byte(data: bytes, offset: int = 0, default: int = 0) -> int:
    """
    Decode a 2-byte register with integrity verification.
    
    # Protocol: Compx register checksum rule (2026-10-15)
    """
    if len(data) < offset + 2:
        return default
    val = data[offset]
    expected_chk = (0x55 - val) & 0xFF
    if data[offset + 1] == expected_chk:
        return val
    return default


def encode_dpi_stage(dpi: int) -> bytes:
    """
    Encode a DPI value into a 4-byte record: [raw_hi, raw_lo, 0x00, checksum].
    DPI must be within [50, 26000] and multiple of 50.
    
    # Protocol: PixArt PAW3395 register mapping (2026-10-15)
    """
    clamped_dpi = max(DPI_MIN, min(DPI_MAX, dpi))
    # DPI step quantization
    clamped_dpi = (clamped_dpi // DPI_STEP) * DPI_STEP

    # Protocol register value is dpi / 50 (or raw value depending on firmware)
    raw_val = clamped_dpi // 50
    b0 = (raw_val >> 8) & 0xFF
    b1 = raw_val & 0xFF
    b2 = 0x00
    chk = (0x55 - (b0 + b1 + b2)) & 0xFF
    return bytes([b0, b1, b2, chk])


def decode_dpi_stage(data: bytes, offset: int = 0) -> int:
    """
    Decode a 4-byte DPI stage record into DPI value.
    
    # Protocol: PixArt PAW3395 register mapping (2026-10-15)
    """
    if len(data) < offset + 4:
        return 800
    b0 = data[offset]
    b1 = data[offset + 1]
    b2 = data[offset + 2]
    expected_chk = (0x55 - (b0 + b1 + b2)) & 0xFF
    if data[offset + 3] != expected_chk:
        return 800  # Fallback safe default DPI
    raw_val = (b0 << 8) | b1
    return max(DPI_MIN, min(DPI_MAX, raw_val * 50))
