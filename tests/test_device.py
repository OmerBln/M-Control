"""Unit tests for FevellDevice hardware controller."""

import pytest
from mcontrol.core.constants import (
    DPI_MAX,
    DPI_MIN,
    DEBOUNCE_MAX_MS,
    DEBOUNCE_MIN_MS,
    LOD_1MM,
    LOD_2MM,
)
from mcontrol.core.device import (
    DeviceCommunicationError,
    DeviceError,
    FevellDevice,
)
from mcontrol.core.protocol import MouseSettings
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


def test_device_connection_lifecycle(mock_device):
    dev = FevellDevice()
    assert dev.is_connected is False
    assert dev.mode is None

    assert dev.connect(hid_device=mock_device, mode="wired") is True
    assert dev.is_connected is True
    assert dev.mode == "wired"

    dev.disconnect()
    assert dev.is_connected is False
    assert dev.mode is None


def test_device_disconnected_error():
    dev = FevellDevice()
    with pytest.raises(DeviceError):
        dev.read_battery()


def test_read_battery(fevell_device, mock_device):
    mock_device.battery_pct = 75
    mock_device.is_charging = True
    mock_device.voltage_mv = 4050

    status = fevell_device.read_battery()
    assert status.percentage == 75
    assert status.is_charging is True
    assert status.voltage_mv == 4050


def test_heartbeat_and_online(fevell_device):
    assert fevell_device.send_heartbeat() is True
    assert fevell_device.is_device_online() is True


def test_polling_rate(fevell_device):
    # Default is 1000 Hz
    assert fevell_device.get_polling_rate() == 1000

    for rate in (125, 250, 500, 1000):
        assert fevell_device.set_polling_rate(rate) is True
        assert fevell_device.get_polling_rate() == rate

    with pytest.raises(ValueError):
        fevell_device.set_polling_rate(800)


def test_debounce_time(fevell_device):
    # Default is 4 ms
    assert fevell_device.get_debounce() == 4

    assert fevell_device.set_debounce(8) is True
    assert fevell_device.get_debounce() == 8

    with pytest.raises(ValueError):
        fevell_device.set_debounce(DEBOUNCE_MIN_MS - 1)

    with pytest.raises(ValueError):
        fevell_device.set_debounce(DEBOUNCE_MAX_MS + 1)


def test_lift_off_distance(fevell_device):
    # Default is 1 mm
    assert fevell_device.get_lod() == LOD_1MM

    assert fevell_device.set_lod(LOD_2MM) is True
    assert fevell_device.get_lod() == LOD_2MM

    with pytest.raises(ValueError):
        fevell_device.set_lod(3)


def test_active_dpi_stage(fevell_device):
    # Default is index 1
    assert fevell_device.get_active_dpi_stage() == 1

    assert fevell_device.set_active_dpi_stage(3) is True
    assert fevell_device.get_active_dpi_stage() == 3

    with pytest.raises(ValueError):
        fevell_device.set_active_dpi_stage(8)


def test_dpi_stage_count(fevell_device):
    # Default is 5
    assert fevell_device.get_dpi_stage_count() == 5

    assert fevell_device.set_dpi_stage_count(4) is True
    assert fevell_device.get_dpi_stage_count() == 4

    with pytest.raises(ValueError):
        fevell_device.set_dpi_stage_count(0)
    with pytest.raises(ValueError):
        fevell_device.set_dpi_stage_count(9)


def test_dpi_stages_read_write(fevell_device):
    stages = fevell_device.get_dpi_stages(count=5)
    assert len(stages) == 5
    assert stages[0] == 400
    assert stages[1] == 800
    assert stages[2] == 1600

    # Modify stage 1 from 800 to 1200
    assert fevell_device.set_dpi_stage(1, 1200) is True
    updated_stages = fevell_device.get_dpi_stages(count=5)
    assert updated_stages[1] == 1200

    with pytest.raises(ValueError):
        fevell_device.set_dpi_stage(0, DPI_MIN - 10)
    with pytest.raises(ValueError):
        fevell_device.set_dpi_stage(0, DPI_MAX + 500)


def test_dpi_colors_read_write(fevell_device):
    # Default stage 0 color is red (255, 0, 0)
    r, g, b = fevell_device.get_dpi_color(0)
    assert (r, g, b) == (255, 0, 0)

    # Set custom color (128, 64, 32)
    assert fevell_device.set_dpi_color(0, 128, 64, 32) is True
    assert fevell_device.get_dpi_color(0) == (128, 64, 32)


def test_read_and_apply_settings(fevell_device):
    initial = fevell_device.read_settings()
    assert initial.polling_rate == 1000
    assert initial.debounce_ms == 4
    assert initial.lod == 1

    custom = MouseSettings(
        polling_rate=500,
        debounce_ms=12,
        lod=2,
        active_stage=2,
        stage_count=3,
        dpi_stages=[800, 1600, 3200],
    )
    assert fevell_device.apply_settings(custom) is True

    applied = fevell_device.read_settings()
    assert applied.polling_rate == 500
    assert applied.debounce_ms == 12
    assert applied.lod == 2
    assert applied.active_stage == 2
    assert applied.stage_count == 3
    assert applied.dpi_stages == [800, 1600, 3200]


def test_context_manager(mock_device):
    dev = FevellDevice()
    dev.connect(hid_device=mock_device)
    assert dev.is_connected is True
    with dev:
        assert dev.is_connected is True
    assert dev.is_connected is False


def test_chunked_flash_read_write(fevell_device):
    # Test reading and writing data larger than 10-byte MAX_PAYLOAD_LEN
    data = bytes(range(18))  # 18 bytes
    assert fevell_device.write_flash_register(0x0200, data) is True

    read_back = fevell_device.read_flash_register(0x0200, 18)
    assert read_back == data


def test_get_hardware_info(fevell_device):
    info = fevell_device.get_hardware_info()
    assert info["model_name"] == "Fevell Z1 / Furylevel Z1"
    assert "PixArt PAW3395" in info["sensor_model"]
    assert "Beken BK3633" in info["mcu_model"]
    assert "0x04F3" in info["vendor_id"]
    assert "0x026E" in info["product_id"]
    assert "v1.0.1.0" in info["firmware_handshake"]
    assert "Native Linux HID Driver" in info["driver_version"]


def test_set_dpi_configuration(fevell_device):
    stages = [600, 1200, 1800, 2400, 3600]
    assert fevell_device.set_dpi_configuration(stages=stages, active_stage=2, stage_count=5) is True

    settings = fevell_device.read_settings()
    assert settings.active_stage == 2
    assert settings.stage_count == 5
    assert settings.dpi_stages[:5] == stages

    with pytest.raises(ValueError):
        fevell_device.set_dpi_configuration(stages=[20, 800])

