"""Unit tests for native USB Feature Report protocol reversed from GamingMS.exe."""

import pytest
from mcontrol.core.constants import FeatureCommand, POLLING_RATE_MAP
from mcontrol.core.device import FevellDevice
from mcontrol.core.protocol import (
    build_dpi_colors_command,
    build_dpi_command,
    build_feature_command,
    build_feature_key_mapping_packet,
    build_feature_lighting_packet,
    build_lod_command,
    build_polling_rate_command,
    calculate_feature_checksum,
    parse_feature_status_05,
    parse_input_status_report,
    verify_feature_checksum,
)
from tests.mock_device import MockHIDDevice


def test_feature_checksum_calculation():
    # Protocol: GamingMS.exe checksum formula
    pkt = bytearray(32)
    pkt[0] = 0x06
    pkt[1] = 0x02
    pkt[2] = 0x01
    pkt[3] = 0x01
    pkt[4] = 0x00
    pkt[5] = 0x02
    chk = calculate_feature_checksum(bytes(pkt))
    pkt[4] = chk

    assert verify_feature_checksum(bytes(pkt)) is True
    # The checksum must equal sum of all bytes with index 4 set to 0 (mod 256)
    pkt_zeroed = bytearray(pkt)
    pkt_zeroed[4] = 0
    assert (sum(pkt_zeroed) & 0xFF) == chk


def test_build_feature_command():
    cmd_pkt = build_feature_command(FeatureCommand.POLLING_RATE, seq=5, payload=bytes([0x01]))
    assert len(cmd_pkt) == 32
    assert cmd_pkt[0] == 0x06
    assert cmd_pkt[1] == FeatureCommand.POLLING_RATE
    assert cmd_pkt[2] == 5
    assert cmd_pkt[3] == 0x01
    assert cmd_pkt[5] == 0x01
    assert verify_feature_checksum(cmd_pkt) is True


def test_build_dpi_command():
    stages = [400, 800, 1600, 3200, 6400]
    pkt = build_dpi_command(active_stage=2, stages=stages, stage_count=5, seq=3)

    assert len(pkt) == 32
    assert pkt[0] == 0x06
    assert pkt[1] == FeatureCommand.DPI_SETTINGS
    assert pkt[2] == 3
    assert pkt[5] == 2  # active stage index 2 (1600 DPI)
    assert pkt[6] == 0x1F  # 5 stages mask: 0b00011111

    # Stage 1: 400 DPI -> (400 // 50) - 1 = 7 -> 0x0007 (little endian: [7, 0])
    assert pkt[7] == 7
    assert pkt[8] == 0
    # Stage 2: 800 DPI -> (800 // 50) - 1 = 15 -> 0x000F ([15, 0])
    assert pkt[9] == 15
    assert pkt[10] == 0
    # Stage 3: 1600 DPI -> (1600 // 50) - 1 = 31 -> 0x001F ([31, 0])
    assert pkt[11] == 31
    assert pkt[12] == 0

    assert verify_feature_checksum(pkt) is True


def test_build_dpi_colors_command():
    colors = [
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
    ]
    pkt = build_dpi_colors_command(colors, seq=1)
    assert len(pkt) == 32
    assert pkt[0] == 0x06
    assert pkt[1] == FeatureCommand.DPI_COLORS
    # First color: Red
    assert pkt[5] == 255
    assert pkt[6] == 0
    assert pkt[7] == 0
    # Second color: Green
    assert pkt[8] == 0
    assert pkt[9] == 255
    assert pkt[10] == 0
    # Third color: Blue
    assert pkt[11] == 0
    assert pkt[12] == 0
    assert pkt[13] == 255
    assert verify_feature_checksum(pkt) is True


def test_build_polling_rate_command():
    for rate, code in [(1000, 0x01), (500, 0x02), (250, 0x04), (125, 0x08)]:
        pkt = build_polling_rate_command(rate, seq=1)
        assert len(pkt) == 32
        assert pkt[1] == FeatureCommand.POLLING_RATE
        assert pkt[5] == code
        assert verify_feature_checksum(pkt) is True

    with pytest.raises(ValueError):
        build_polling_rate_command(800)


def test_build_lod_command():
    pkt_1mm = build_lod_command(1, seq=1)
    assert pkt_1mm[1] == FeatureCommand.LOD
    assert pkt_1mm[5] == 0x01
    assert verify_feature_checksum(pkt_1mm) is True

    pkt_2mm = build_lod_command(2, seq=1)
    assert pkt_2mm[5] == 0x02
    assert verify_feature_checksum(pkt_2mm) is True

    with pytest.raises(ValueError):
        build_lod_command(3)


def test_parse_feature_status_05():
    # Online handshake packet from real mouse: 05 31 30 31 30 01 01 00 ...
    raw = bytearray(32)
    raw[0] = 0x05
    raw[1:5] = b"1010"
    raw[5] = 0x01  # connected
    raw[6] = 0x01  # 1000Hz mode
    raw[7] = 85    # 85% battery

    is_online, rate_hz, battery = parse_feature_status_05(bytes(raw))
    assert is_online is True
    assert rate_hz == 1000
    assert battery == 85

    # Offline packet (link status = 0)
    raw[5] = 0x00
    is_online, _, _ = parse_feature_status_05(bytes(raw))
    assert is_online is False


def test_fevell_device_feature_commands_with_mock():
    mock = MockHIDDevice(mode="wired")
    dev = FevellDevice()
    dev.connect(hid_device=mock, mode="wired")

    # Verify device online check
    assert dev.is_device_online() is True

    # Verify polling rate set via Feature Report
    assert dev.set_polling_rate(500) is True
    assert dev.get_polling_rate() == 500

    # Verify LOD set via Feature Report
    assert dev.set_lod(2) is True
    assert dev.get_lod() == 2

    # Verify DPI set via Feature Report
    assert dev.set_dpi_stage(0, 1200) is True
    stages = dev.get_dpi_stages()
    assert stages[0] == 1200

    # Ensure Factory Reset (Cmd 0x0F) was NEVER sent during normal setting changes!
    for sent in mock.sent_packets:
        if len(sent) == 32 and sent[0] == 0x06:
            assert sent[1] != FeatureCommand.FACTORY_RESET

    # Verify live Input Report 0x04 polling (simulating physical DPI button press to stage 3)
    mock.queue_input_status_report(active_stage=3, polling_rate_idx=2, battery_pct=77, is_charging=True, lod_flag=0)
    live = dev.poll_input_report()
    assert live is not None
    assert live["active_stage"] == 3
    assert live["polling_rate"] == 500
    assert live["battery_pct"] == 77
    assert live["is_charging"] == 1
    assert live["lod"] == 2
    assert dev._cached_settings.active_stage == 3

    # Verify sensor advanced & power sleep & button mappings commands
    assert dev.set_sensor_advanced(angle_snap=True, motion_sync=True, ripple_control=False) is True
    assert mock.angle_snap is True
    assert mock.motion_sync is True
    assert mock.ripple_control is False

    assert dev.set_power_sleep(sleep_timeout_min=5, move_light_off=False) is True
    assert mock.sleep_timeout_code == 50
    assert mock.move_light_off is False

    dev.disconnect()


def test_build_key_mapping_command():
    # Exact match with GamingMS.exe @ 0x00435bf6..0x00435c86:
    # 06 01 00 01 b8 10 01 00 10 02 00 10 04 00 10 08 00 10 10 00 40 01 00 ...
    pkt = build_feature_key_mapping_packet(seq=0)
    assert len(pkt) == 32
    assert pkt[0] == 0x06
    assert pkt[1] == FeatureCommand.KEY_MAPPING
    assert pkt[2] == 0x00
    assert pkt[3] == 0x01
    assert pkt[4] == 0xB8
    assert pkt[5:23] == bytes.fromhex("100100 100200 100400 100800 101000 400100")
    assert verify_feature_checksum(pkt) is True


def test_build_lighting_command():
    # GamingMS.exe @ 0x00436258..0x004362b0:
    # payload[0]=0, payload[1]=mode, payload[2]=(brightness<<4)|speed, payload[3]=0
    pkt = build_feature_lighting_packet(seq=2, mode=1, brightness=3, speed=2)
    assert len(pkt) == 32
    assert pkt[0] == 0x06
    assert pkt[1] == FeatureCommand.SET_LIGHTING
    assert pkt[5] == 0x00
    assert pkt[6] == 0x01
    assert pkt[7] == 0x32
    assert pkt[8] == 0x00
    assert verify_feature_checksum(pkt) is True


def test_parse_input_status_report_hardware_codes():
    # GamingMS.exe @ 0x00432e03..0x00432f67:
    # report[2]=stage(0..5), report[3]=rate_code(0x01=1000Hz, 0x04=250Hz, 0x08=125Hz),
    # report[4]=battery, report[5]=charge_state(2=full 100%), report[6]=lod(1=1mm, 2=2mm)
    pkt = bytearray(32)
    pkt[0] = 0x04
    pkt[1] = 0x01  # Even if byte 1 is not 0x04, GamingMS.exe only checks byte 0 == 0x04
    pkt[2] = 0x00  # Stage 1 (0-indexed)
    pkt[3] = 0x01  # 1000 Hz hardware code
    pkt[4] = 65
    pkt[5] = 0x02  # Charge state 2 -> forces battery_pct = 100, is_charging = 1
    pkt[6] = 0x01  # 1mm LOD

    parsed = parse_input_status_report(bytes(pkt))
    assert parsed is not None
    assert parsed["active_stage"] == 0
    assert parsed["polling_rate"] == 1000
    assert parsed["battery_pct"] == 100
    assert parsed["is_charging"] == 1
    assert parsed["lod"] == 1



