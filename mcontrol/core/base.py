"""Base abstractions and driver interface for extensible mouse support in M-Control."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from mcontrol.core.protocol import BatteryStatus, MouseSettings


@dataclass
class DeviceCapabilities:
    """Hardware capabilities and supported configuration ranges for a mouse model."""
    name: str
    min_dpi: int = 50
    max_dpi: int = 26000
    dpi_step: int = 50
    max_dpi_stages: int = 8
    supported_polling_rates: List[int] = field(default_factory=lambda: [125, 250, 500, 1000])
    supports_lod: bool = True
    supports_debounce: bool = True
    supports_battery_read: bool = True
    supports_profiles: bool = True


class BaseMouseDriver(ABC):
    """
    Abstract base class that all mouse drivers must implement.
    
    # Protocol: Driver abstraction interface (2026-10-29)
    Enables M-Control to support multiple mouse brands/models seamlessly in CLI and GUI.
    """

    @property
    @abstractmethod
    def capabilities(self) -> DeviceCapabilities:
        """Return the device hardware capabilities."""
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if the mouse or receiver is currently connected and open."""
        pass

    @property
    @abstractmethod
    def mode(self) -> Optional[str]:
        """Return the active connection mode ('wired', 'dongle', or None)."""
        pass

    @abstractmethod
    def connect(self, hid_device=None, mode: Optional[str] = None) -> bool:
        """
        Attempt to establish connection with the physical mouse or receiver.
        
        # Protocol: Base connection method (2026-10-29)
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close active HID handle."""
        pass

    @abstractmethod
    def read_battery(self) -> BatteryStatus:
        """
        Query live battery percentage, voltage, and charging status.
        
        # Protocol: Battery query contract (2026-10-29)
        """
        pass

    @abstractmethod
    def read_settings(self) -> MouseSettings:
        """
        Read complete onboard configuration from the mouse.
        
        # Protocol: Settings dump contract (2026-10-29)
        """
        pass

    @abstractmethod
    def set_dpi(self, dpi: int, stage_index: Optional[int] = None) -> bool:
        """
        Set DPI for the active stage or specified stage.
        
        # Protocol: DPI configuration contract (2026-10-29)
        """
        pass

    @abstractmethod
    def set_polling_rate(self, rate_hz: int) -> bool:
        """
        Set mouse polling rate in Hz (e.g. 125, 250, 500, 1000).
        
        # Protocol: Polling rate contract (2026-10-29)
        """
        pass

    @abstractmethod
    def set_lod(self, lod_mm: int) -> bool:
        """
        Set lift-off distance in millimeters (1 or 2).
        
        # Protocol: LOD contract (2026-10-29)
        """
        pass

    @abstractmethod
    def set_debounce(self, debounce_ms: int) -> bool:
        """
        Set button debounce delay in milliseconds.
        
        # Protocol: Debounce contract (2026-10-29)
        """
        pass

    def get_hardware_info(self) -> dict:
        """
        Return comprehensive hardware, sensor, MCU, and driver diagnostics.
        
        # Protocol: Hardware diagnostics contract (2026-10-29)
        """
        return {
            "model_name": self.capabilities.name,
            "connection_mode": self.mode or "Bilinmiyor",
            "driver_version": "M-Control Driver v0.2.0",
        }

    def set_dpi_configuration(
        self,
        stages: List[int],
        active_stage: int = 0,
        stage_count: Optional[int] = None,
    ) -> bool:
        """
        Set multiple DPI stages and active stage in a single transaction.
        
        # Protocol: DPI batch configuration contract (2026-10-29)
        """
        for idx, dpi in enumerate(stages):
            self.set_dpi(dpi, stage_index=idx)
        return True


