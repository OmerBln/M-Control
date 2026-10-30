"""Command-line interface for M-Control mouse configuration."""

import argparse
import sys
from typing import Optional

from mcontrol.core.base import BaseMouseDriver
from mcontrol.core.device import discover_mouse
from mcontrol.core.constants import (
    DEBOUNCE_MAX_MS,
    DEBOUNCE_MIN_MS,
    MAX_DPI_STAGES,
    POLLING_RATE_MAP,
)


def get_connected_device() -> BaseMouseDriver:
    """Discover and return connected mouse driver or exit with friendly error."""
    dev = discover_mouse()
    if not dev:
        print("Hata: Desteklenen bir fare bulunamadı veya erişim yetkisi yok.", file=sys.stderr)
        print("İpucu: Fare takılıysa udev kurallarının (/etc/udev/rules.d/70-m-control.rules) kurulu olduğundan emin olun.", file=sys.stderr)
        sys.exit(1)
    return dev


def cmd_status(dev: BaseMouseDriver, args):
    """Print complete mouse status."""
    if dev.mode == "wired":
        mode_tr = "Kablolu USB"
    elif dev.mode == "dongle_4k":
        mode_tr = "4K/8K Kablosuz Alıcı"
    elif dev.mode == "dongle":
        mode_tr = "2.4GHz Kablosuz"
    else:
        mode_tr = "Bilinmiyor"
    print(f"=== {dev.capabilities.name} Durumu ===")
    print(f"Bağlantı Modu : {mode_tr}")

    try:
        bat = dev.read_battery()
        charging = " (Şarj Oluyor)" if bat.is_charging else ""
        print(f"Pil Durumu    : %{bat.percentage} [{bat.voltage_mv} mV]{charging}")
    except Exception as e:
        print(f"Pil Durumu    : Okunamadı ({e})")

    try:
        settings = dev.read_settings()
        print(f"Yoklama Hızı  : {settings.polling_rate} Hz")
        print(f"Kalkış (LOD)  : {settings.lod} mm")
        print(f"Debounce      : {settings.debounce_ms} ms")
        print(f"Aktif DPI     : Kademe {settings.active_stage + 1} ({settings.active_dpi} DPI)")
        print("DPI Kademeleri:")
        mask = getattr(settings, "stage_enable_mask", (1 << settings.stage_count) - 1)
        for idx, dpi_val in enumerate(settings.dpi_stages):
            if mask & (1 << idx):
                mark = "-> " if idx == settings.active_stage else "   "
                print(f"  {mark}Kademe {idx + 1}: {dpi_val} DPI")
    except Exception as e:
        print(f"Ayar Bilgisi  : Okunamadı ({e})")


def cmd_battery(dev: BaseMouseDriver, args):
    """Print only battery percentage for status bars (Waybar, Polybar, etc.)."""
    try:
        bat = dev.read_battery()
        if args.raw:
            print(bat.percentage)
        else:
            state = "⚡" if bat.is_charging else "🔋"
            print(f"{state} %{bat.percentage}")
    except Exception as e:
        print("N/A", file=sys.stderr)
        sys.exit(1)


def cmd_set_dpi(dev: BaseMouseDriver, args):
    """Set mouse DPI."""
    dpi = args.dpi
    caps = dev.capabilities
    if not (caps.min_dpi <= dpi <= caps.max_dpi):
        print(f"Hata: DPI {caps.min_dpi} ile {caps.max_dpi} arasında olmalıdır.", file=sys.stderr)
        sys.exit(1)

    stage = args.stage - 1 if args.stage is not None else None
    if stage is not None and not (0 <= stage < caps.max_dpi_stages):
        print(f"Hata: Kademe numarası 1 ile {caps.max_dpi_stages} arasında olmalıdır.", file=sys.stderr)
        sys.exit(1)

    if dev.set_dpi(dpi, stage_index=stage):
        target = f"Kademe {args.stage}" if args.stage else "Aktif kademe"
        print(f"Başarılı: {target} DPI değeri {dpi} olarak ayarlandı.")
    else:
        print("Hata: DPI uygulanamadı.", file=sys.stderr)
        sys.exit(1)


def cmd_set_rate(dev: BaseMouseDriver, args):
    """Set mouse polling rate."""
    rate = args.rate
    if rate not in dev.capabilities.supported_polling_rates:
        rates_str = ", ".join(str(r) for r in dev.capabilities.supported_polling_rates)
        print(f"Hata: Geçersiz yoklama hızı. Desteklenen değerler: {rates_str}", file=sys.stderr)
        sys.exit(1)

    if dev.set_polling_rate(rate):
        print(f"Başarılı: Yoklama hızı {rate} Hz olarak ayarlandı.")
    else:
        print("Hata: Yoklama hızı uygulanamadı.", file=sys.stderr)
        sys.exit(1)


def cmd_set_lod(dev: BaseMouseDriver, args):
    """Set lift-off distance."""
    lod = args.lod
    if lod not in (1, 2):
        print("Hata: LOD değeri 1 (1mm) veya 2 (2mm) olmalıdır.", file=sys.stderr)
        sys.exit(1)

    if dev.set_lod(lod):
        print(f"Başarılı: Kalkış mesafesi (LOD) {lod} mm olarak ayarlandı.")
    else:
        print("Hata: LOD ayarlanamadı.", file=sys.stderr)
        sys.exit(1)


def cmd_set_debounce(dev: BaseMouseDriver, args):
    """Set debounce time."""
    ms = args.ms
    if not (DEBOUNCE_MIN_MS <= ms <= DEBOUNCE_MAX_MS):
        print(
            f"Hata: Debounce süresi {DEBOUNCE_MIN_MS} ile {DEBOUNCE_MAX_MS} ms arasında olmalıdır.",
            file=sys.stderr,
        )
        sys.exit(1)

    if dev.set_debounce(ms):
        print(f"Başarılı: Tıklama gecikmesi (Debounce) {ms} ms olarak ayarlandı.")
    else:
        print("Hata: Debounce ayarlanamadı.", file=sys.stderr)
        sys.exit(1)


def cmd_reset(dev: BaseMouseDriver, args):
    """
    Emergency recovery and factory reset command.
    Restores mouse hardware to factory default settings without requiring mouse clicks.
    
    # Protocol: GamingMS.exe Feature Report 0x06 Cmd 0x0F & Default Mapping (2026-10-30)
    """
    if not args.force:
        print("Uyarı: Bu işlem farenin tüm tuş, DPI ve sensör ayarlarını fabrika varsayılanlarına döndürür.", file=sys.stderr)
        print("Onaylamak için '--force' bayrağını kullanın: mcontrol reset --force", file=sys.stderr)
        sys.exit(1)

    print("Kurtarma işlemi başlatılıyor: Donanım fabrika ayarlarına sıfırlanıyor...")
    try:
        if dev.factory_reset():
            print("Başarılı: Fare donanımı ve tuş atamaları fabrika ayarlarına döndürüldü.")
            print("Tuşlar (Sol Tık, Sağ Tık, vb.) ve sensör varsayılan durumuna geri getirildi.")
        else:
            print("Hata: Fabrika ayarlarına sıfırlama başarısız oldu.", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Hata: Sıfırlama sırasında istisna oluştu ({e})", file=sys.stderr)
        sys.exit(1)


def main():
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="mcontrol",
        description="M-Control: Linux Mouse Configuration Utility",
    )
    subparsers = parser.add_subparsers(dest="command", help="Komutlar")

    # status
    p_status = subparsers.add_parser("status", help="Fare durumunu ve ayarlarını gösterir")
    p_status.set_defaults(func=cmd_status)

    # battery
    p_bat = subparsers.add_parser("battery", help="Pil durumunu gösterir (Waybar/Polybar uyumlu)")
    p_bat.add_argument("--raw", action="store_true", help="Sadece yüzde sayısını yazdırır")
    p_bat.set_defaults(func=cmd_battery)

    # set-dpi
    p_dpi = subparsers.add_parser("set-dpi", help="DPI değerini ayarlar")
    p_dpi.add_argument("dpi", type=int, help="DPI değeri (50 - 26000)")
    p_dpi.add_argument(
        "--stage",
        type=int,
        default=None,
        help=f"Kademe numarası (1-{MAX_DPI_STAGES}, varsayılan: aktif kademe)",
    )
    p_dpi.set_defaults(func=cmd_set_dpi)

    # set-rate
    p_rate = subparsers.add_parser("set-rate", help="Yoklama hızını (Hz) ayarlar")
    p_rate.add_argument("rate", type=int, choices=[125, 250, 500, 1000], help="Yoklama hızı (Hz)")
    p_rate.set_defaults(func=cmd_set_rate)

    # set-lod
    p_lod = subparsers.add_parser("set-lod", help="Kalkış mesafesini (LOD) ayarlar")
    p_lod.add_argument("lod", type=int, choices=[1, 2], help="Kalkış mesafesi mm (1 veya 2)")
    p_lod.set_defaults(func=cmd_set_lod)

    # set-debounce
    p_deb = subparsers.add_parser("set-debounce", help="Tıklama gecikmesini (Debounce) ayarlar")
    p_deb.add_argument("ms", type=int, help=f"Milisaniye ({DEBOUNCE_MIN_MS} - {DEBOUNCE_MAX_MS})")
    p_deb.set_defaults(func=cmd_set_debounce)

    # reset (emergency recovery)
    p_reset = subparsers.add_parser("reset", help="Acil durum kurtarma: Fareyi klavyeden fabrika ayarlarına döndürür")
    p_reset.add_argument("--force", action="store_true", help="Onay sormadan sıfırlamayı gerçekleştirir")
    p_reset.set_defaults(func=cmd_reset)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    dev = get_connected_device()
    try:
        args.func(dev, args)
    finally:
        dev.close()


if __name__ == "__main__":
    main()

