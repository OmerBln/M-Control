"""Packet builders, parsers, and checksum utilities for Fevell Z1 (PAW3395 / BK3633)."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from mcontrol.core.constants import (
    BUTTON_ACTIONS,
    CHECKSUM_MAGIC,
     Command,
    DEFAULT_BUTTON_KEYS,
    DEFAULT_DEBOUNCE_MS,
    DEFAULT_DPI_STAGE_COLORS,
    DEFAULT_DPI_STAGES,
    DPI_MAX,
    DPI_MIN,
    DPI_STEP,
    FeatureCommand,
    INPUT_REPORT_POLLING_INDEX_MAP,
    LOD_1MM,
    LOD_2MM,
    MAX_DPI_STAGES,
    MAX_PAYLOAD_LEN,
    PACKET_LEN_CMD,
    PACKET_LEN_FEATURE_CMD,
    PACKET_LEN_STATE_READ,
    POLLING_RATE_MAP,
    POLLING_RATE_REVERSE_MAP,
    REPORT_ID_CMD,
    REPORT_ID_FEATURE_CMD,
    REPORT_ID_INPUT_STATUS,
    REPORT_ID_STATE_READ,
    REPORT_ID_STATUS,
    SLEEP_TIMEOUT_OPTIONS,
    VALID_LOD_VALUES,
)


@dataclass
class DpiStage:
    """Represents a single DPI stage and its indicator color."""
    index: int
    dpi: int
    color: Tuple[int, int, int] = (255, 0, 0)


@dataclass
class BatteryStatus:
    """Represents mouse battery telemetry."""
    percentage: int
    is_charging: bool
    voltage_mv: int

    def __str__(self) -> str:
        state = "Şarj Oluyor" if self.is_charging else "Deşarj"
        return f"%{self.percentage} ({state}, {self.voltage_mv} mV)"


@dataclass
class MouseSettings:
    """Complete snapshot of Fevell Z1 mouse hardware settings."""
    polling_rate: int = 1000
    debounce_ms: int = DEFAULT_DEBOUNCE_MS
    lod: int = LOD_1MM
    active_stage: int = 1  # 0-based index (default 1 -> 800 DPI)
    stage_count: int = 4
    stage_enable_mask: int = 0x0F  # Bitmask for enabled stages (bits 0..5)
    dpi_stages: List[int] = field(default_factory=lambda: list(DEFAULT_DPI_STAGES))
    dpi_colors: List[Tuple[int, int, int]] = field(
        default_factory=lambda: list(DEFAULT_DPI_STAGE_COLORS[:MAX_DPI_STAGES])
    )
    angle_snap: bool = False
    motion_sync: bool = True
    ripple_control: bool = False
    sleep_timeout_min: int = 1
    move_light_off: bool = True
    lighting_mode: int = 1
    lighting_brightness: int = 3
    lighting_speed: int = 2
    button_mappings: List[str] = field(default_factory=lambda: list(DEFAULT_BUTTON_KEYS))

    @property
    def active_dpi(self) -> int:
        if 0 <= self.active_stage < len(self.dpi_stages):
            return self.dpi_stages[self.active_stage]
        return 800


def calculate_checksum(report_id: int, packet_without_checksum: bytes) -> int:
    """
    Calculate the 16-byte legacy packet checksum (Byte 15).
    
    # Protocol: Compx / BK3633 Legacy Checksum Algorithm (2026-10-15)
    """
    total = (report_id + sum(packet_without_checksum[:15])) & 0xFF
    return (CHECKSUM_MAGIC - total) & 0xFF


def verify_checksum(report_id: int, packet: bytes) -> bool:
    """
    Verify that a 16-byte packet satisfies the 0x55 checksum rule.
    
    # Protocol: Compx / BK3633 Legacy Checksum Verification (2026-10-15)
    """
    if len(packet) != PACKET_LEN_CMD:
        return False
    expected = calculate_checksum(report_id, packet[:15])
    return packet[15] == expected


def calculate_feature_checksum(packet: bytearray) -> int:
    """
    Calculate checksum for 32-byte Feature Report 0x06 packets.
    
    # Protocol: Reverse-engineered from GamingMS.exe @ 0x00436443..0x00436470 (2026-10-29)
    Checksum is stored at index 4 and equals the 8-bit sum of all 32 bytes
    (including Report ID 0x06 at index 0) with index 4 set to 0.
    """
    total = 0
    for idx, val in enumerate(packet[:PACKET_LEN_FEATURE_CMD]):
        if idx != 4:
            total += val
    return total & 0xFF


def build_feature_packet(
    cmd: int,
    seq: int,
    payload: bytes = b"",
    subcmd: int = 0x01,
) -> bytes:
    """
    Build a 32-byte Feature Report 0x06 command packet for Fevell Z1.
    
    # Protocol: Reverse-engineered from GamingMS.exe @ 0x00435be0..0x00437029 (2026-10-29)
    Layout:
      Byte 0:  0x06 (Report ID)
      Byte 1:  Command ID (FeatureCommand)
      Byte 2:  Sequence Counter (0..255)
      Byte 3:  Sub-command / Direction Flag (0x01 for commands 0x02..0x0F, 0x00 for 0x01)
      Byte 4:  8-bit Additive Checksum
      Byte 5..31: Command Payload (up to 27 bytes)
    """
    if len(payload) > 27:
        raise ValueError(f"Feature payload length {len(payload)} exceeds maximum of 27 bytes")

    packet = bytearray(PACKET_LEN_FEATURE_CMD)
    packet[0] = REPORT_ID_FEATURE_CMD
    packet[1] = cmd & 0xFF
    packet[2] = seq & 0xFF
    packet[3] = subcmd & 0xFF
    packet[4] = 0x00

    for i, b in enumerate(payload):
        packet[5 + i] = b & 0xFF

    packet[4] = calculate_feature_checksum(packet)
    return bytes(packet)


def encode_dpi_step(dpi: int) -> int:
    """
    Encode a DPI value (50..26000) into the 16-bit step value used in Feature Report 0x06 Cmd 0x02.
    
    # Protocol: Reverse-engineered from GamingMS.exe lookup table @ 0x0064e720 (2026-10-29)
    GamingMS.exe indexes `word_64e720[dpi // 50]`, where `word_64e720[1] = 0x0000` (50 DPI),
    `word_64e720[8] = 0x0007` (400 DPI), `word_64e720[16] = 0x000F` (800 DPI),
    `word_64e720[32] = 0x001F` (1600 DPI), `word_64e720[64] = 0x003F` (3200 DPI).
    Formula: `(clamped_dpi // 50) - 1`.
    """
    clamped = max(DPI_MIN, min(DPI_MAX, dpi))
    return max(0, (clamped // DPI_STEP) - 1)


def decode_dpi_step(raw_step: int) -> int:
    """
    Decode a 16-bit little-endian step value back to DPI.
    
    # Protocol: Reverse-engineered from GamingMS.exe @ 0x0064e720 (2026-10-29)
    Formula: `(raw_step + 1) * 50`.
    """
    if raw_step < 0:
        return 800
    dpi = (raw_step + 1) * DPI_STEP
    return max(DPI_MIN, min(DPI_MAX, dpi))


def build_feature_dpi_packet(
    seq: int,
    stages: List[int],
    active_stage: int = 1,
    enable_mask: Optional[int] = None,
    debounce_ms: int = DEFAULT_DEBOUNCE_MS,
) -> bytes:
    """
    Build Feature Report 0x06 Command 0x02 (DPI Configuration).
    
    # Protocol: Reverse-engineered from GamingMS.exe @ 0x00436314..0x00436470 (2026-10-29)
    Payload layout (starting at packet[5]):
      payload[0] (pkt[5]): Active stage index (0..5)
      payload[1] (pkt[6]): Enabled stages bitmask (e.g. 0x0F for 4 stages, 0x3F for 6 stages)
      payload[2..13] (pkt[7..18]): 6 DPI stages as 16-bit Little-Endian step values `(dpi // 50) - 1`
      payload[14..17] (pkt[19..22]): 0x00 reserved bytes (must be 0x00!)
    """
    stage_count = max(1, min(MAX_DPI_STAGES, len(stages)))
    if enable_mask is None:
        mask = (1 << stage_count) - 1
    else:
        mask = enable_mask & 0x3F
        if mask == 0:
            mask = 0x01

    padded_stages = list(stages[:MAX_DPI_STAGES])
    while len(padded_stages) < MAX_DPI_STAGES:
        fallback = DEFAULT_DPI_STAGES[len(padded_stages)] if len(padded_stages) < len(DEFAULT_DPI_STAGES) else 3200
        padded_stages.append(fallback)

    payload = bytearray(18)
    payload[0] = max(0, min(MAX_DPI_STAGES - 1, active_stage))
    payload[1] = mask

    for i in range(MAX_DPI_STAGES):
        step = encode_dpi_step(padded_stages[i])
        payload[2 + i * 2] = step & 0xFF
        payload[3 + i * 2] = (step >> 8) & 0xFF

    # Bytes payload[14..17] (pkt[19..22]) are explicitly zeroed in GamingMS.exe @ 0x00436418..0x0043643d
    return build_feature_packet(FeatureCommand.SET_DPI, seq, bytes(payload))


def build_feature_dpi_colors_packet(
    seq: int,
    colors: List[Tuple[int, int, int]],
) -> bytes:
    """
    Build Feature Report 0x06 Command 0x03 (DPI Stage RGB Colors).
    
    # Protocol: Reverse-engineered from GamingMS.exe @ 0x00436515..0x004366b5 (2026-10-29)
    Payload layout (starting at packet[5]):
      payload[0..23] (pkt[5..28]): 8 stages x 3 bytes [R, G, B]
    """
    payload = bytearray(24)
    for i in range(8):
        if i < len(colors):
            r, g, b = colors[i]
        else:
            r, g, b = DEFAULT_DPI_STAGE_COLORS[i]
        payload[i * 3] = r & 0xFF
        payload[i * 3 + 1] = g & 0xFF
        payload[i * 3 + 2] = b & 0xFF

    return build_feature_packet(FeatureCommand.SET_DPI_COLORS, seq, bytes(payload))


def build_feature_polling_packet(seq: int, rate_hz: int) -> bytes:
    """
    Build Feature Report 0x06 Command 0x04 (Polling Rate).
    
    # Protocol: Reverse-engineered from GamingMS.exe @ 0x00436764..0x00436877 (2026-10-29)
    Payload: [rate_code] where 1000Hz=0x01, 500Hz=0x02, 250Hz=0x04, 125Hz=0x08.
    """
    rate_code = POLLING_RATE_MAP.get(rate_hz, 0x01)
    return build_feature_packet(FeatureCommand.SET_POLLING_RATE, seq, bytes([rate_code]))


def build_feature_lod_packet(seq: int, lod_mm: int) -> bytes:
    """
    Build Feature Report 0x06 Command 0x05 (Lift-Off Distance).
    
    # Protocol: Reverse-engineered from GamingMS.exe @ 0x00436881..0x00436994 (2026-10-29)
    Payload: [0x01 for 1mm, 0x02 for 2mm]
    """
    lod_code = 0x01 if lod_mm == LOD_1MM else 0x02
    return build_feature_packet(FeatureCommand.SET_LOD, seq, bytes([lod_code]))


def build_feature_lighting_packet(
    seq: int,
    mode: int = 1,
    brightness: int = 3,
    speed: int = 2,
    color: Tuple[int, int, int] = (255, 0, 0),
) -> bytes:
    """
    Build Feature Report 0x06 Command 0x06 (Lighting Effect).
    
    # Protocol: Reverse-engineered from GamingMS.exe @ 0x00436258..0x004362b0 & 0x004369a4..0x00436ad3 (2026-10-29)
    Payload (25 bytes at pkt[5..29]):
      payload[0] (pkt[5]): 0x00
      payload[1] (pkt[6]): Lighting1ModeValue (0..9)
      payload[2] (pkt[7]): ((brightness_0_to_3 + 1) << 4) | ((speed_0_to_3 + 1) & 0x0F)
      payload[3] (pkt[8]): Lighting2OffOn (0x00)
      payload[4..24] (pkt[9..29]): 0x00
    """
    payload = bytearray(25)
    mode_clamped = max(0, min(9, mode))
    b_nib = max(1, min(4, brightness))
    s_nib = max(1, min(4, speed))

    payload[0] = 0x00
    payload[1] = mode_clamped
    payload[2] = (b_nib << 4) | s_nib
    payload[3] = 0x00

    return build_feature_packet(FeatureCommand.SET_LIGHTING, seq, bytes(payload))


def build_feature_power_sleep_packet(
    seq: int,
    sleep_timeout_min: int = 1,
    move_light_off: bool = True,
) -> bytes:
    """
    Build Feature Report 0x06 Command 0x07 (Power Down Timeout & Move Lighting Off Mode).
    
    # Protocol: Reverse-engineered from GamingMS.exe @ 0x00436ae0..0x00436d42 (2026-10-29)
    Payload:
      payload[0] (pkt[5]): PowerDownTime (in 6-second / 0.1-minute units: 10 = 1 min, 30 = 3 min, 50 = 5 min)
      payload[1] (pkt[6]): MoveLightingOnOffMode (1 = turn off LED on movement to save battery, 0 = keep LED on)
    """
    power_down_code = SLEEP_TIMEOUT_OPTIONS.get(
        sleep_timeout_min,
        max(10, min(250, sleep_timeout_min * 10)),
    )
    move_code = 0x01 if move_light_off else 0x00
    return build_feature_packet(
        FeatureCommand.SET_POWER_SLEEP,
        seq,
        bytes([power_down_code & 0xFF, move_code]),
    )


def build_feature_sensor_advanced_packet(
    seq: int,
    angle_snap: bool = False,
    motion_sync: bool = True,
    ripple_control: bool = False,
) -> bytes:
    """
    Build Feature Report 0x06 Command 0x08 (PAW3395 Advanced Sensor Features).
    
    # Protocol: Reverse-engineered from GamingMS.exe @ 0x00436da0..0x00437029 (2026-10-29)
    Payload:
      payload[0] (pkt[5]): AngleSnap (0 or 1)
      payload[1] (pkt[6]): MotionSync (0 or 1)
      payload[2] (pkt[7]): RippleControl (0 or 1)
    """
    payload = bytes([
        0x01 if angle_snap else 0x00,
        0x01 if motion_sync else 0x00,
        0x01 if ripple_control else 0x00,
    ])
    return build_feature_packet(FeatureCommand.SET_SENSOR_ADVANCED, seq, payload)


def build_feature_key_mapping_packet(
    seq: int,
    button_keys: Optional[List[str]] = None,
) -> bytes:
    """
    Build Feature Report 0x06 Command 0x01 (6-Button Key Mapping).
    
    # Protocol: Reverse-engineered from GamingMS.exe @ 0x004358b6..0x00435c60 (2026-10-29)
    Note: At 0x00435c1e, `mov %si, 0xd76d7(%edi)` sets pkt[3] = 0x01 (subcmd=0x01).
    At 0x00435c30, `movzbl 0x3fd(%eax), %ecx` copies starting from `0xd7ad6` (skipping the 2-byte
    `0x0C, 0x71` internal header at `0xd7ad4..0xd7ad5`), so `pkt[5..22]` contains the 6 x 3-byte
    button descriptors directly in hardware slot order:
    [Btn1(Left), Btn2(Right), Btn3(Middle), Btn5(Back), Btn4(Forward), Btn6(DPI)].
    """
    keys = list(button_keys) if button_keys else list(DEFAULT_BUTTON_KEYS)
    while len(keys) < 6:
        keys.append(DEFAULT_BUTTON_KEYS[len(keys)])

    # Hardware slot order in GamingMS.exe: [Btn1(Left), Btn2(Right), Btn3(Middle), Btn5(Back), Btn4(Forward), Btn6(DPI)]
    hw_order_indices = [0, 1, 2, 4, 3, 5]
    payload = bytearray(18)

    for slot_idx, btn_idx in enumerate(hw_order_indices):
        key_name = keys[btn_idx]
        _, action_bytes = BUTTON_ACTIONS.get(key_name, BUTTON_ACTIONS["left_click"])
        payload[slot_idx * 3] = action_bytes[0]
        payload[1 + slot_idx * 3] = action_bytes[1]
        payload[2 + slot_idx * 3] = action_bytes[2]

    return build_feature_packet(FeatureCommand.KEY_MAPPING, seq, bytes(payload), subcmd=0x01)


def build_feature_factory_reset_packet(seq: int) -> bytes:
    """
    Build Feature Report 0x06 Command 0x0F (Restore Factory Defaults).
    
    # Protocol: Reverse-engineered from GamingMS.exe @ 0x00437f60 & 0x0041b3c1 (2026-10-29)
    WARNING: This command resets the mouse hardware to factory default settings!
    Only send when the user explicitly requests a factory reset.
    """
    return build_feature_packet(FeatureCommand.FACTORY_RESET, seq, bytes([0xFF]))


def build_feature_apply_packet(seq: int, mode: int = 0xFF) -> bytes:
    """
    Legacy alias for `build_feature_factory_reset_packet`.
    
    # Protocol: GamingMS.exe @ 0x00437f60 (2026-10-29)
    """
    return build_feature_packet(FeatureCommand.FACTORY_RESET, seq, bytes([mode & 0xFF]))


def verify_feature_checksum(packet: bytes) -> bool:
    """
    Verify checksum at index 4 of a 32-byte Feature Report 0x06 packet.
    
    # Protocol: GamingMS.exe @ 0x00436443..0x00436470 (2026-10-29)
    """
    if len(packet) != PACKET_LEN_FEATURE_CMD:
        return False
    expected = calculate_feature_checksum(bytearray(packet))
    return packet[4] == expected


def build_feature_command(cmd: int, seq: int = 0, payload: bytes = b"") -> bytes:
    """
    Compatibility wrapper for `build_feature_packet`.
    # Protocol: GamingMS.exe Feature Report 0x06 (2026-10-29)
    """
    return build_feature_packet(cmd, seq, payload)


def build_dpi_command(
    active_stage: int,
    stages: List[int],
    stage_count: Optional[int] = None,
    seq: int = 0,
) -> bytes:
    """
    Compatibility wrapper for `build_feature_dpi_packet`.
    # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x02 (2026-10-29)
    """
    count = stage_count if stage_count is not None else len(stages)
    mask = (1 << max(1, min(MAX_DPI_STAGES, count))) - 1
    return build_feature_dpi_packet(seq=seq, stages=stages, active_stage=active_stage, enable_mask=mask)


def build_dpi_colors_command(colors: List[Tuple[int, int, int]], seq: int = 0) -> bytes:
    """
    Compatibility wrapper for `build_feature_dpi_colors_packet`.
    # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x03 (2026-10-29)
    """
    return build_feature_dpi_colors_packet(seq=seq, colors=colors)


def build_polling_rate_command(rate_hz: int, seq: int = 0) -> bytes:
    """
    Build Feature Report 0x06 Command 0x04 with validation.
    # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x04 (2026-10-29)
    """
    if rate_hz not in POLLING_RATE_MAP:
        raise ValueError(f"Unsupported polling rate: {rate_hz}")
    return build_feature_polling_packet(seq=seq, rate_hz=rate_hz)


def build_lod_command(lod_mm: int, seq: int = 0) -> bytes:
    """
    Build Feature Report 0x06 Command 0x05 with validation.
    # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x05 (2026-10-29)
    """
    if lod_mm not in VALID_LOD_VALUES:
        raise ValueError(f"Unsupported LOD: {lod_mm}")
    return build_feature_lod_packet(seq=seq, lod_mm=lod_mm)


def parse_feature_status_05(report: bytes) -> Tuple[bool, int, int]:
    """
    Parse 32-byte Feature Report 0x05 status response.
    
    # Protocol: GamingMS.exe @ 0x00438150..0x00438314 (2026-10-29)
    Returns (is_online, max_polling_rate_hz, battery_pct).
    """
    if len(report) < 8 or report[0] != REPORT_ID_STATUS:
        return False, 1000, 0
    is_online = bool(report[5])
    rate_code = report[6]
    rate_hz = 8000 if rate_code == 8 else (4000 if rate_code == 4 else 1000)
    battery_pct = max(0, min(100, report[7]))
    return is_online, rate_hz, battery_pct


def parse_input_status_report(report: bytes) -> Optional[Dict[str, int]]:
    """
    Parse 32-byte asynchronous Input Report 0x04 sent by the mouse when
    physical DPI button is pressed or battery/status changes.
    
    # Protocol: Reverse-engineered from GamingMS.exe reader thread @ 0x00432c30..0x004330c0 (2026-10-29)
    Layout when report[0] == 0x04:
      report[2]: CurrentDPILevelValue (0..5, 0-indexed stage)
      report[3]: PollingRate code (0x08=125Hz, 0x04=250Hz, 0x02=500Hz, 0x01=1000Hz)
      report[4]: Battery percentage (0..100)
      report[5]: Charging status (1=charging, 2=full charge 100%, 0=discharging)
      report[6]: LiftDetectionHeight (1=1mm, 2/0=2mm)
    """
    if not report or len(report) < 7:
        return None
    if report[0] != REPORT_ID_INPUT_STATUS:
        return None
    if not any(report[1:7]):
        return None

    active_stage = max(0, min(MAX_DPI_STAGES - 1, report[2]))
    polling_rate = INPUT_REPORT_POLLING_INDEX_MAP.get(report[3], 1000)
    battery_pct = max(0, min(100, report[4]))
    charge_state = report[5]
    if charge_state == 2:
        battery_pct = 100
        is_charging = 1
    elif charge_state == 1:
        is_charging = 1
    else:
        is_charging = 0
    lod_mm = LOD_1MM if report[6] == 1 else LOD_2MM

    return {
        "active_stage": active_stage,
        "polling_rate": polling_rate,
        "battery_pct": battery_pct,
        "is_charging": is_charging,
        "lod": lod_mm,
    }


def parse_state_report_bd(report: bytes) -> MouseSettings:
    """
    Parse 136-byte Feature Report 0xBD from Fevell Z1 hardware.
    
    # Protocol: Feature Report 0xBD State Parser (2026-10-29)
    """
    if len(report) < 32 or report[0] != REPORT_ID_STATE_READ:
        return MouseSettings()

    active_stage = report[2] if report[2] < MAX_DPI_STAGES else 1
    rate_code = report[4]
    polling_rate = POLLING_RATE_REVERSE_MAP.get(rate_code, 1000)
    lod_mm = LOD_2MM if report[5] == 2 else LOD_1MM
    debounce_ms = report[6] if 0 <= report[6] <= 30 else DEFAULT_DEBOUNCE_MS

    stages: List[int] = []
    for i in range(MAX_DPI_STAGES):
        offset = 7 + i * 2
        if offset + 1 < len(report):
            raw_step = report[offset] | (report[offset + 1] << 8)
            if raw_step > 0:
                stages.append(decode_dpi_step(raw_step))

    if not stages:
        stages = list(DEFAULT_DPI_STAGES)

    mask = report[3] & 0x3F
    stage_count = bin(mask).count("1") if mask else 4
    stage_count = max(1, min(len(stages), stage_count))

    return MouseSettings(
        polling_rate=polling_rate,
        debounce_ms=debounce_ms,
        lod=lod_mm,
        active_stage=min(active_stage, stage_count - 1),
        stage_count=stage_count,
        stage_enable_mask=mask if mask else 0x0F,
        dpi_stages=stages,
    )


def build_command_packet(
    cmd: Command,
    addr: int = 0x0000,
    length: int = 0x00,
    payload: bytes = b"",
    report_id: int = REPORT_ID_CMD,
) -> bytes:
    """
    Build a 16-byte legacy command packet.
    
    # Protocol: Compx / BK3633 16-byte HID Packet Structure (2026-10-15)
    """
    if len(payload) > MAX_PAYLOAD_LEN:
        raise ValueError(f"Payload length {len(payload)} exceeds max {MAX_PAYLOAD_LEN}")

    packet = bytearray(PACKET_LEN_CMD)
    packet[0] = int(cmd) & 0xFF
    packet[1] = 0x00
    packet[2] = (addr >> 8) & 0xFF
    packet[3] = addr & 0xFF
    packet[4] = length & 0xFF

    for i, b in enumerate(payload):
        packet[5 + i] = b

    packet[15] = calculate_checksum(report_id, bytes(packet[:15]))
    return bytes(packet)


def encode_register_2byte(value: int) -> bytes:
    """
    Encode a single byte register value into the [val, 0x55 - val] 2-byte format.
    
    # Protocol: BK3633 Flash Register Checksum Pair (2026-10-15)
    """
    val = value & 0xFF
    chk = (CHECKSUM_MAGIC - val) & 0xFF
    return bytes([val, chk])


def decode_register_2byte(data: bytes, offset: int = 0, default: int = 0) -> int:
    """
    Decode a 2-byte register pair [val, chk] at the given offset.
    
    # Protocol: BK3633 Flash Register Checksum Pair (2026-10-15)
    """
    if offset + 1 >= len(data):
        return default
    val = data[offset]
    chk = data[offset + 1]
    if ((val + chk) & 0xFF) == CHECKSUM_MAGIC:
        return val
    return default


def encode_dpi_stage(dpi: int) -> bytes:
    """
    Encode a DPI value (50 - 26000) into a 4-byte legacy flash entry.
    
    # Protocol: PAW3395 DPI Register Encoding (2026-10-15)
    """
    clamped = max(DPI_MIN, min(DPI_MAX, dpi))
    steps = max(1, clamped // DPI_STEP)
    hi = (steps >> 8) & 0xFF
    lo = steps & 0xFF
    chk = (CHECKSUM_MAGIC - ((hi + lo) & 0xFF)) & 0xFF
    return bytes([hi, lo, 0x00, chk])


def decode_dpi_stage(data: bytes, offset: int = 0) -> int:
    """
    Decode a 4-byte DPI stage entry from legacy flash memory.
    
    # Protocol: PAW3395 DPI Register Decoding (2026-10-15)
    """
    if offset + 3 >= len(data):
        return 800
    hi = data[offset]
    lo = data[offset + 1]
    steps = (hi << 8) | lo
    if steps == 0:
        return 800
    dpi = steps * DPI_STEP
    return max(DPI_MIN, min(DPI_MAX, dpi))


def encode_dpi_color(r: int, g: int, b: int) -> bytes:
    """
    Encode an RGB color tuple into a 4-byte flash entry [R, G, B, chk].
    
    # Protocol: BK3633 RGB Color Register Format (2026-10-15)
    """
    r_b, g_b, b_b = r & 0xFF, g & 0xFF, b & 0xFF
    chk = (CHECKSUM_MAGIC - ((r_b + g_b + b_b) & 0xFF)) & 0xFF
    return bytes([r_b, g_b, b_b, chk])


def decode_dpi_color(data: bytes, offset: int = 0) -> Tuple[int, int, int]:
    """
    Decode a 4-byte RGB color entry from flash memory.
    
    # Protocol: BK3633 RGB Color Register Format (2026-10-15)
    """
    if offset + 2 >= len(data):
        return (255, 0, 0)
    return (data[offset], data[offset + 1], data[offset + 2])


def parse_battery_response(payload: bytes) -> BatteryStatus:
    """
    Parse the 16-byte response from Command.BATTERY_LEVEL (0x04).
    
    # Protocol: BK3633 Battery Telemetry Response (2026-10-15)
    """
    if len(payload) < 9:
        return BatteryStatus(percentage=0, is_charging=False, voltage_mv=0)

    pct = max(0, min(100, payload[5]))
    charging = bool(payload[6])
    voltage = (payload[7] << 8) | payload[8]
    return BatteryStatus(percentage=pct, is_charging=charging, voltage_mv=voltage)
