"""Core hardware communication and protocol drivers."""

from mcontrol.core.base import (
    BaseMouseDriver,
    DeviceCapabilities,
)
from mcontrol.core.constants import (
    Command,
    FlashAddr,
    WIRED_VID,
    WIRED_PID,
    DONGLE_VID,
    DONGLE_PID,
)
from mcontrol.core.device import (
    DeviceCommunicationError,
    DeviceError,
    DeviceNotFoundError,
    FevellDevice,
    discover_mouse,
)
from mcontrol.core.monitor import (
    DeviceEvent,
    DeviceMonitor,
)
from mcontrol.core.protocol import (
    BatteryStatus,
    DpiStage,
    MouseSettings,
)

__all__ = [
    "BaseMouseDriver",
    "DeviceCapabilities",
    "Command",
    "FlashAddr",
    "WIRED_VID",
    "WIRED_PID",
    "DONGLE_VID",
    "DONGLE_PID",
    "FevellDevice",
    "discover_mouse",
    "DeviceError",
    "DeviceNotFoundError",
    "DeviceCommunicationError",
    "DeviceMonitor",
    "DeviceEvent",
    "BatteryStatus",
    "DpiStage",
    "MouseSettings",
]
