"""PyQt6 Graphical User Interface for M-Control (Fevell Z1 / Furylevel Z1 Gaming Mouse)."""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mcontrol.core.constants import (
    BUTTON_ACTIONS,
    DEBOUNCE_MAX_MS,
    DEBOUNCE_MIN_MS,
    DEFAULT_BUTTON_KEYS,
    DEFAULT_DPI_STAGE_COLORS,
    DEFAULT_DPI_STAGES,
    DPI_MAX,
    DPI_MIN,
    DPI_STEP,
    LOD_1MM,
    LOD_2MM,
    MAX_DPI_STAGES,
    POLLING_RATE_MAP,
    SLEEP_TIMEOUT_OPTIONS,
)
from mcontrol.core.device import DeviceError, FevellDevice
from mcontrol.core.protocol import MouseSettings

# Modern Dark Gaming Theme modeled after Furylevel Z1 / Fevell Z1 Official Software
# IMPORTANT: Every QFrame rule uses an explicit #objectName selector so child QLabel,
# QRadioButton, QCheckBox, QSpinBox, and QSlider widgets NEVER inherit unintended borders or padding.
STYLESHEET = """
QMainWindow, QWidget#CentralRoot {
    background-color: #0f111a;
    color: #e2e8f0;
    font-family: 'Inter', 'Noto Sans', 'Segoe UI', sans-serif;
    font-size: 13px;
}

QLabel {
    background: transparent;
    border: none;
    padding: 0px;
    color: #e2e8f0;
}

QFrame#TopHeader {
    background-color: #161926;
    border: 1px solid #262b40;
    border-radius: 10px;
}

QFrame#PanelCard {
    background-color: #161926;
    border: 1px solid #262b40;
    border-radius: 10px;
}

QFrame#MouseVisualBox {
    background-color: #111420;
    border: 1px solid #23283c;
    border-radius: 8px;
}

QFrame#StageRow {
    background-color: #1b1f30;
    border: 1px solid #2a3048;
    border-radius: 8px;
}

QFrame#StageRowActive {
    background-color: #1f2742;
    border: 1px solid #3b82f6;
    border-radius: 8px;
}

QFrame#BottomBar {
    background-color: #161926;
    border: 1px solid #262b40;
    border-radius: 10px;
}

QFrame#DiagRow {
    background-color: #1b1f30;
    border: 1px solid #262b40;
    border-radius: 6px;
}

QTabWidget::pane {
    border: none;
    background: transparent;
}

QTabBar::tab {
    background-color: #161926;
    color: #94a3b8;
    border: 1px solid #262b40;
    border-radius: 8px;
    padding: 9px 20px;
    margin-right: 8px;
    font-weight: 600;
    font-size: 13px;
}

QTabBar::tab:selected {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #3b82f6;
}

QTabBar::tab:hover:!selected {
    background-color: #1e2436;
    color: #f8fafc;
}

QPushButton {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #3b82f6;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 600;
    font-size: 12px;
}

QPushButton:hover {
    background-color: #3b82f6;
}

QPushButton:pressed {
    background-color: #1d4ed8;
}

QPushButton#SecondaryBtn {
    background-color: #1e2436;
    color: #cbd5e1;
    border: 1px solid #333b54;
}

QPushButton#SecondaryBtn:hover {
    background-color: #283048;
    color: #ffffff;
    border: 1px solid #475569;
}

QPushButton#RatePill {
    background-color: #1b1f30;
    color: #94a3b8;
    border: 1px solid #2a3048;
    border-radius: 6px;
    padding: 7px 10px;
    font-weight: 700;
}

QPushButton#RatePill:checked {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #60a5fa;
}

QPushButton#RatePill:hover:!checked {
    background-color: #23293e;
    color: #e2e8f0;
}

QPushButton#ApplyBtn {
    background-color: #16a34a;
    color: #ffffff;
    border: 1px solid #22c55e;
    border-radius: 7px;
    padding: 9px 22px;
    font-size: 13px;
    font-weight: 700;
}

QPushButton#ApplyBtn:hover {
    background-color: #22c55e;
}

QPushButton#DangerBtn {
    background-color: #2a1820;
    color: #fca5a5;
    border: 1px solid #7f1d1d;
}

QPushButton#DangerBtn:hover {
    background-color: #991b1b;
    color: #ffffff;
}

QComboBox, QSpinBox {
    background-color: #111420;
    color: #f8fafc;
    border: 1px solid #2e3650;
    border-radius: 6px;
    padding: 5px 10px;
    font-weight: 600;
    selection-background-color: #2563eb;
}

QComboBox:focus, QSpinBox:focus {
    border: 1px solid #3b82f6;
}

QComboBox::drop-down {
    border: none;
    width: 22px;
}

QComboBox QAbstractItemView {
    background-color: #161926;
    color: #f8fafc;
    border: 1px solid #3b82f6;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
    outline: 0;
}

QSlider::groove:horizontal {
    border: none;
    height: 6px;
    background: #111420;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: #3b82f6;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #f8fafc;
    border: 2px solid #2563eb;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 8px;
}

QSlider::handle:horizontal:hover {
    background: #60a5fa;
}

QProgressBar {
    border: 1px solid #2e3650;
    border-radius: 6px;
    background-color: #111420;
    text-align: center;
    color: #ffffff;
    font-weight: 700;
    font-size: 11px;
}

QProgressBar::chunk {
    background-color: #10b981;
    border-radius: 5px;
}

QRadioButton, QCheckBox {
    background: transparent;
    border: none;
    padding: 0px;
    color: #e2e8f0;
    font-weight: 600;
    spacing: 6px;
}

QRadioButton::indicator {
    width: 15px;
    height: 15px;
    border-radius: 8px;
    border: 2px solid #475569;
    background-color: #111420;
}

QRadioButton::indicator:checked {
    background-color: #3b82f6;
    border: 2px solid #93c5fd;
}

QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 2px solid #475569;
    background-color: #111420;
}

QCheckBox::indicator:checked {
    background-color: #2563eb;
    border: 2px solid #60a5fa;
}

QScrollArea {
    border: none;
    background: transparent;
}
"""


class MainWindow(QMainWindow):
    """
    Main application window for M-Control modeled after the official
    Fevell Z1 / Furylevel Z1 configuration suite.
    """

    def __init__(self, device: Optional[FevellDevice] = None):
        super().__init__()
        self.device = device or FevellDevice()
        self.setWindowTitle("M-Control — Fevell Z1 / Furylevel Z1")
        self.setMinimumSize(1020, 720)
        self.resize(1060, 750)
        self.setStyleSheet(STYLESHEET)
        self._syncing_ui = False

        assets_dir = Path(__file__).resolve().parent.parent / "assets"
        for icon_name in ("m-control.png", "m-control.svg"):
            icon_path = assets_dir / icon_name
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
                break

        self._assets_dir = assets_dir
        self._stage_colors: List[Tuple[int, int, int]] = list(DEFAULT_DPI_STAGE_COLORS[:MAX_DPI_STAGES])
        self._buttons_dirty = False
        self._lighting_dirty = False
        self._colors_dirty = False
        self._last_applied_buttons: List[str] = list(DEFAULT_BUTTON_KEYS)

        self._dpi_commit_timer = QTimer(self)
        self._dpi_commit_timer.setSingleShot(True)
        self._dpi_commit_timer.setInterval(250)
        self._dpi_commit_timer.timeout.connect(self._on_dpi_commit_timer_timeout)

        self._init_ui()
        self.refresh_device_state()

        # Fast non-blocking timer (200ms) for physical DPI button presses (Input Report 0x04)
        self.live_input_timer = QTimer(self)
        self.live_input_timer.timeout.connect(self._poll_live_hardware_events)
        self.live_input_timer.start(200)

        # Periodic telemetry refresh timer (15s)
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.timeout.connect(self.update_battery_only)
        self.telemetry_timer.start(15000)

        # Keyboard emergency recovery shortcut (Ctrl+Shift+R)
        self.recovery_action = QAction(self)
        self.recovery_action.setShortcut(QKeySequence("Ctrl+Shift+R"))
        self.recovery_action.triggered.connect(self._on_emergency_recovery_shortcut)
        self.addAction(self.recovery_action)

    def _init_ui(self) -> None:
        central = QWidget()
        central.setObjectName("CentralRoot")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(12)

        # --- 1. Top Header Bar ---
        header_card = QFrame()
        header_card.setObjectName("TopHeader")
        header_card.setFixedHeight(68)
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(18, 10, 18, 10)
        header_layout.setSpacing(16)

        # Brand & Device Name
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.lbl_device_name = QLabel("Fevell Z1")
        self.lbl_device_name.setFont(QFont("Inter", 16, QFont.Weight.Bold))
        self.lbl_device_name.setStyleSheet("color: #f8fafc;")

        self.lbl_conn_mode = QLabel("Durum: Aranıyor...")
        self.lbl_conn_mode.setStyleSheet("color: #60a5fa; font-size: 12px; font-weight: 600;")
        title_col.addWidget(self.lbl_device_name)
        title_col.addWidget(self.lbl_conn_mode)
        header_layout.addLayout(title_col)

        header_layout.addStretch()

        # Active DPI Live Pill in Header
        self.lbl_active_dpi_display = QLabel("800 DPI (2. Kademe)")
        self.lbl_active_dpi_display.setStyleSheet(
            "background-color: #1e293b; color: #38bdf8; border: 1px solid #334155; "
            "border-radius: 6px; padding: 6px 14px; font-size: 13px; font-weight: 700;"
        )
        header_layout.addWidget(self.lbl_active_dpi_display)

        # Battery Bar
        bat_box = QHBoxLayout()
        bat_box.setSpacing(6)
        lbl_bat = QLabel("Pil:")
        lbl_bat.setFixedWidth(26)
        lbl_bat.setStyleSheet("color: #94a3b8; font-weight: 600;")
        self.battery_bar = QProgressBar()
        self.battery_bar.setRange(0, 100)
        self.battery_bar.setValue(0)
        self.battery_bar.setFixedWidth(115)
        self.battery_bar.setFixedHeight(22)
        self.battery_bar.setFormat("%p%")
        bat_box.addWidget(lbl_bat)
        bat_box.addWidget(self.battery_bar)
        header_layout.addLayout(bat_box)

        self.btn_reconnect = QPushButton("Yenile")
        self.btn_reconnect.setObjectName("SecondaryBtn")
        self.btn_reconnect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reconnect.clicked.connect(self.refresh_device_state)
        header_layout.addWidget(self.btn_reconnect)

        main_layout.addWidget(header_card)

        # --- 2. Navigation Tabs ---
        self.tabs = QTabWidget()
        self.tab_dpi = QWidget()
        self.tab_perf = QWidget()
        self.tab_hw = QWidget()

        self.tabs.addTab(self.tab_dpi, "DPI && Hassasiyet")
        self.tabs.addTab(self.tab_perf, "Sensör && Performans")
        self.tabs.addTab(self.tab_hw, "Donanım && Teşhis Bilgileri")

        self._build_dpi_and_buttons_tab()
        self._build_performance_and_sensor_tab()
        self._build_hardware_diagnostics_tab()

        main_layout.addWidget(self.tabs, stretch=1)

        # --- 3. Bottom Action Bar ---
        bottom_card = QFrame()
        bottom_card.setObjectName("BottomBar")
        bottom_card.setFixedHeight(56)
        bottom_layout = QHBoxLayout(bottom_card)
        bottom_layout.setContentsMargins(16, 8, 16, 8)
        bottom_layout.setSpacing(12)

        self.lbl_status = QLabel("Hazır.")
        self.lbl_status.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600;")
        bottom_layout.addWidget(self.lbl_status)

        bottom_layout.addStretch()

        self.chk_live_apply = QCheckBox("Anında Uygula (Canlı)")
        self.chk_live_apply.setChecked(True)
        self.chk_live_apply.setToolTip(
            "Etkinleştirildiğinde kademe veya hız seçimleri anında fareye gönderilir."
        )
        bottom_layout.addWidget(self.chk_live_apply)

        self.btn_read_device = QPushButton("Ayarları Oku")
        self.btn_read_device.setObjectName("SecondaryBtn")
        self.btn_read_device.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_read_device.clicked.connect(self.refresh_device_state)
        bottom_layout.addWidget(self.btn_read_device)

        self.btn_apply = QPushButton("Uygula ve Fareye Kaydet")
        self.btn_apply.setObjectName("ApplyBtn")
        self.btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply.clicked.connect(self.apply_changes)
        bottom_layout.addWidget(self.btn_apply)

        main_layout.addWidget(bottom_card)

    def _build_dpi_and_buttons_tab(self) -> None:
        """
        Build Tab 1: Furylevel Z1 Split View:
        - Left Column: Fevell Z1 Mouse Diagram (`fevell-z1-mouse.png`) + 6 Numbered Button Mappings
        - Right Column: 6 DPI Stages (Checkbox + Radio + Color Swatch + Slider + SpinBox) + Polling Rate Pills
        """
        root_layout = QHBoxLayout(self.tab_dpi)
        root_layout.setContentsMargins(0, 6, 0, 0)
        root_layout.setSpacing(14)

        # ==================== LEFT PANEL: MOUSE DIAGRAM & 6 BUTTONS ====================
        left_card = QFrame()
        left_card.setObjectName("PanelCard")
        left_card.setFixedWidth(370)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(14, 12, 14, 12)
        left_layout.setSpacing(10)

        lbl_left_title = QLabel("Tuş Atamaları & Fare Görünümü")
        lbl_left_title.setFont(QFont("Inter", 13, QFont.Weight.Bold))
        lbl_left_title.setStyleSheet("color: #f8fafc;")
        left_layout.addWidget(lbl_left_title)

        # Mouse Visual Container
        visual_box = QFrame()
        visual_box.setObjectName("MouseVisualBox")
        visual_layout = QVBoxLayout(visual_box)
        visual_layout.setContentsMargins(8, 8, 8, 8)
        visual_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_mouse_image = QLabel()
        self.lbl_mouse_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mouse_img_path = self._assets_dir / "fevell-z1-mouse.png"
        if mouse_img_path.exists():
            pix = QPixmap(str(mouse_img_path)).scaled(
                185,
                230,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.lbl_mouse_image.setPixmap(pix)
        else:
            self.lbl_mouse_image.setText("FEVELL Z1")
        visual_layout.addWidget(self.lbl_mouse_image)
        left_layout.addWidget(visual_box)

        # 6 Button Assignment Combos matching callouts 1..6 on the mouse image
        btn_grid = QGridLayout()
        btn_grid.setHorizontalSpacing(10)
        btn_grid.setVerticalSpacing(6)

        button_labels = [
            "1. Sol Tık",
            "2. Sağ Tık",
            "3. Orta Tık",
            "4. İleri Tuşu",
            "5. Geri Tuşu",
            "6. DPI Tuşu",
        ]
        self.button_combos: List[QComboBox] = []
        action_items = [(key, label) for key, (label, _) in BUTTON_ACTIONS.items()]

        for idx, text in enumerate(button_labels):
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #cbd5e1; font-size: 12px; font-weight: 600;")
            combo = QComboBox()
            for key, human_label in action_items:
                combo.addItem(human_label, userData=key)
            default_key = DEFAULT_BUTTON_KEYS[idx]
            default_idx = combo.findData(default_key)
            if default_idx >= 0:
                combo.setCurrentIndex(default_idx)
            combo.currentIndexChanged.connect(
                lambda _c_idx, b_idx=idx: self._on_button_mapping_changed(b_idx)
            )
            self.button_combos.append(combo)
            btn_grid.addWidget(lbl, idx, 0)
            btn_grid.addWidget(combo, idx, 1)

        btn_grid.setColumnStretch(1, 1)
        left_layout.addLayout(btn_grid)
        left_layout.addStretch()

        root_layout.addWidget(left_card)

        # ==================== RIGHT PANEL: 6 DPI STAGES & POLLING RATE ====================
        right_card = QFrame()
        right_card.setObjectName("PanelCard")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(16, 12, 16, 12)
        right_layout.setSpacing(10)

        # Top row of right card: Title + Quick Presets
        dpi_top_row = QHBoxLayout()
        lbl_dpi_title = QLabel("DPI Kademeleri (50 – 26.000 DPI)")
        lbl_dpi_title.setFont(QFont("Inter", 13, QFont.Weight.Bold))
        lbl_dpi_title.setStyleSheet("color: #f8fafc;")
        dpi_top_row.addWidget(lbl_dpi_title)
        dpi_top_row.addStretch()

        presets = [
            ("Espor (400-3200)", [400, 800, 1200, 1600, 2400, 3200]),
            ("Varsayılan", [400, 800, 1600, 3200, 6400, 12000]),
            ("Maksimum (26K)", [800, 1600, 3200, 6400, 12800, 26000]),
        ]
        for title, values in presets:
            btn_p = QPushButton(title)
            btn_p.setObjectName("SecondaryBtn")
            btn_p.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_p.clicked.connect(lambda checked, v=values: self.apply_preset(v))
            dpi_top_row.addWidget(btn_p)

        right_layout.addLayout(dpi_top_row)

        lbl_dpi_hint = QLabel(
            "Aktif kademeyi yuvarlak seçim kutusundan veya fare üzerindeki DPI tuşuna basarak değiştirebilirsiniz."
        )
        lbl_dpi_hint.setStyleSheet("color: #94a3b8; font-size: 11px;")
        right_layout.addWidget(lbl_dpi_hint)

        # Hidden compatibility spin_dpi synced with the active stage spinbox
        self.spin_dpi = QSpinBox()
        self.spin_dpi.setRange(DPI_MIN, DPI_MAX)
        self.spin_dpi.setSingleStep(DPI_STEP)
        self.spin_dpi.setValue(800)
        self.spin_dpi.setVisible(False)
        self.spin_dpi.valueChanged.connect(self._on_compat_spin_dpi_changed)

        # 6 Stage Rows
        self.stage_cards: List[QFrame] = []
        self.stage_checks: List[QCheckBox] = []
        self.stage_radios: List[QRadioButton] = []
        self.stage_color_btns: List[QPushButton] = []
        self.stage_sliders: List[QSlider] = []
        self.stage_spinboxes: List[QSpinBox] = []
        self.stage_radio_group = QButtonGroup(self)
        self.stage_radio_group.setExclusive(True)

        for i in range(MAX_DPI_STAGES):
            row_card = QFrame()
            row_card.setObjectName("StageRowActive" if i == 1 else "StageRow")
            row_card.setFixedHeight(48)
            row_layout = QHBoxLayout(row_card)
            row_layout.setContentsMargins(12, 6, 12, 6)
            row_layout.setSpacing(10)

            chk = QCheckBox()
            chk.setChecked(i < 5)
            chk.setToolTip(f"{i + 1}. DPI kademesini döngüye dahil et / çıkar")
            chk.toggled.connect(lambda checked, idx=i: self._on_stage_enable_toggled(idx, checked))

            radio = QRadioButton(f"{i + 1}. Kademe")
            radio.setFixedWidth(98)
            radio.setCursor(Qt.CursorShape.PointingHandCursor)
            if i == 1:
                radio.setChecked(True)
            self.stage_radio_group.addButton(radio, i)
            radio.toggled.connect(lambda checked, idx=i: self._on_stage_radio_toggled(idx, checked))

            # Color indicator button
            r_c, g_c, b_c = self._stage_colors[i]
            btn_color = QPushButton()
            btn_color.setFixedSize(22, 22)
            btn_color.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_color.setToolTip(f"{i + 1}. Kademe RGB rengini seçin")
            btn_color.setStyleSheet(
                f"background-color: rgb({r_c}, {g_c}, {b_c}); "
                "border: 2px solid #cbd5e1; border-radius: 11px; padding: 0px;"
            )
            btn_color.clicked.connect(lambda checked, idx=i: self._choose_stage_color(idx))

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(DPI_MIN, DPI_MAX)
            slider.setSingleStep(DPI_STEP)
            slider.setPageStep(DPI_STEP * 4)
            default_val = DEFAULT_DPI_STAGES[i] if i < len(DEFAULT_DPI_STAGES) else 3200
            slider.setValue(default_val)

            spin = QSpinBox()
            spin.setRange(DPI_MIN, DPI_MAX)
            spin.setSingleStep(DPI_STEP)
            spin.setSuffix(" DPI")
            spin.setValue(default_val)
            spin.setFixedWidth(112)

            slider.valueChanged.connect(lambda val, idx=i: self._on_stage_slider_moved(idx, val))
            slider.sliderReleased.connect(lambda idx=i: self._on_stage_value_committed(idx))
            spin.valueChanged.connect(lambda val, idx=i: self._on_stage_spin_changed(idx, val))
            spin.editingFinished.connect(lambda idx=i: self._on_stage_value_committed(idx))

            row_layout.addWidget(chk)
            row_layout.addWidget(radio)
            row_layout.addWidget(btn_color)
            row_layout.addWidget(slider, stretch=1)
            row_layout.addWidget(spin)

            self.stage_cards.append(row_card)
            self.stage_checks.append(chk)
            self.stage_radios.append(radio)
            self.stage_color_btns.append(btn_color)
            self.stage_sliders.append(slider)
            self.stage_spinboxes.append(spin)
            right_layout.addWidget(row_card)

        right_layout.addStretch()

        # Quick Polling Rate Selector Bar at bottom of Right Column
        rate_bar_frame = QFrame()
        rate_bar_frame.setObjectName("StageRow")
        rate_bar_frame.setFixedHeight(50)
        rate_bar_layout = QHBoxLayout(rate_bar_frame)
        rate_bar_layout.setContentsMargins(14, 6, 14, 6)
        rate_bar_layout.setSpacing(10)

        lbl_quick_rate = QLabel("Raporlama Hızı (Polling Rate):")
        lbl_quick_rate.setStyleSheet("color: #f8fafc; font-weight: 700; font-size: 12px;")
        rate_bar_layout.addWidget(lbl_quick_rate)
        rate_bar_layout.addStretch()

        self.rate_pill_group = QButtonGroup(self)
        self.rate_pill_group.setExclusive(True)
        self.rate_pills: Dict[int, QPushButton] = {}
        for hz in (125, 250, 500, 1000):
            pill = QPushButton(f"{hz} Hz")
            pill.setObjectName("RatePill")
            pill.setCheckable(True)
            pill.setCursor(Qt.CursorShape.PointingHandCursor)
            pill.setFixedWidth(84)
            if hz == 1000:
                pill.setChecked(True)
            self.rate_pill_group.addButton(pill, hz)
            self.rate_pills[hz] = pill
            pill.clicked.connect(lambda checked, rate=hz: self._on_rate_pill_clicked(rate))
            rate_bar_layout.addWidget(pill)

        right_layout.addWidget(rate_bar_frame)
        root_layout.addWidget(right_card, stretch=1)

    def _build_performance_and_sensor_tab(self) -> None:
        """
        Build Tab 2: PAW3395 Advanced Sensor Controls, LOD, Debounce, Power Sleep & RGB Lighting.
        """
        root_layout = QHBoxLayout(self.tab_perf)
        root_layout.setContentsMargins(0, 6, 0, 0)
        root_layout.setSpacing(14)

        # Left Column: Sensor & Click Response
        sensor_card = QFrame()
        sensor_card.setObjectName("PanelCard")
        sensor_layout = QVBoxLayout(sensor_card)
        sensor_layout.setContentsMargins(18, 16, 18, 16)
        sensor_layout.setSpacing(14)

        lbl_sensor_hdr = QLabel("PAW3395 Sensör & Tuş Tepkimesi")
        lbl_sensor_hdr.setFont(QFont("Inter", 14, QFont.Weight.Bold))
        lbl_sensor_hdr.setStyleSheet("color: #f8fafc;")
        sensor_layout.addWidget(lbl_sensor_hdr)

        # Polling Rate ComboBox
        row_rate = QHBoxLayout()
        lbl_rate = QLabel("Yoklama Oranı (Polling Rate):")
        lbl_rate.setStyleSheet("color: #cbd5e1; font-weight: 600;")
        self.combo_rate = QComboBox()
        for rate in sorted(POLLING_RATE_MAP.keys()):
            self.combo_rate.addItem(f"{rate} Hz", userData=rate)
        self.combo_rate.setCurrentText("1000 Hz")
        self.combo_rate.currentTextChanged.connect(self._on_combo_rate_changed)
        row_rate.addWidget(lbl_rate)
        row_rate.addStretch()
        row_rate.addWidget(self.combo_rate)
        sensor_layout.addLayout(row_rate)

        # Lift-Off Distance (LOD) ComboBox
        row_lod = QHBoxLayout()
        lbl_lod = QLabel("Kalkış Mesafesi (Lift-Off Distance / LOD):")
        lbl_lod.setStyleSheet("color: #cbd5e1; font-weight: 600;")
        self.combo_lod = QComboBox()
        self.combo_lod.addItem("1 mm (Düşük — Rekabetçi)", userData=LOD_1MM)
        self.combo_lod.addItem("2 mm (Standart)", userData=LOD_2MM)
        self.combo_lod.currentIndexChanged.connect(self._on_lod_changed)
        row_lod.addWidget(lbl_lod)
        row_lod.addStretch()
        row_lod.addWidget(self.combo_lod)
        sensor_layout.addLayout(row_lod)

        # Key Debounce Slider
        deb_hdr = QHBoxLayout()
        lbl_deb = QLabel("Tuş Tepki Gecikmesi (Key Debounce):")
        lbl_deb.setStyleSheet("color: #cbd5e1; font-weight: 600;")
        self.lbl_debounce_val = QLabel("4 ms")
        self.lbl_debounce_val.setStyleSheet("color: #38bdf8; font-weight: 700; font-size: 13px;")
        deb_hdr.addWidget(lbl_deb)
        deb_hdr.addStretch()
        deb_hdr.addWidget(self.lbl_debounce_val)
        sensor_layout.addLayout(deb_hdr)

        self.slider_debounce = QSlider(Qt.Orientation.Horizontal)
        self.slider_debounce.setRange(DEBOUNCE_MIN_MS, DEBOUNCE_MAX_MS)
        self.slider_debounce.setValue(4)
        self.slider_debounce.valueChanged.connect(self._on_debounce_slider_changed)
        self.slider_debounce.sliderReleased.connect(self._on_debounce_committed)
        sensor_layout.addWidget(self.slider_debounce)

        # PAW3395 Hardware Feature Checkboxes (Cmd 0x08)
        lbl_adv_hdr = QLabel("Gelişmiş PAW3395 Sensör Algoritmaları")
        lbl_adv_hdr.setFont(QFont("Inter", 12, QFont.Weight.Bold))
        lbl_adv_hdr.setStyleSheet("color: #93c5fd; margin-top: 6px;")
        sensor_layout.addWidget(lbl_adv_hdr)

        self.chk_motion_sync = QCheckBox("Motion Sync (Sensör ve USB paketlerini senkronize et — Önerilen)")
        self.chk_motion_sync.setChecked(True)
        self.chk_motion_sync.toggled.connect(self._on_sensor_advanced_changed)

        self.chk_angle_snap = QCheckBox("Angle Snapping / Açı Düzeltme (Doğrusal çizim düzleştirme)")
        self.chk_angle_snap.setChecked(False)
        self.chk_angle_snap.toggled.connect(self._on_sensor_advanced_changed)

        self.chk_ripple_control = QCheckBox("Ripple Control / Dalgalanma Önleme (Yüksek DPI yumuşatma)")
        self.chk_ripple_control.setChecked(False)
        self.chk_ripple_control.toggled.connect(self._on_sensor_advanced_changed)

        sensor_layout.addWidget(self.chk_motion_sync)
        sensor_layout.addWidget(self.chk_angle_snap)
        sensor_layout.addWidget(self.chk_ripple_control)
        sensor_layout.addStretch()

        root_layout.addWidget(sensor_card, stretch=1)

        # Right Column: Power Management & RGB Lighting + Factory Reset
        power_card = QFrame()
        power_card.setObjectName("PanelCard")
        power_layout = QVBoxLayout(power_card)
        power_layout.setContentsMargins(18, 16, 18, 16)
        power_layout.setSpacing(14)

        lbl_power_hdr = QLabel("Güç Yönetimi & RGB Aydınlatma")
        lbl_power_hdr.setFont(QFont("Inter", 14, QFont.Weight.Bold))
        lbl_power_hdr.setStyleSheet("color: #f8fafc;")
        power_layout.addWidget(lbl_power_hdr)

        # Sleep Timeout
        row_sleep = QHBoxLayout()
        lbl_sleep = QLabel("Kablosuz Uyku Süresi:")
        lbl_sleep.setStyleSheet("color: #cbd5e1; font-weight: 600;")
        self.combo_sleep = QComboBox()
        for mins in sorted(SLEEP_TIMEOUT_OPTIONS.keys()):
            self.combo_sleep.addItem(f"{mins} Dakika", userData=mins)
        self.combo_sleep.currentIndexChanged.connect(self._on_power_sleep_changed)
        row_sleep.addWidget(lbl_sleep)
        row_sleep.addStretch()
        row_sleep.addWidget(self.combo_sleep)
        power_layout.addLayout(row_sleep)

        self.chk_move_light_off = QCheckBox("Fare hareket ederken pil tasarrufu için LED ışığını kapat")
        self.chk_move_light_off.setChecked(True)
        self.chk_move_light_off.toggled.connect(self._on_power_sleep_changed)
        power_layout.addWidget(self.chk_move_light_off)

        # Lighting Effect Mode
        row_light = QHBoxLayout()
        lbl_light = QLabel("Aydınlatma Efekti:")
        lbl_light.setStyleSheet("color: #cbd5e1; font-weight: 600;")
        self.combo_lighting_mode = QComboBox()
        self.combo_lighting_mode.addItem("Kapalı (Off)", userData=0)
        self.combo_lighting_mode.addItem("Sabit Renk (Steady)", userData=1)
        self.combo_lighting_mode.addItem("Nefes Alma (Breathing)", userData=2)
        self.combo_lighting_mode.addItem("Gökkuşağı Dalga (Rainbow)", userData=3)
        self.combo_lighting_mode.setCurrentIndex(1)
        self.combo_lighting_mode.currentIndexChanged.connect(self._on_lighting_changed)
        row_light.addWidget(lbl_light)
        row_light.addStretch()
        row_light.addWidget(self.combo_lighting_mode)
        power_layout.addLayout(row_light)

        # Brightness slider
        row_bright = QHBoxLayout()
        lbl_bright = QLabel("LED Parlaklık Seviyesi:")
        lbl_bright.setStyleSheet("color: #cbd5e1; font-weight: 600;")
        self.slider_brightness = QSlider(Qt.Orientation.Horizontal)
        self.slider_brightness.setRange(1, 4)
        self.slider_brightness.setValue(3)
        self.slider_brightness.sliderReleased.connect(self._on_lighting_changed)
        row_bright.addWidget(lbl_bright)
        row_bright.addWidget(self.slider_brightness, stretch=1)
        power_layout.addLayout(row_bright)

        power_layout.addStretch()

        # Factory Reset Box
        reset_row = QHBoxLayout()
        lbl_reset_info = QLabel("Tüm ayarları varsayılan fabrika değerlerine döndür:")
        lbl_reset_info.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self.btn_factory_reset = QPushButton("Fabrika Ayarlarına Sıfırla")
        self.btn_factory_reset.setObjectName("DangerBtn")
        self.btn_factory_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_factory_reset.clicked.connect(self._on_factory_reset_clicked)
        reset_row.addWidget(lbl_reset_info)
        reset_row.addStretch()
        reset_row.addWidget(self.btn_factory_reset)
        power_layout.addLayout(reset_row)

        root_layout.addWidget(power_card, stretch=1)

    def _build_hardware_diagnostics_tab(self) -> None:
        """Build Tab 3: Comprehensive Hardware & Protocol Diagnostics."""
        layout = QVBoxLayout(self.tab_hw)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(12)

        hw_card = QFrame()
        hw_card.setObjectName("PanelCard")
        hw_layout = QVBoxLayout(hw_card)
        hw_layout.setContentsMargins(18, 16, 18, 16)
        hw_layout.setSpacing(12)

        lbl_title = QLabel("Donanım Kimliği, Sensör ve Canlı HID Protokol Teşhisi")
        lbl_title.setFont(QFont("Inter", 14, QFont.Weight.Bold))
        lbl_title.setStyleSheet("color: #f8fafc;")
        hw_layout.addWidget(lbl_title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)

        self.hw_labels: Dict[str, QLabel] = {}
        fields = [
            ("model_name", "Fare Modeli"),
            ("sensor_model", "Optik Sensör"),
            ("mcu_model", "Mikrodenetleyici (MCU)"),
            ("connection_type", "Aktif Bağlantı Tipi"),
            ("vendor_id", "USB Üretici Kimliği (VID)"),
            ("product_id", "USB Ürün Kimliği (PID)"),
            ("hidraw_node", "Linux Aygıt Düğümü"),
            ("usb_interface", "HID Yapılandırma Arayüzü"),
            ("firmware_handshake", "Donanım Yazılımı (Firmware)"),
            ("live_battery", "Canlı Pil ve Voltaj Telemetrisi"),
            ("live_settings_summary", "Aktif Donanım Özeti"),
            ("status_report_05", "Durum Raporu (Report 0x05)"),
            ("wake_report_bc", "Uyandırma Raporu (Report 0xBC)"),
            ("driver_version", "Sürücü & Protokol Sürümü"),
        ]

        for idx, (key, label_text) in enumerate(fields):
            row = idx // 2
            col = (idx % 2) * 2

            cell = QFrame()
            cell.setObjectName("DiagRow")
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(12, 8, 12, 8)

            lbl_k = QLabel(f"{label_text}:")
            lbl_k.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600;")

            lbl_v = QLabel("Okunuyor...")
            color_hex = "#34d399" if ("Pil" in label_text or "Özeti" in label_text) else "#f8fafc"
            lbl_v.setStyleSheet(f"color: {color_hex}; font-size: 12px; font-weight: 700;")
            lbl_v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            cell_layout.addWidget(lbl_k)
            cell_layout.addStretch()
            cell_layout.addWidget(lbl_v)
            self.hw_labels[key] = lbl_v
            grid.addWidget(cell, row, col, 1, 2)

        hw_layout.addLayout(grid)
        hw_layout.addStretch()

        action_row = QHBoxLayout()
        self.btn_test_comm = QPushButton("Donanım İletişimini Test Et")
        self.btn_test_comm.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test_comm.clicked.connect(self.test_hardware_communication)

        self.btn_copy_diag = QPushButton("Bilgileri Panoya Kopyala")
        self.btn_copy_diag.setObjectName("SecondaryBtn")
        self.btn_copy_diag.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_diag.clicked.connect(self.copy_diagnostics_to_clipboard)

        action_row.addWidget(self.btn_test_comm)
        action_row.addWidget(self.btn_copy_diag)
        action_row.addStretch()
        hw_layout.addLayout(action_row)

        layout.addWidget(hw_card, stretch=1)

    # ==================== EVENT HANDLERS & SYNCHRONIZATION ====================

    def _on_dpi_commit_timer_timeout(self) -> None:
        if self._syncing_ui:
            return
        if self.chk_live_apply.isChecked() and self.device.is_connected:
            self._push_dpi_to_hardware()

    def _on_stage_slider_moved(self, stage_idx: int, value: int) -> None:
        if self._syncing_ui:
            return
        snapped = max(DPI_MIN, min(DPI_MAX, round(value / DPI_STEP) * DPI_STEP))
        self._syncing_ui = True
        try:
            if self.stage_sliders[stage_idx].value() != snapped:
                self.stage_sliders[stage_idx].setValue(snapped)
            self.stage_spinboxes[stage_idx].setValue(snapped)
            if self.stage_radios[stage_idx].isChecked():
                self.spin_dpi.setValue(snapped)
            self._update_active_dpi_banner()
        finally:
            self._syncing_ui = False

        if not self.stage_sliders[stage_idx].isSliderDown() and self.chk_live_apply.isChecked():
            self._dpi_commit_timer.start(250)

    def _on_stage_spin_changed(self, stage_idx: int, value: int) -> None:
        if self._syncing_ui:
            return
        snapped = max(DPI_MIN, min(DPI_MAX, round(value / DPI_STEP) * DPI_STEP))
        self._syncing_ui = True
        try:
            self.stage_sliders[stage_idx].setValue(snapped)
            if self.stage_radios[stage_idx].isChecked():
                self.spin_dpi.setValue(snapped)
            self._update_active_dpi_banner()
        finally:
            self._syncing_ui = False

        if self.chk_live_apply.isChecked():
            self._dpi_commit_timer.start(250)

    def _on_stage_value_committed(self, stage_idx: int) -> None:
        if self._syncing_ui:
            return
        self._dpi_commit_timer.stop()
        if self.chk_live_apply.isChecked() and self.device.is_connected:
            self._push_dpi_to_hardware()

    def _on_compat_spin_dpi_changed(self, value: int) -> None:
        if self._syncing_ui:
            return
        active_idx = self.get_selected_stage_index()
        self._syncing_ui = True
        try:
            self.stage_spinboxes[active_idx].setValue(value)
            self.stage_sliders[active_idx].setValue(value)
            self._update_active_dpi_banner()
        finally:
            self._syncing_ui = False

    def _on_stage_radio_toggled(self, stage_idx: int, checked: bool) -> None:
        if not checked:
            return
        if not self.stage_checks[stage_idx].isChecked():
            self._syncing_ui = True
            self.stage_checks[stage_idx].setChecked(True)
            self._syncing_ui = False

        was_syncing = self._syncing_ui
        self._syncing_ui = True
        try:
            self.spin_dpi.setValue(self.stage_spinboxes[stage_idx].value())
            self._update_stage_row_styles()
            self._update_active_dpi_banner()
        finally:
            self._syncing_ui = was_syncing

        if not self._syncing_ui and self.chk_live_apply.isChecked() and self.device.is_connected:
            self._push_dpi_to_hardware()

    def _on_stage_enable_toggled(self, stage_idx: int, checked: bool) -> None:
        if self._syncing_ui:
            return
        # Ensure at least 1 stage remains enabled
        enabled_indices = [i for i, chk in enumerate(self.stage_checks) if chk.isChecked()]
        if not enabled_indices:
            self._syncing_ui = True
            self.stage_checks[stage_idx].setChecked(True)
            self._syncing_ui = False
            return

        if not checked and self.stage_radios[stage_idx].isChecked():
            self.stage_radios[enabled_indices[0]].setChecked(True)

        if self.chk_live_apply.isChecked() and self.device.is_connected:
            self._push_dpi_to_hardware()

    def _choose_stage_color(self, stage_idx: int) -> None:
        r, g, b = self._stage_colors[stage_idx]
        chosen = QColorDialog.getColor(
            QColor(r, g, b),
            self,
            f"{stage_idx + 1}. DPI Kademesi Rengini Seçin",
        )
        if not chosen.isValid():
            return
        new_rgb = (chosen.red(), chosen.green(), chosen.blue())
        self._stage_colors[stage_idx] = new_rgb
        self._colors_dirty = True
        self.stage_color_btns[stage_idx].setStyleSheet(
            f"background-color: rgb({new_rgb[0]}, {new_rgb[1]}, {new_rgb[2]}); "
            "border: 2px solid #cbd5e1; border-radius: 11px; padding: 0px;"
        )
        if self.chk_live_apply.isChecked() and self.device.is_connected:
            try:
                self.device.set_dpi_color(stage_idx, new_rgb[0], new_rgb[1], new_rgb[2])
                self._colors_dirty = False
                self.lbl_status.setText(f"{stage_idx + 1}. kademe rengi güncellendi.")
            except Exception:
                pass

    def _on_rate_pill_clicked(self, rate_hz: int) -> None:
        if self._syncing_ui:
            return
        self._syncing_ui = True
        try:
            self.combo_rate.setCurrentText(f"{rate_hz} Hz")
        finally:
            self._syncing_ui = False

        if self.chk_live_apply.isChecked() and self.device.is_connected:
            try:
                self.device.set_polling_rate(rate_hz)
                self.lbl_status.setText(f"Yoklama oranı {rate_hz} Hz olarak uygulandı.")
                self._refresh_diagnostics_labels()
            except Exception:
                pass

    def _on_combo_rate_changed(self, text: str) -> None:
        if self._syncing_ui or not text:
            return
        try:
            hz = int(text.split()[0])
        except ValueError:
            return
        self._syncing_ui = True
        try:
            if hz in self.rate_pills:
                self.rate_pills[hz].setChecked(True)
        finally:
            self._syncing_ui = False

        if self.chk_live_apply.isChecked() and self.device.is_connected:
            try:
                self.device.set_polling_rate(hz)
                self.lbl_status.setText(f"Yoklama oranı {hz} Hz olarak uygulandı.")
                self._refresh_diagnostics_labels()
            except Exception:
                pass

    def _on_lod_changed(self, _index: int) -> None:
        if self._syncing_ui:
            return
        lod_mm = LOD_1MM if self.combo_lod.currentIndex() == 0 else LOD_2MM
        if self.chk_live_apply.isChecked() and self.device.is_connected:
            try:
                self.device.set_lod(lod_mm)
                self.lbl_status.setText(f"Kalkış mesafesi (LOD) {lod_mm} mm olarak uygulandı.")
                self._refresh_diagnostics_labels()
            except Exception:
                pass

    def _on_debounce_slider_changed(self, value: int) -> None:
        self.lbl_debounce_val.setText(f"{value} ms")
        if self._syncing_ui:
            return
        if not self.slider_debounce.isSliderDown() and self.chk_live_apply.isChecked() and self.device.is_connected:
            self._on_debounce_committed()

    def _on_debounce_committed(self) -> None:
        if self._syncing_ui:
            return
        ms = self.slider_debounce.value()
        if self.chk_live_apply.isChecked() and self.device.is_connected:
            try:
                self.device.set_debounce(ms)
                self.lbl_status.setText(f"Tuş tepki gecikmesi (Debounce) {ms} ms olarak kaydedildi.")
                self._refresh_diagnostics_labels()
            except Exception:
                pass

    def _on_sensor_advanced_changed(self, _checked: bool = False) -> None:
        if self._syncing_ui:
            return
        if self.chk_live_apply.isChecked() and self.device.is_connected:
            try:
                self.device.set_sensor_advanced(
                    angle_snap=self.chk_angle_snap.isChecked(),
                    motion_sync=self.chk_motion_sync.isChecked(),
                    ripple_control=self.chk_ripple_control.isChecked(),
                )
                self.lbl_status.setText("PAW3395 sensör algoritmaları canlı olarak güncellendi.")
            except Exception:
                pass

    def _on_power_sleep_changed(self, *_args) -> None:
        if self._syncing_ui:
            return
        if self.chk_live_apply.isChecked() and self.device.is_connected:
            try:
                sleep_min = int(self.combo_sleep.currentData() or 1)
                move_light_off = self.chk_move_light_off.isChecked()
                self.device.set_power_sleep(
                    sleep_timeout_min=sleep_min,
                    move_light_off=move_light_off,
                )
                self.lbl_status.setText(f"Kablosuz uyku süresi ({sleep_min} dk) güncellendi.")
            except Exception:
                pass

    def _on_lighting_changed(self, *_args) -> None:
        if self._syncing_ui:
            return
        self._lighting_dirty = True
        if self.chk_live_apply.isChecked() and self.device.is_connected:
            try:
                light_mode = int(self.combo_lighting_mode.currentData() or 0)
                light_bright = self.slider_brightness.value()
                active_idx = self.get_selected_stage_index()
                self.device.set_lighting(
                    mode=light_mode,
                    brightness=light_bright,
                    speed=2,
                    color=self._stage_colors[active_idx],
                )
                self._lighting_dirty = False
                self.lbl_status.setText("RGB aydınlatma efekti güncellendi.")
            except Exception:
                pass

    def _on_button_mapping_changed(self, btn_idx: int) -> None:
        if self._syncing_ui:
            return
        button_keys = [
            str(c.currentData() or DEFAULT_BUTTON_KEYS[i])
            for i, c in enumerate(self.button_combos)
        ]
        # GamingMS.exe @ 0x0041b79d safety check: at least one button must remain Left Click
        if "left_click" not in button_keys:
            self._syncing_ui = True
            try:
                left_idx = self.button_combos[btn_idx].findData("left_click")
                if left_idx >= 0:
                    self.button_combos[btn_idx].setCurrentIndex(left_idx)
            finally:
                self._syncing_ui = False
            self.lbl_status.setText("Güvenlik: En az bir tuş 'Sol Tık' olarak atanmış olmalıdır.")
            return

        self._buttons_dirty = True
        if self.chk_live_apply.isChecked() and self.device.is_connected:
            try:
                self.device.set_button_mappings(button_keys)
                self._last_applied_buttons = list(button_keys)
                self._buttons_dirty = False
                self.lbl_status.setText(f"{btn_idx + 1}. tuş ataması güncellendi.")
            except Exception:
                pass

    def _on_live_control_edited(self, *args) -> None:
        if self._syncing_ui:
            return

    def _update_stage_row_styles(self) -> None:
        active_idx = self.get_selected_stage_index()
        for idx, card in enumerate(self.stage_cards):
            target_name = "StageRowActive" if idx == active_idx else "StageRow"
            if card.objectName() != target_name:
                card.setObjectName(target_name)
                card.style().unpolish(card)
                card.style().polish(card)

    def _update_active_dpi_banner(self) -> None:
        active_idx = self.get_selected_stage_index()
        active_dpi = self.stage_spinboxes[active_idx].value()
        self.lbl_active_dpi_display.setText(f"{active_dpi} DPI ({active_idx + 1}. Kademe)")

    def get_selected_stage_index(self) -> int:
        for i, radio in enumerate(self.stage_radios):
            if radio.isChecked():
                return i
        return 0

    def get_stage_enable_mask(self) -> int:
        mask = 0
        for i, chk in enumerate(self.stage_checks):
            if chk.isChecked():
                mask |= (1 << i)
        return mask if mask != 0 else 0x01

    def apply_preset(self, values: List[int]) -> None:
        self._syncing_ui = True
        try:
            for i, val in enumerate(values[:MAX_DPI_STAGES]):
                self.stage_spinboxes[i].setValue(val)
                self.stage_sliders[i].setValue(val)
            active_idx = self.get_selected_stage_index()
            self.spin_dpi.setValue(self.stage_spinboxes[active_idx].value())
            self._update_active_dpi_banner()
        finally:
            self._syncing_ui = False

        self.lbl_status.setText("DPI ön ayarı yüklendi.")
        if self.chk_live_apply.isChecked() and self.device.is_connected:
            self._push_dpi_to_hardware()

    def _push_dpi_to_hardware(self) -> None:
        if not self.device.is_connected:
            return
        try:
            stages = [spin.value() for spin in self.stage_spinboxes]
            active_idx = self.get_selected_stage_index()
            mask = self.get_stage_enable_mask()
            count = bin(mask).count("1")
            self.device.set_dpi_configuration(
                stages=stages,
                active_stage=active_idx,
                stage_count=count,
                enable_mask=mask,
                colors=None,
            )
            self.lbl_status.setText(
                f"Canlı uygulandı: {stages[active_idx]} DPI ({active_idx + 1}. Kademe)"
            )
            self._refresh_diagnostics_labels()
        except Exception as exc:
            self.lbl_status.setText(f"DPI gönderilemedi: {exc}")

    def _poll_live_hardware_events(self) -> None:
        """
        Poll Input Report 0x04 from the mouse every 200ms so physical DPI button presses
        immediately update the active DPI stage in the GUI.
        """
        if not self.device.is_connected:
            return
        try:
            update = self.device.poll_input_report()
        except Exception:
            return

        if not update:
            return

        prev_stage = self.get_selected_stage_index()
        new_stage = update.get("active_stage", prev_stage)
        self._syncing_ui = True
        try:
            if 0 <= new_stage < len(self.stage_radios):
                self.stage_radios[new_stage].setChecked(True)
                self.spin_dpi.setValue(self.stage_spinboxes[new_stage].value())
                self._update_stage_row_styles()
                self._update_active_dpi_banner()

            if "polling_rate" in update:
                rate_hz = update["polling_rate"]
                self.combo_rate.setCurrentText(f"{rate_hz} Hz")
                if rate_hz in self.rate_pills:
                    self.rate_pills[rate_hz].setChecked(True)

            if "lod" in update:
                lod_idx = 0 if update["lod"] == LOD_1MM else 1
                self.combo_lod.setCurrentIndex(lod_idx)

            if "battery_pct" in update:
                self.battery_bar.setValue(update["battery_pct"])
        finally:
            self._syncing_ui = False

        if new_stage != prev_stage:
            active_dpi = self.stage_spinboxes[self.get_selected_stage_index()].value()
            self.lbl_status.setText(
                f"Fare üzerinden DPI değiştirildi: {new_stage + 1}. Kademe ({active_dpi} DPI)"
            )
        self._refresh_diagnostics_labels()

    def refresh_device_state(self) -> None:
        """Connect to the mouse if needed and populate all UI controls with current state."""
        try:
            if not self.device.is_connected:
                self.device.connect()

            mode_str = "Kablolu USB" if self.device.mode == "wired" else "2.4GHz Kablosuz (Dongle)"
            self.lbl_conn_mode.setText(f"Bağlı ({mode_str})")
            self.lbl_conn_mode.setStyleSheet("color: #34d399; font-size: 12px; font-weight: 700;")

            bat = self.device.read_battery()
            self.battery_bar.setValue(bat.percentage)
            self.battery_bar.setToolTip(str(bat))

            settings = self.device.read_settings()
            self._syncing_ui = True
            try:
                stages = list(settings.dpi_stages)
                while len(stages) < MAX_DPI_STAGES:
                    stages.append(DEFAULT_DPI_STAGES[len(stages)])

                for i in range(MAX_DPI_STAGES):
                    self.stage_spinboxes[i].setValue(stages[i])
                    self.stage_sliders[i].setValue(stages[i])
                    is_enabled = bool(settings.stage_enable_mask & (1 << i))
                    self.stage_checks[i].setChecked(is_enabled)

                if settings.dpi_colors:
                    for i, rgb in enumerate(settings.dpi_colors[:MAX_DPI_STAGES]):
                        self._stage_colors[i] = rgb
                        self.stage_color_btns[i].setStyleSheet(
                            f"background-color: rgb({rgb[0]}, {rgb[1]}, {rgb[2]}); "
                            "border: 2px solid #cbd5e1; border-radius: 11px; padding: 0px;"
                        )

                active_idx = max(0, min(MAX_DPI_STAGES - 1, settings.active_stage))
                self.stage_radios[active_idx].setChecked(True)
                self.spin_dpi.setValue(stages[active_idx])
                self._update_stage_row_styles()
                self._update_active_dpi_banner()

                self.combo_rate.setCurrentText(f"{settings.polling_rate} Hz")
                if settings.polling_rate in self.rate_pills:
                    self.rate_pills[settings.polling_rate].setChecked(True)

                lod_idx = 0 if settings.lod == LOD_1MM else 1
                self.combo_lod.setCurrentIndex(lod_idx)

                self.slider_debounce.setValue(settings.debounce_ms)
                self.lbl_debounce_val.setText(f"{settings.debounce_ms} ms")

                self.chk_motion_sync.setChecked(settings.motion_sync)
                self.chk_angle_snap.setChecked(settings.angle_snap)
                self.chk_ripple_control.setChecked(settings.ripple_control)

                sleep_idx = self.combo_sleep.findData(settings.sleep_timeout_min)
                if sleep_idx >= 0:
                    self.combo_sleep.setCurrentIndex(sleep_idx)
                self.chk_move_light_off.setChecked(settings.move_light_off)

                light_idx = self.combo_lighting_mode.findData(settings.lighting_mode)
                if light_idx >= 0:
                    self.combo_lighting_mode.setCurrentIndex(light_idx)
                self.slider_brightness.setValue(settings.lighting_brightness)

                if settings.button_mappings:
                    for i, key_name in enumerate(settings.button_mappings[:6]):
                        c_idx = self.button_combos[i].findData(key_name)
                        if c_idx >= 0:
                            self.button_combos[i].setCurrentIndex(c_idx)
                    self._last_applied_buttons = list(settings.button_mappings[:6])
                self._buttons_dirty = False
                self._lighting_dirty = False
                self._colors_dirty = False
            finally:
                self._syncing_ui = False

            self._refresh_diagnostics_labels(bat_override=bat, settings_override=settings)
            self.lbl_status.setText("Fare ayarları ve donanım bilgileri başarıyla okundu.")
            self.btn_apply.setEnabled(True)

        except DeviceError as exc:
            self.lbl_conn_mode.setText("Bağlı Değil")
            self.lbl_conn_mode.setStyleSheet("color: #f87171; font-size: 12px; font-weight: 700;")
            self.battery_bar.setValue(0)
            self.lbl_status.setText(str(exc))

    def _refresh_diagnostics_labels(self, bat_override=None, settings_override=None) -> None:
        if not self.device.is_connected:
            return
        try:
            hw_info = self.device.get_hardware_info()
            for key, val in hw_info.items():
                if key in self.hw_labels:
                    self.hw_labels[key].setText(str(val))

            bat = bat_override or self.device.read_battery()
            settings = settings_override or self.device.read_settings()

            if "live_battery" in self.hw_labels:
                charge_txt = "Şarj Oluyor / USB Gücü" if bat.is_charging else "Pil ile Çalışıyor"
                self.hw_labels["live_battery"].setText(
                    f"%{bat.percentage} ({charge_txt}, ~{bat.voltage_mv} mV)"
                )
            if "live_settings_summary" in self.hw_labels:
                self.hw_labels["live_settings_summary"].setText(
                    f"{settings.active_dpi} DPI (Kademe {settings.active_stage + 1}) | "
                    f"{settings.polling_rate} Hz | LOD {settings.lod} mm | Debounce {settings.debounce_ms} ms"
                )
        except Exception:
            pass

    def update_battery_only(self) -> None:
        """Lightweight periodic battery telemetry check."""
        if not self.device.is_connected:
            return
        try:
            bat = self.device.read_battery()
            self.battery_bar.setValue(bat.percentage)
            self.battery_bar.setToolTip(str(bat))
            if "live_battery" in self.hw_labels:
                charge_txt = "Şarj Oluyor / USB Gücü" if bat.is_charging else "Pil ile Çalışıyor"
                self.hw_labels["live_battery"].setText(
                    f"%{bat.percentage} ({charge_txt}, ~{bat.voltage_mv} mV)"
                )
        except DeviceError:
            pass

    def apply_changes(self) -> None:
        """Write all configured settings from UI controls to the Fevell Z1 hardware."""
        try:
            if not self.device.is_connected:
                self.device.connect()

            stages = [spin.value() for spin in self.stage_spinboxes]
            active_idx = self.get_selected_stage_index()
            mask = self.get_stage_enable_mask()
            stage_count = bin(mask).count("1")

            rate_str = self.combo_rate.currentText().split()[0]
            rate_hz = int(rate_str)
            lod_mm = LOD_1MM if self.combo_lod.currentIndex() == 0 else LOD_2MM
            debounce_ms = self.slider_debounce.value()

            sleep_min = int(self.combo_sleep.currentData() or 1)
            move_light_off = self.chk_move_light_off.isChecked()
            light_mode = int(self.combo_lighting_mode.currentData() or 0)
            light_bright = self.slider_brightness.value()
            button_keys = [str(c.currentData() or DEFAULT_BUTTON_KEYS[i]) for i, c in enumerate(self.button_combos)]
            if "left_click" not in button_keys:
                button_keys[0] = "left_click"

            self.device.set_debounce(debounce_ms)
            self.device.set_dpi_configuration(
                stages=stages,
                active_stage=active_idx,
                stage_count=stage_count,
                enable_mask=mask,
                colors=self._stage_colors if self._colors_dirty else None,
            )
            self._colors_dirty = False
            self.device.set_polling_rate(rate_hz)
            self.device.set_lod(lod_mm)
            self.device.set_sensor_advanced(
                angle_snap=self.chk_angle_snap.isChecked(),
                motion_sync=self.chk_motion_sync.isChecked(),
                ripple_control=self.chk_ripple_control.isChecked(),
            )
            self.device.set_power_sleep(
                sleep_timeout_min=sleep_min,
                move_light_off=move_light_off,
            )
            if self._lighting_dirty:
                self.device.set_lighting(
                    mode=light_mode,
                    brightness=light_bright,
                    speed=2,
                    color=self._stage_colors[active_idx],
                )
                self._lighting_dirty = False

            if self._buttons_dirty or button_keys != self._last_applied_buttons:
                self.device.set_button_mappings(button_keys)
                self._last_applied_buttons = list(button_keys)
                self._buttons_dirty = False

            active_dpi = stages[active_idx]
            self._update_active_dpi_banner()
            self._refresh_diagnostics_labels()
            self.lbl_status.setText(
                f"Ayarlar başarıyla kaydedildi: {active_dpi} DPI (Kademe {active_idx + 1}), {rate_hz} Hz, {lod_mm} mm LOD"
            )
            QMessageBox.information(
                self,
                "Ayarlar Kaydedildi",
                f"Yeni ayarlar Fevell Z1 fareye başarıyla aktarıldı!\n\n"
                f"• Aktif DPI: {active_dpi} DPI ({active_idx + 1}. Kademe)\n"
                f"• Yoklama Oranı: {rate_hz} Hz\n"
                f"• Kalkış Mesafesi (LOD): {lod_mm} mm\n"
                f"• Tuş Gecikmesi (Debounce): {debounce_ms} ms\n"
                f"• Motion Sync: {'Açık' if self.chk_motion_sync.isChecked() else 'Kapalı'}",
            )
        except Exception as exc:
            self.lbl_status.setText(f"Hata: {exc}")
            QMessageBox.critical(self, "Donanım Kayıt Hatası", str(exc))

    def _on_factory_reset_clicked(self) -> None:
        reply = QMessageBox.question(
            self,
            "Fabrika Ayarlarına Sıfırla",
            "Fevell Z1 farenin tüm DPI, sensör ve tuş ayarlarını fabrika varsayılanlarına sıfırlamak istediğinize emin misiniz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.device.factory_reset()
            self.refresh_device_state()
            self.lbl_status.setText("Fare fabrika ayarlarına sıfırlandı.")
        except Exception as exc:
            QMessageBox.critical(self, "Sıfırlama Hatası", str(exc))

    def _on_emergency_recovery_shortcut(self) -> None:
        """
        Emergency recovery handler triggered by Ctrl+Shift+R keyboard shortcut.
        Restores mouse hardware without requiring any mouse clicks.
        """
        try:
            self.device.factory_reset()
            self.refresh_device_state()
            self.lbl_status.setText("Acil kurtarma: Fare fabrika ayarlarına sıfırlandı (Ctrl+Shift+R).")
            QMessageBox.information(
                self,
                "Acil Kurtarma Başarılı",
                "Klavye kısayolu (Ctrl+Shift+R) ile fare başarıyla fabrika ayarlarına sıfırlandı.\n"
                "Tuş atamaları ve sensör varsayılan durumuna getirildi.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Kurtarma Hatası", f"Sıfırlama yapılamadı: {exc}")

    def test_hardware_communication(self) -> None:
        """Verify live bidirectional feature report exchange with the mouse."""
        try:
            if not self.device.is_connected:
                self.device.connect()
            ok = self.device.send_heartbeat()
            online = self.device.is_device_online()
            hw_info = self.device.get_hardware_info()
            if ok and online:
                msg = (
                    f"Fevell Z1 Donanım İletişimi Başarılı!\n\n"
                    f"• Aygıt Düğümü: {hw_info.get('hidraw_node')}\n"
                    f"• Bağlantı: {hw_info.get('connection_type')}\n"
                    f"• Firmware Handshake: {hw_info.get('firmware_handshake')}\n"
                    f"• Durum Raporu (0x05): {hw_info.get('status_report_05')}"
                )
                self.lbl_status.setText("Donanım iletişim testi başarılı.")
                QMessageBox.information(self, "Donanım Testi Başarılı", msg)
            else:
                self.lbl_status.setText("Donanım yanıt vermedi.")
                QMessageBox.warning(self, "Donanım Testi", "Fare şu anda uyku modunda veya yanıt vermiyor.")
        except Exception as exc:
            QMessageBox.critical(self, "İletişim Hatası", str(exc))

    def copy_diagnostics_to_clipboard(self) -> None:
        """Copy all hardware diagnostics to system clipboard."""
        lines = ["=== M-Control Donanım & Teşhis Raporu ==="]
        for key, lbl in self.hw_labels.items():
            lines.append(f"{key}: {lbl.text()}")
        text = "\n".join(lines)
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        self.lbl_status.setText("Donanım ve teşhis bilgileri panoya kopyalandı.")
        QMessageBox.information(self, "Kopyalandı", "Donanım bilgileri panoya kopyalandı.")


def main() -> int:
    """Entry point for `mcontrol-gui`."""
    app = QApplication(sys.argv)
    app.setApplicationName("M-Control")
    app.setDesktopFileName("m-control")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
