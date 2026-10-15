"""Unit tests for DeviceMonitor hotplug and unplug detection."""

import time
from unittest.mock import MagicMock, patch
import pytest

from mcontrol.core.constants import (
    DONGLE_PID,
    DONGLE_VID,
    WIRED_PID,
    WIRED_VID,
)
from mcontrol.core.monitor import DeviceEvent, DeviceMonitor


class MockUdevDevice:
    """Simulated pyudev.Device for offline testing."""

    def __init__(
        self,
        vendor_id: str,
        model_id: str,
        device_node: str = "/dev/hidraw1",
        action: str = "add",
        subsystem: str = "hidraw",
        parent=None,
    ):
        self._props = {
            "ID_VENDOR_ID": vendor_id,
            "ID_MODEL_ID": model_id,
        }
        self.attributes = {
            "idVendor": vendor_id,
            "idProduct": model_id,
        }
        self.device_node = device_node
        self.action = action
        self.subsystem = subsystem
        self._parent = parent

    def get(self, key, default=None):
        return self._props.get(key, default)

    def find_parent(self, subsystem, device_type=None):
        return self._parent


def test_identify_wired_device():
    dev = MockUdevDevice("04f3", "026e", "/dev/hidraw1")
    match = DeviceMonitor.identify_device(dev)
    assert match is not None
    mode, vid, pid = match
    assert mode == "wired"
    assert vid == WIRED_VID
    assert pid == WIRED_PID


def test_identify_dongle_device():
    dev = MockUdevDevice("32c2", "0018", "/dev/hidraw4")
    match = DeviceMonitor.identify_device(dev)
    assert match is not None
    mode, vid, pid = match
    assert mode == "dongle"
    assert vid == DONGLE_VID
    assert pid == DONGLE_PID


def test_identify_parent_usb_traversal():
    parent_usb = MockUdevDevice("04f3", "026e")
    child_hidraw = MockUdevDevice("", "", "/dev/hidraw1", parent=parent_usb)
    # Clear direct props on child
    child_hidraw._props.clear()

    match = DeviceMonitor.identify_device(child_hidraw)
    assert match is not None
    mode, vid, pid = match
    assert mode == "wired"


def test_identify_unknown_device():
    dev = MockUdevDevice("1234", "5678", "/dev/hidraw9")
    match = DeviceMonitor.identify_device(dev)
    assert match is None


def test_process_udev_event_connected_disconnected():
    connected_events = []
    disconnected_events = []

    monitor = DeviceMonitor(
        on_connected=lambda ev: connected_events.append(ev),
        on_disconnected=lambda ev: disconnected_events.append(ev),
    )

    # 1. Simulate wired mouse plug-in (add)
    wired_dev = MockUdevDevice("04f3", "026e", "/dev/hidraw1", action="add")
    ev1 = monitor.process_udev_event("add", wired_dev)
    assert ev1 is not None
    assert ev1.action == "add"
    assert ev1.mode == "wired"
    assert ev1.device_node == "/dev/hidraw1"
    assert len(connected_events) == 1
    assert len(disconnected_events) == 0

    # 2. Simulate dongle disconnect (remove)
    dongle_dev = MockUdevDevice("32c2", "0018", "/dev/hidraw4", action="remove")
    ev2 = monitor.process_udev_event("remove", dongle_dev)
    assert ev2 is not None
    assert ev2.action == "remove"
    assert ev2.mode == "dongle"
    assert len(connected_events) == 1
    assert len(disconnected_events) == 1

    # 3. Ignored unrelated action
    ev_ignore = monitor.process_udev_event("change", wired_dev)
    assert ev_ignore is None


def test_add_custom_callback():
    received = []
    monitor = DeviceMonitor()
    monitor.add_callback(lambda ev: received.append(ev))

    dev = MockUdevDevice("04f3", "026e", "/dev/hidraw2")
    monitor.process_udev_event("add", dev)

    assert len(received) == 1
    assert received[0].mode == "wired"


def test_callback_exception_safety():
    """Verify an exception in one callback does not break others."""
    executed = []

    def failing_callback(ev):
        raise RuntimeError("Crash in user callback!")

    def passing_callback(ev):
        executed.append(ev)

    monitor = DeviceMonitor()
    monitor.add_callback(failing_callback)
    monitor.add_callback(passing_callback)

    dev = MockUdevDevice("04f3", "026e")
    ev = monitor.process_udev_event("add", dev)

    assert ev is not None
    assert len(executed) == 1


def test_monitor_start_stop():
    """Test start and stop lifecycle of background thread with mocked pyudev."""
    monitor = DeviceMonitor()
    assert monitor.is_running is False

    mock_monitor = MagicMock()
    mock_monitor.poll.return_value = None

    with patch("pyudev.Context"), patch("pyudev.Monitor.from_netlink", return_value=mock_monitor):
        monitor.start()
        assert monitor.is_running is True

        # Idempotent start
        monitor.start()
        assert monitor.is_running is True

        monitor.stop()
        assert monitor.is_running is False

