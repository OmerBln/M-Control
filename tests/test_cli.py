"""Unit tests for M-Control CLI commands."""

import pytest
from unittest.mock import MagicMock
from mcontrol.cli.main import (
    cmd_status,
    cmd_battery,
    cmd_set_dpi,
    cmd_set_rate,
    cmd_set_lod,
    cmd_set_debounce,
    cmd_reset,
)
from mcontrol.core.protocol import BatteryStatus, MouseSettings


def test_cli_cmd_status(fevell_device, capsys):
    args = MagicMock()
    cmd_status(fevell_device, args)
    captured = capsys.readouterr()
    assert "Fevell Z1 Durumu" in captured.out
    assert "Kablolu USB" in captured.out
    assert "%88" in captured.out
    assert "1000 Hz" in captured.out


def test_cli_cmd_battery_formatted(fevell_device, capsys):
    args = MagicMock(raw=False)
    cmd_battery(fevell_device, args)
    captured = capsys.readouterr()
    assert "🔋 %88" in captured.out


def test_cli_cmd_battery_raw(fevell_device, capsys):
    args = MagicMock(raw=True)
    cmd_battery(fevell_device, args)
    captured = capsys.readouterr()
    assert "88\n" == captured.out


def test_cli_cmd_set_dpi(fevell_device, capsys):
    args = MagicMock(dpi=1600, stage=None)
    cmd_set_dpi(fevell_device, args)
    captured = capsys.readouterr()
    assert "Başarılı" in captured.out
    assert "1600" in captured.out


def test_cli_cmd_set_rate(fevell_device, capsys):
    args = MagicMock(rate=500)
    cmd_set_rate(fevell_device, args)
    captured = capsys.readouterr()
    assert "Başarılı" in captured.out
    assert "500 Hz" in captured.out
    assert fevell_device.get_polling_rate() == 500


def test_cli_cmd_set_lod(fevell_device, capsys):
    args = MagicMock(lod=2)
    cmd_set_lod(fevell_device, args)
    captured = capsys.readouterr()
    assert "Başarılı" in captured.out
    assert "2 mm" in captured.out
    assert fevell_device.get_lod() == 2


def test_cli_cmd_set_debounce(fevell_device, capsys):
    args = MagicMock(ms=8)
    cmd_set_debounce(fevell_device, args)
    captured = capsys.readouterr()
    assert "Başarılı" in captured.out
    assert "8 ms" in captured.out
    assert fevell_device.get_debounce() == 8


def test_cli_cmd_reset_requires_force(fevell_device, capsys):
    args = MagicMock(force=False)
    with pytest.raises(SystemExit):
        cmd_reset(fevell_device, args)
    captured = capsys.readouterr()
    assert "--force" in captured.err


def test_cli_cmd_reset_success(fevell_device, capsys):
    # Alter settings first
    fevell_device.set_polling_rate(500)
    args = MagicMock(force=True)
    cmd_reset(fevell_device, args)
    captured = capsys.readouterr()
    assert "Başarılı" in captured.out
    assert "fabrika ayarlarına" in captured.out
    # Must restore 1000 Hz default
    assert fevell_device.get_polling_rate() == 1000


