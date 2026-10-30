"""Hardware constants, USB IDs, and protocol register definitions for Fevell Z1 (PAW3395 / BK3633)."""

from enum import IntEnum

# USB Device Identification
# Protocol: Confirmed via lsusb / udev and GamingMS.exe (2026-10-29)
# Primary targets: 04F3:026E (Wired), 04F3:026F (Wireless 2.4GHz), 04F3:026D (4K/8K Receiver)
FEVELL_VENDOR_ID = 0x04F3
FEVELL_WIRED_PID = 0x026E
FEVELL_DONGLE_PID = 0x026F
FEVELL_DONGLE_4K_PID = 0x026D

# Legacy VID/PID aliases used by DeviceMonitor and tests
WIRED_VID = FEVELL_VENDOR_ID
WIRED_PID = FEVELL_WIRED_PID
WIRED_PIDS = (FEVELL_WIRED_PID, FEVELL_DONGLE_PID, FEVELL_DONGLE_4K_PID)
DONGLE_VID = 0x32C2
DONGLE_PID = 0x0018

# Secondary / Fallback PAW3395 / Compx /CX52850 / BK3633 IDs
COMPX_VENDOR_ID = 0x3554
COMPX_WIRED_PID = 0xF58A
COMPX_DONGLE_PID = 0xF58B

FEVELL_SUPPORTED_PIDS = {
    FEVELL_WIRED_PID: "wired",
    FEVELL_DONGLE_PID: "dongle",
    FEVELL_DONGLE_4K_PID: "dongle_4k",
}

# HID Usage Page & Usage for Vendor Configuration Interface (Interface 1)
# Protocol: Confirmed via HID report descriptor & GamingMS.exe (2026-10-29)
VENDOR_USAGE_PAGE = 0xFF00
VENDOR_USAGE = 0x0001
VENDOR_INTERFACE_NUMBER = 1

# HID Report IDs & Packet Sizes
# Protocol: Reverse-engineered from Furylevel Z1 GamingMS.exe (2026-10-29)
# - Input Report 0x04 (32 bytes): Asynchronous status notification (DPI button press, battery, etc.)
# - Feature Report 0x05 (32 bytes): Device status & firmware handshake ("1010", online flag, receiver rate)
# - Feature Report 0x06 (32 bytes): Configuration command write & ACK read
# - Feature Report 0xBC (8 bytes): Device wake/status query
# - Feature Report 0xBD (136 bytes): Extended descriptor report
REPORT_ID_INPUT_STATUS = 0x04
REPORT_ID_STATUS = 0x05
REPORT_ID_FEATURE_CMD = 0x06
REPORT_ID_WAKE = 0xBC
REPORT_ID_STATE_READ = 0xBD

PACKET_LEN_INPUT_STATUS = 32
PACKET_LEN_FEATURE_CMD = 32
PACKET_LEN_WAKE = 8
PACKET_LEN_STATE_READ = 136

# Legacy constants preserved for unit test compatibility
REPORT_ID_CMD = 0x08
REPORT_ID_FEATURE_SHORT = 0xBC
REPORT_ID_FEATURE_LONG = 0xBD
PACKET_LEN_CMD = 16
PACKET_LEN_SHORT = 8
PACKET_LEN_LONG = 136
CHECKSUM_MAGIC = 0x55
MAX_PAYLOAD_LEN = 10


class FeatureCommand(IntEnum):
    """
    Command IDs used in 32-byte Feature Report 0x06 packets (byte[1]).
    # Protocol: Reverse-engineered from GamingMS.exe @ 0x00435870..0x00438146 (2026-10-29)
    """
    KEY_MAPPING = 0x01          # 6-button mapping table (6x3B descriptors in pkt[5..22])
    SET_DPI = 0x02              # Active stage, enable mask, 6x 16-bit LE DPI steps
    DPI_SETTINGS = 0x02         # Alias for SET_DPI
    SET_DPI_COLORS = 0x03       # 8x RGB color triples (24 bytes)
    DPI_COLORS = 0x03           # Alias for SET_DPI_COLORS
    SET_POLLING_RATE = 0x04     # Polling rate code (0x08=125, 0x04=250, 0x02=500, 0x01=1000)
    POLLING_RATE = 0x04         # Alias for SET_POLLING_RATE
    SET_LOD = 0x05              # Lift-off distance (0x01=1mm, 0x02=2mm)
    LOD = 0x05                  # Alias for SET_LOD
    SET_LIGHTING = 0x06         # RGB lighting effect configuration (25 bytes)
    SET_POWER_SLEEP = 0x07      # PowerDownTime + MoveLightingOnOffMode
    SET_SENSOR_ADVANCED = 0x08  # AngleSnap + MotionSync + RippleControl
    FACTORY_RESET = 0x0F        # Restore factory defaults (byte[5] = 0xFF) — DO NOT call on normal save!
    APPLY_PROFILE = 0x0F        # Legacy alias for FACTORY_RESET


class Command(IntEnum):
    """
    Legacy HID Command IDs preserved for backward test compatibility.
    # Protocol: Legacy BK3633/PAW3395 test protocol (2026-10-15)
    """
    ENCRYPTION_DATA = 0x01
    PC_DRIVER_STATUS = 0x02
    DEVICE_ONLINE = 0x03
    BATTERY_LEVEL = 0x04
    PAIRING = 0x05
    RESTORE_DEFAULT = 0x06
    WRITE_FLASH = 0x07
    READ_FLASH = 0x08
    CLEAR_SETTING = 0x09


class FlashAddr(IntEnum):
    """
    Simulated Flash/EEPROM offsets used by MockHIDDevice.
    # Protocol: Mock flash layout (2026-10-15)
    """
    POLLING_RATE = 0x0000
    STAGE_COUNT = 0x0002
    ACTIVE_STAGE = 0x0004
    LIFT_OFF = 0x0006
    DEBOUNCE = 0x000A
    DPI_STAGES = 0x000C
    DPI_COLORS = 0x002C
    BUTTON_MAP_BASE = 0x0060


# Polling Rate Encodings (Hz -> Protocol Byte in Cmd 0x04)
# Protocol: Reverse-engineered from GamingMS.exe @ 0x00435dc3..0x00435e2b (2026-10-29)
POLLING_RATE_MAP = {
    125: 0x08,
    250: 0x04,
    500: 0x02,
    1000: 0x01,
}

POLLING_RATE_REVERSE_MAP = {v: k for k, v in POLLING_RATE_MAP.items()}

# Input Report 0x04 byte[3] polling rate code (hardware byte -> Hz)
# Protocol: Reverse-engineered from GamingMS.exe @ 0x00432e85..0x00432ee1 (2026-10-29)
# Real hardware sends 0x08 (125Hz), 0x04 (250Hz), 0x02 (500Hz), 0x01 (1000Hz),
# 0x11 (2000Hz), 0x12 (4000Hz), 0x14 (8000Hz). Legacy mock indices 0 (125Hz) and 3 (1000Hz)
# do not collide with any hardware code and are kept for test compatibility.
INPUT_REPORT_POLLING_INDEX_MAP = {
    0x08: 125,
    0x04: 250,
    0x02: 500,
    0x01: 1000,
    0x11: 2000,
    0x12: 4000,
    0x14: 8000,
    0: 125,
    3: 1000,
}

# Lift-Off Distance (LOD) Constants
# Protocol: GamingMS.exe @ 0x00435eb0: 0x01 = 1mm, 0x02 = 2mm (2026-10-29)
LOD_1MM = 1
LOD_2MM = 2
VALID_LOD_VALUES = (LOD_1MM, LOD_2MM)

# DPI Limits & Step Granularity (PAW3395 Sensor)
# Protocol: GamingMS.exe @ 0x0064e720 lookup table (50..26000 DPI in 50 DPI steps) (2026-10-29)
DPI_MIN = 50
DPI_MAX = 26000
DPI_STEP = 50
MAX_DPI_STAGES = 6
DEFAULT_DPI_STAGES = [400, 800, 1600, 3200, 6400, 12000]
DEFAULT_DPI_STAGE_COLORS = [
    (255, 0, 0),      # 1. Kademe: Kırmızı
    (0, 255, 0),      # 2. Kademe: Yeşil
    (0, 0, 255),      # 3. Kademe: Mavi
    (255, 255, 0),    # 4. Kademe: Sarı
    (0, 255, 255),    # 5. Kademe: Camgöbeği (Cyan)
    (255, 0, 255),    # 6. Kademe: Mor (Magenta)
    (255, 255, 255),  # 7. Yedek: Beyaz
    (255, 255, 255),  # 8. Yedek: Beyaz (GamingMS.exe @ 0x0044418d)
]

# Debounce Time Limits (ms)
# Protocol: GamingMS.exe default0.psf KeyDebounce (0..30 ms, default 8 ms) (2026-10-29)
DEBOUNCE_MIN_MS = 0
DEBOUNCE_MAX_MS = 30
DEFAULT_DEBOUNCE_MS = 8

# Power Sleep Timeout (in 10s/tenths of min units as in default0.psf PowerDownTime=10 -> 1 min)
# Protocol: GamingMS.exe Cmd 0x07 @ 0x00436ae0 (2026-10-29)
SLEEP_TIMEOUT_OPTIONS = {
    1: 10,    # 1 Dakika
    3: 30,    # 3 Dakika
    5: 50,    # 5 Dakika
    10: 100,  # 10 Dakika
    15: 150,  # 15 Dakika
    30: 250,  # 30 Dakika
}

# 6-Button Action Definitions
# Protocol: GamingMS.exe Cmd 0x01 @ 0x00434e00..0x00435000 (2026-10-29)
BUTTON_ACTIONS = {
    "left_click": ("Sol Tık", (0x10, 0x01, 0x00)),
    "right_click": ("Sağ Tık", (0x10, 0x02, 0x00)),
    "middle_click": ("Orta Tık (Tekerlek)", (0x10, 0x04, 0x00)),
    "forward": ("İleri (Yan Tuş 1)", (0x10, 0x10, 0x00)),
    "back": ("Geri (Yan Tuş 2)", (0x10, 0x08, 0x00)),
    "dpi_loop": ("DPI Döngüsü", (0x40, 0x01, 0x00)),
    "dpi_plus": ("DPI Artır (+)", (0x40, 0x02, 0x00)),
    "dpi_minus": ("DPI Azalt (-)", (0x40, 0x03, 0x00)),
    "multimedia_play": ("Medya Oynat / Duraklat", (0x20, 0xCD, 0x00)),
    "multimedia_vol_up": ("Ses Artır (+)", (0x20, 0xE9, 0x00)),
    "multimedia_vol_down": ("Ses Azalt (-)", (0x20, 0xEA, 0x00)),
    "multimedia_mute": ("Sesi Kapat (Mute)", (0x20, 0xE2, 0x00)),
    "disabled": ("Devre Dışı", (0x00, 0x00, 0x00)),
}

DEFAULT_BUTTON_KEYS = [
    "left_click",    # 1. Sol Tık
    "right_click",   # 2. Sağ Tık
    "middle_click",  # 3. Orta Tık
    "forward",       # 4. İleri
    "back",          # 5. Geri
    "dpi_loop",      # 6. DPI Tuşu
]
