"""Hardware constants, USB identifiers, report IDs, and protocol commands for Fevell Z1."""

# Protocol: Fevell Z1 USB HID / Beken BK3633 reference design (2026-10-15)

# --- USB Hardware Identifiers ---
# Wired mode (Elan Microelectronics Corp. - Fevell Z1)
WIRED_VID = 0x04F3
WIRED_PID = 0x026E

# 2.4GHz Wireless Dongle mode (HS6209 Receiver)
DONGLE_VID = 0x32C2
DONGLE_PID = 0x0018

# Supported Device Pairs: (VID, PID, mode_name)
SUPPORTED_DEVICES = [
    (WIRED_VID, WIRED_PID, "wired"),
    (DONGLE_VID, DONGLE_PID, "dongle"),
]

# --- USB HID Report IDs ---
# Standard command exchange report ID
REPORT_ID_CMD = 0x08

# Vendor Feature Report IDs (Interface 1 on wired mode 04F3:026E)
REPORT_ID_FEATURE_SHORT = 0x05       # 32 bytes
REPORT_ID_FEATURE_STATUS = 0x06      # 32 bytes
REPORT_ID_FEATURE_CONTROL = 0xBC     # 8 bytes command packet
REPORT_ID_FEATURE_PROFILE_1 = 0xBD   # 136 bytes Profile 1 flash dump
REPORT_ID_FEATURE_PROFILE_2 = 0xBE   # 136 bytes Profile 2 flash dump
REPORT_ID_FEATURE_PROFILE_3 = 0xBF   # 136 bytes Profile 3 flash dump

# Dongle Vendor Report ID (Interface 2 on dongle 32C2:0018)
REPORT_ID_DONGLE_VENDOR = 0xB5       # 8 bytes wireless control

# --- Protocol Packet Sizes ---
PACKET_LEN_CMD = 16
MAX_PAYLOAD_LEN = 10
PROFILE_BLOCK_LEN = 136

# --- Protocol Commands ---
class Command:
    """Protocol command codes for 16-byte HID packets."""
    # Protocol: Compx / BK3633 protocol standard
    PC_DRIVER_STATUS = 0x02     # Heartbeat / Keep-alive to wake wireless RF link
    DEVICE_ONLINE = 0x03        # Check if mouse is awake and reachable
    BATTERY_LEVEL = 0x04        # Query battery status (percentage, charging, mV)
    WRITE_FLASH = 0x07          # Write configuration registers to onboard flash
    READ_FLASH = 0x08           # Read configuration registers from onboard flash
    STATUS_CHANGED = 0x0A       # Asynchronous notification from mouse (DPI button pressed, etc.)
    GET_CURRENT_CONFIG = 0x0E   # Query active profile index
    SET_CURRENT_CONFIG = 0x0F   # Switch active profile / apply settings
    READ_CID_MID = 0x10         # Read chip ID / manufacturer ID
    READ_VERSION = 0x12         # Read firmware version string
    SET_LONG_RANGE = 0x16       # Set long-distance RF mode
    GET_LONG_RANGE = 0x17       # Query long-distance RF mode

# --- Flash Register Memory Addresses (0x0000 - 0x00BF) ---
class FlashAddr:
    """Flash memory offsets for mouse configuration."""
    POLLING_RATE = 0x00         # 2 bytes: [val, check]
    STAGE_COUNT = 0x02          # 2 bytes: active DPI stage count
    ACTIVE_STAGE = 0x04         # 2 bytes: current active DPI stage index (0-based)
    LIFT_OFF = 0x0A             # 2 bytes: LOD (1 = 1mm, 2 = 2mm)
    DPI_STAGES = 0x0C           # 8 stages x 4 bytes
    DPI_COLORS = 0x2C           # 8 stages x 4 bytes RGB [R, G, B, check]
    BUTTON_MAPPINGS = 0x60      # Button configuration records
    DEBOUNCE = 0xA9             # 2 bytes: Debounce time in ms
    MOTION_SYNC = 0xAB          # 2 bytes: Motion Sync enable/disable
    ANGLE_SNAPPING = 0xAF       # 2 bytes: Angle snapping toggle
    RIPPLE_CONTROL = 0xB1       # 2 bytes: Ripple control toggle
    PEAK_PERFORMANCE = 0xB5     # 2 bytes: Sensor peak performance mode
    SENSOR_MODE = 0xB9          # 2 bytes: Sensor low power / high performance

# --- Sensor & Hardware Constraints (PixArt PAW3395) ---
DPI_MIN = 50
DPI_MAX = 26000
DPI_STEP = 50
MAX_DPI_STAGES = 8

# Polling rates in Hz mapped to protocol register values
POLLING_RATE_MAP = {
    1000: 1,
    500: 2,
    250: 4,
    125: 8,
}
POLLING_RATE_REVERSE_MAP = {v: k for k, v in POLLING_RATE_MAP.items()}

# Lift-Off Distance (LOD) levels in mm
LOD_1MM = 1
LOD_2MM = 2

# Debounce limits in milliseconds
DEBOUNCE_MIN_MS = 1
DEBOUNCE_MAX_MS = 20

# Default DPI stages for Fevell Z1
DEFAULT_DPI_STAGES = [
    (400, "#ff0000"),    # Red
    (800, "#0000ff"),    # Blue
    (1600, "#00ff00"),   # Green
    (3200, "#ffff00"),   # Yellow
    (6400, "#00ffff"),   # Cyan
]
