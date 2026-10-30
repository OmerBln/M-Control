"""Common pytest fixtures for M-Control test suite."""

import pytest
from mcontrol.core.device import FevellDevice
from tests.mock_device import MockHIDDevice


@pytest.fixture
def mock_device():
    dev = MockHIDDevice(initial_battery=88, is_charging=False)
    dev.open(0x04F3, 0x026E)
    return dev


@pytest.fixture
def fevell_device(mock_device):
    device = FevellDevice()
    device.connect(hid_device=mock_device, mode="wired")
    return device

