"""Asynchronous USB hotplug and unplug monitor for Fevell Z1 using pyudev."""

from dataclasses import dataclass
import logging
import threading
from typing import Callable, List, Optional, Tuple

from mcontrol.core.constants import (
    DONGLE_PID,
    DONGLE_VID,
    WIRED_PID,
    WIRED_VID,
)

logger = logging.getLogger(__name__)


@dataclass
class DeviceEvent:
    """
    Represents a hardware connection or disconnection event.
    
    # Protocol: Hardware hotplug event representation (2026-10-15)
    """
    action: str                     # "add" or "remove"
    mode: str                       # "wired" or "dongle"
    vendor_id: int
    product_id: int
    device_node: Optional[str] = None # e.g. "/dev/hidraw1"


class DeviceMonitor:
    """
    Monitors Linux udev subsystem for Fevell Z1 mouse and dongle events.
    
    # Protocol: pyudev epoll-based hotplug monitor (2026-10-15)
    Filters hidraw / usb subsystems with zero idle CPU overhead.
    """

    def __init__(
        self,
        on_connected: Optional[Callable[[DeviceEvent], None]] = None,
        on_disconnected: Optional[Callable[[DeviceEvent], None]] = None,
    ):
        """
        Initialize the hotplug monitor.
        
        # Protocol: Monitor lifecycle initialization (2026-10-15)
        """
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._callbacks: List[Callable[[DeviceEvent], None]] = []

        if on_connected:
            self._callbacks.append(
                lambda ev: on_connected(ev) if ev.action == "add" else None
            )
        if on_disconnected:
            self._callbacks.append(
                lambda ev: on_disconnected(ev) if ev.action == "remove" else None
            )

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._observer = None

    @property
    def is_running(self) -> bool:
        """Check if the monitor thread is currently active."""
        return self._thread is not None and self._thread.is_alive()

    # Protocol: Callback listener registration (2026-10-15)
    def add_callback(self, callback: Callable[[DeviceEvent], None]):
        """Register a callback for all device events."""
        self._callbacks.append(callback)

    # Protocol: pyudev device identification and filtering (2026-10-15)
    @staticmethod
    def identify_device(device) -> Optional[Tuple[str, int, int]]:
        """
        Identify whether a udev device belongs to Fevell Z1.
        
        # Protocol: VID/PID matching for wired (04f3:026e) & dongle (32c2:0018) (2026-10-15)
        Returns (mode, vid, pid) if matched, None otherwise.
        """
        try:
            # Check properties on device itself or parent USB device
            vid_str = device.get("ID_VENDOR_ID")
            pid_str = device.get("ID_MODEL_ID")

            if not vid_str or not pid_str:
                # Walk up to the parent USB device
                parent = device.find_parent("usb", "usb_device")
                if parent:
                    vid_str = parent.get("ID_VENDOR_ID") or parent.attributes.get("idVendor")
                    pid_str = parent.get("ID_MODEL_ID") or parent.attributes.get("idProduct")

            if not vid_str or not pid_str:
                return None

            if isinstance(vid_str, bytes):
                vid_str = vid_str.decode("utf-8", errors="ignore")
            if isinstance(pid_str, bytes):
                pid_str = pid_str.decode("utf-8", errors="ignore")

            vid = int(str(vid_str), 16)
            pid = int(str(pid_str), 16)

            if vid == WIRED_VID and pid == WIRED_PID:
                return "wired", vid, pid
            elif vid == DONGLE_VID and pid == DONGLE_PID:
                return "dongle", vid, pid

            return None
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Failed to inspect udev device attributes: {e}")
            return None

    # Protocol: Process and dispatch device event (2026-10-15)
    def process_udev_event(self, action: str, device) -> Optional[DeviceEvent]:
        """
        Inspect a udev action/device and dispatch to callbacks if it matches Fevell Z1.
        
        # Protocol: Hotplug event dispatch (2026-10-15)
        """
        if action not in ("add", "remove"):
            return None

        match = self.identify_device(device)
        if not match:
            return None

        mode, vid, pid = match
        dev_node = device.device_node

        event = DeviceEvent(
            action=action,
            mode=mode,
            vendor_id=vid,
            product_id=pid,
            device_node=dev_node,
        )

        logger.info(f"Fevell Z1 event: action={action}, mode={mode}, node={dev_node}")

        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.error(f"Error in DeviceMonitor callback: {e}", exc_info=True)

        return event

    # Protocol: Background monitoring loop execution (2026-10-15)
    def _monitor_loop(self):
        """Thread worker loop utilizing pyudev netlink monitor."""
        try:
            import pyudev
        except ImportError:
            logger.error("pyudev is required for device monitoring.")
            return

        try:
            context = pyudev.Context()
            monitor = pyudev.Monitor.from_netlink(context)
            # Filter by hidraw subsystem (or usb)
            monitor.filter_by(subsystem="hidraw")
            monitor.start()

            while not self._stop_event.is_set():
                # Poll with 500ms timeout to allow responsive thread termination
                device = monitor.poll(timeout=0.5)
                if device is not None and not self._stop_event.is_set():
                    self.process_udev_event(device.action, device)
        except Exception as e:
            if not self._stop_event.is_set():
                logger.error(f"Unexpected error in udev monitor loop: {e}", exc_info=True)

    # Protocol: Start monitoring thread (2026-10-15)
    def start(self):
        """Start the background udev monitoring thread."""
        if self.is_running:
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="FevellDeviceMonitor",
            daemon=True,
        )
        self._thread.start()
        logger.info("Fevell Z1 hotplug monitor started.")

    # Protocol: Stop monitoring thread (2026-10-15)
    def stop(self, timeout: float = 2.0):
        """Stop the background udev monitoring thread cleanly."""
        if not self.is_running:
            return

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.info("Fevell Z1 hotplug monitor stopped.")
