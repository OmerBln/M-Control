"""Unit tests for M-Control Qt6 GUI."""

import os
import pytest

# Ensure offscreen platform for Qt in headless environments
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
from mcontrol.gui.app import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_main_window_init_with_fevell(qapp, fevell_device):
    window = MainWindow(device=fevell_device)
    assert window.lbl_device_name.text() == "Fevell Z1"
    assert "Kablolu USB" in window.lbl_conn_mode.text()
    assert window.battery_bar.value() == 88
    assert window.spin_dpi.value() == 800
    assert window.combo_rate.currentText() == "1000 Hz"


def test_main_window_apply_changes(qapp, fevell_device):
    window = MainWindow(device=fevell_device)
    # Change DPI to 1600
    window.spin_dpi.setValue(1600)
    # Change Polling rate to 500 Hz
    window.combo_rate.setCurrentText("500 Hz")
    # Change LOD to 2mm
    window.combo_lod.setCurrentIndex(1)
    # Change debounce to 8ms
    window.slider_debounce.setValue(8)

    # Monkeypatch QMessageBox to avoid blocking popups during test
    from PyQt6 import QtWidgets
    QtWidgets.QMessageBox.information = lambda *args, **kwargs: None
    QtWidgets.QMessageBox.warning = lambda *args, **kwargs: None
    QtWidgets.QMessageBox.critical = lambda *args, **kwargs: None

    window.apply_changes()
    assert fevell_device.get_polling_rate() == 500
    assert fevell_device.get_lod() == 2
    assert fevell_device.get_debounce() == 8
    assert "başarıyla" in window.lbl_status.text()


def test_main_window_tabs_structure(qapp, fevell_device):
    window = MainWindow(device=fevell_device)
    assert window.tabs.count() == 3
    tab_titles = [window.tabs.tabText(i).replace("&&", "&") for i in range(3)]
    assert "DPI & Hassasiyet" in tab_titles
    assert "Sensör & Performans" in tab_titles
    assert "Donanım & Teşhis Bilgileri" in tab_titles


def test_main_window_multi_stage_dpi(qapp, fevell_device):
    window = MainWindow(device=fevell_device)
    assert len(window.stage_spinboxes) == 6
    assert len(window.stage_sliders) == 6
    assert len(window.stage_radios) == 6
    assert len(window.stage_checks) == 6
    assert len(window.stage_color_btns) == 6
    assert len(window.button_combos) == 6

    # Change stage 0 to 600 DPI
    window.stage_spinboxes[0].setValue(600)
    assert window.stage_sliders[0].value() == 600

    # Select stage 0 as active
    window.stage_radios[0].setChecked(True)
    assert window.get_selected_stage_index() == 0
    assert "600 DPI" in window.lbl_active_dpi_display.text()


def test_main_window_presets(qapp, fevell_device):
    window = MainWindow(device=fevell_device)
    window.apply_preset([400, 800, 1200, 1600, 2400, 3200])
    assert window.stage_spinboxes[0].value() == 400
    assert window.stage_spinboxes[2].value() == 1200
    assert window.stage_spinboxes[4].value() == 2400
    assert window.stage_spinboxes[5].value() == 3200


def test_main_window_hardware_tab_diagnostics(qapp, fevell_device):
    window = MainWindow(device=fevell_device)
    assert "PixArt PAW3395" in window.hw_labels["sensor_model"].text()
    assert "Beken BK3633" in window.hw_labels["mcu_model"].text()
    assert "0x04F3" in window.hw_labels["vendor_id"].text()
    assert "0x026E" in window.hw_labels["product_id"].text()


def test_main_window_test_hardware_communication(qapp, fevell_device):
    window = MainWindow(device=fevell_device)
    from PyQt6 import QtWidgets
    info_shown = []
    QtWidgets.QMessageBox.information = lambda parent, title, text: info_shown.append(text)
    window.test_hardware_communication()
    assert len(info_shown) == 1
    assert "Fevell Z1 Donanım İletişimi Başarılı" in info_shown[0]


def test_main_window_copy_diagnostics(qapp, fevell_device):
    window = MainWindow(device=fevell_device)
    from PyQt6 import QtWidgets
    QtWidgets.QMessageBox.information = lambda *args, **kwargs: None
    window.copy_diagnostics_to_clipboard()
    clip_text = QApplication.clipboard().text()
    assert "M-Control Donanım & Teşhis Raporu" in clip_text
    assert "PAW3395" in clip_text


def test_main_window_left_click_safety_guard(qapp, fevell_device):
    window = MainWindow(device=fevell_device)
    # Try changing button 0 (Left Click) to right_click when no other button is left_click
    right_idx = window.button_combos[0].findData("right_click")
    window.button_combos[0].setCurrentIndex(right_idx)
    # Safety guard must revert button 0 back to left_click
    assert window.button_combos[0].currentData() == "left_click"
    assert "Sol Tık" in window.lbl_status.text()



