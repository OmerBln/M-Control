"""Unit tests for BaseMouseDriver, capabilities, and device registry auto-discovery."""

import pytest
from mcontrol.core.base import BaseMouseDriver, DeviceCapabilities
from mcontrol.core.device import FevellDevice, discover_mouse, DRIVER_REGISTRY
from tests.mock_device import MockHIDDevice


def test_fevell_device_implements_base_driver(mock_device):
    dev = FevellDevice(hid_device=mock_device)
    assert isinstance(dev, BaseMouseDriver)
    
    caps = dev.capabilities
    assert isinstance(caps, DeviceCapabilities)
    assert caps.name == "Fevell Z1"
    assert caps.min_dpi == 50
    assert caps.max_dpi == 26000
    assert 1000 in caps.supported_polling_rates
    assert caps.supports_lod is True
    assert caps.supports_debounce is True


def test_fevell_set_dpi_default_stage(fevell_device):
    # Default active stage in mock is 1 (800 DPI)
    active = fevell_device.get_active_dpi_stage()
    assert active == 1
    # Update active stage DPI via generic set_dpi
    success = fevell_device.set_dpi(1600)
    assert success is True
    assert fevell_device.get_dpi_stages()[active] == 1600

    # Update specific stage DPI
    success = fevell_device.set_dpi(3200, stage_index=2)
    assert success is True
    assert fevell_device.get_dpi_stages()[2] == 3200


def test_discover_mouse_mock(monkeypatch, mock_device):
    # Test discover_mouse with mock
    class MockFevell(FevellDevice):
        def connect(self, hid_device=None, mode=None):
            return super().connect(hid_device=mock_device, mode="wired")

    monkeypatch.setattr("mcontrol.core.device.DRIVER_REGISTRY", [MockFevell])
    discovered = discover_mouse()
    assert discovered is not None
    assert isinstance(discovered, BaseMouseDriver)
    assert discovered.capabilities.name == "Fevell Z1"
