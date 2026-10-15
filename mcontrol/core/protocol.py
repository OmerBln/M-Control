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


@dataclass
class MouseSettings:
    """
    Represents complete configuration state read from or written to the mouse.
    
    # Protocol: Fevell Z1 register configuration model (2026-10-15)
    """
    polling_rate: int = 1000            # Hz (125, 250, 500, 1000)
    debounce_ms: int = 4                # ms (1-20)
    lod: int = 1                        # 1 = 1mm, 2 = 2mm
    active_stage: int = 0               # 0-indexed active DPI stage
    stage_count: int = 5                # Number of configured stages (1-8)
    dpi_stages: Optional[List[int]] = None # List of DPI values per stage
    motion_sync: bool = True
    angle_snapping: bool = False
    ripple_control: bool = False

    def __post_init__(self):
        if self.dpi_stages is None:
            self.dpi_stages = [400, 800, 1600, 3200, 6400]



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


def encode_dpi_color(r: int, g: int, b: int) -> bytes:
    """
    Encode an RGB color into a 4-byte record: [r, g, b, checksum].
    
    # Protocol: BK3633/Compx DPI LED color record (2026-10-15)
    """
    r_val = max(0, min(255, r))
    g_val = max(0, min(255, g))
    b_val = max(0, min(255, b))
    chk = (0x55 - (r_val + g_val + b_val)) & 0xFF
    return bytes([r_val, g_val, b_val, chk])


def decode_dpi_color(data: bytes, offset: int = 0) -> Tuple[int, int, int]:
    """
    Decode a 4-byte DPI LED color record into RGB tuple.
    
    # Protocol: BK3633/Compx DPI LED color record (2026-10-15)
    """
    if len(data) < offset + 4:
        return (255, 0, 0)
    r = data[offset]
    g = data[offset + 1]
    b = data[offset + 2]
    expected_chk = (0x55 - (r + g + b)) & 0xFF
    if data[offset + 3] != expected_chk:
        return (255, 0, 0)
    return (r, g, b)

