"""Unit tests for Fevell Z1 protocol, checksums, and MockHIDDevice."""

import pytest
from mcontrol.core.constants import Command, FlashAddr, REPORT_ID_CMD
from mcontrol.core.protocol import (
    calculate_checksum,
    verify_checksum,
    build_command_packet,
    parse_battery_response,
    encode_register_2byte,
    decode_register_2byte,
    encode_dpi_stage,
    decode_dpi_stage,
)
from tests.mock_device import MockHIDDevice


def test_checksum_calculation():
    # An empty packet with cmd=0x03 (DeviceOnline)
    packet = bytearray(16)
    packet[0] = Command.DEVICE_ONLINE
    chk = calculate_checksum(REPORT_ID_CMD, bytes(packet))
    packet[15] = chk

    assert verify_checksum(REPORT_ID_CMD, bytes(packet)) is True
    # The sum of report_id + packet bytes must equal 0x55 (mod 256)
    assert (REPORT_ID_CMD + sum(packet)) & 0xFF == 0x55


def test_build_command_packet():
    packet = build_command_packet(Command.BATTERY_LEVEL)
    assert len(packet) == 16
    assert packet[0] == Command.BATTERY_LEVEL
    assert verify_checksum(REPORT_ID_CMD, packet) is True


def test_battery_response_parsing():
    # Build simulated battery response: 85%, charging, 3950 mV (0x0F6E)
    raw = bytearray(16)
    raw[0] = Command.BATTERY_LEVEL
    raw[5] = 85
    raw[6] = 1
    raw[7] = 0x0F
    raw[8] = 0x6E
    raw[15] = calculate_checksum(REPORT_ID_CMD, bytes(raw))

    status = parse_battery_response(bytes(raw))
    assert status.percentage == 85
    assert status.is_charging is True
    assert status.voltage_mv == 3950
    assert "85" in str(status)


def test_register_encoding_decoding():
    encoded = encode_register_2byte(4)  # Debounce 4ms
    assert len(encoded) == 2
    assert encoded[0] == 4
    assert encoded[1] == (0x55 - 4) & 0xFF

    decoded = decode_register_2byte(encoded, 0)
    assert decoded == 4

    # Corrupt checksum should yield default fallback
    corrupt = bytes([4, 0x00])
    assert decode_register_2byte(corrupt, 0, default=10) == 10


def test_dpi_encoding_decoding():
    # Encode 1600 DPI
    encoded = encode_dpi_stage(1600)
    assert len(encoded) == 4
    # 1600 / 50 = 32 (0x0020)
    assert encoded[0] == 0x00
    assert encoded[1] == 0x20
    assert encoded[2] == 0x00
    expected_chk = (0x55 - 0x20) & 0xFF
    assert encoded[3] == expected_chk

    decoded = decode_dpi_stage(encoded, 0)
    assert decoded == 1600


def test_mock_device_battery_query():
    dev = MockHIDDevice(initial_battery=92, is_charging=False)
    dev.open(0x04F3, 0x026E)

    req = build_command_packet(Command.BATTERY_LEVEL)
    # Prepend report ID for USB output report
    dev.write(bytes([REPORT_ID_CMD]) + req)

    resp = dev.read(17)
    assert len(resp) == 17
    report_id = resp[0]
    payload = bytes(resp[1:])

    assert report_id == REPORT_ID_CMD
    assert verify_checksum(report_id, payload) is True

    status = parse_battery_response(payload)
    assert status.percentage == 92
    assert status.is_charging is False


def test_mock_device_flash_read_write():
    dev = MockHIDDevice()
    dev.open(0x04F3, 0x026E)

    # 1. Read default polling rate (FlashAddr.POLLING_RATE = 0x00)
    req = build_command_packet(Command.READ_FLASH, addr=FlashAddr.POLLING_RATE, length=2)
    dev.write(bytes([REPORT_ID_CMD]) + req)
    resp = dev.read(17)
    payload = bytes(resp[1:])

    # Default is 1000Hz (val = 1)
    rate_val = decode_register_2byte(payload, offset=5)
    assert rate_val == 1

    # 2. Write new polling rate: 500Hz (val = 2)
    new_reg = encode_register_2byte(2)
    write_req = build_command_packet(Command.WRITE_FLASH, addr=FlashAddr.POLLING_RATE, length=2, payload=new_reg)
    dev.write(bytes([REPORT_ID_CMD]) + write_req)
    _ = dev.read(17)

    # 3. Read back to verify
    dev.write(bytes([REPORT_ID_CMD]) + req)
    resp2 = dev.read(17)
    payload2 = bytes(resp2[1:])
    updated_val = decode_register_2byte(payload2, offset=5)
    assert updated_val == 2
