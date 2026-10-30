# M-Control

Linux sistemler için geliştirilmiş; doğrudan donanım düzeyinde iletişim kuran, yerel (native) mouse yapılandırma ve kontrol yazılımı. 

Wine veya Windows emülasyonuna ihtiyaç duymadan, doğrudan çekirdek HID (`hidraw`) katmanı üzerinden cihazla iki yönlü haberleşir.

---

## Desteklenen Donanım Mimarisi

Bu uygulama belirli bir markaya bağımlı olmaksızın, aşağıdaki donanım bileşenleri ve kontrolcü mimarisini temel alan fareleri destekler:

- **Optik Sensör:** PixArt PAW3395 (50 – 26.000 DPI, 650 IPS, 50G)
- **Mikrodenetleyici (MCU) / RF Çözümü:** Beken BK3633 / Compx kablosuz çözümü
- **İletişim Protokolü:** 32-bayt Feature Report (Report ID `0x06` & `0x05`) ve Asenkron Durum Geri Bildirimi (`0x04`)
- **Desteklenen USB VID / PID Tanımlayıcıları:**
  - Kablolu USB Modu: `04F3:026E`, `3554:F58A`
  - 2.4 GHz Standart Alıcı Modu: `04F3:026F`, `3554:F58B`, `32C2:0018`
  - 4K / 8K Yüksek Hızlı Kablosuz Alıcı Modu: `04F3:026D`

---

## Donanım Güvenliği & Test Mimarisi

Donanımla doğrudan USB HID seviyesinde bayt dizileri üzerinden haberleşen yazılımlarda hatalı bir bayt cihazın kilitlenmesine (brick) veya tuşların yanıt vermemesine yol açabilir. M-Control, bu riskleri ortadan kaldırmak için çok katmanlı güvenlik mekanizmalarına sahiptir:

### 1. Sanal Cihaz Doğrulaması (`MockHIDDevice`)
Tüm komut paketleri, sağlama toplamları (checksum) ve durum ayrıştırıcıları önce bellekte çalışan sanal bir donanım üzerinde simüle edilir. Fiziksel donanıma doğrulanmamış hiçbir paket iletilmez.

### 2. Sol Tık Koruma Kilidi (Left-Click Lock Guard)
Kullanıcının tuş atamaları sırasında tüm butonları yanlışlıkla başka fonksiyonlara atayıp fareyi tıklamasız bırakmasını engellemek için, tuş haritasında daima en az bir adet `Sol Tık` (Left Click) fonksiyonunun bulunması zorunlu kılınmıştır.

### 3. Akıllı Değişiklik Takibi ("Dirty Buffer" Yönetimi)
Her kaydetme işleminde farenin tüm Flash belleği körlemesine yeniden yazılmaz. Yalnızca kullanıcının gerçekten değiştirdiği alt sistem paketleri (DPI, LOD, tuş veya aydınlatma) gönderilerek donanım yıpranması ve kilitlenmeler önlenir.

### 4. Acil Durum Fabrika Ayarlarına Sıfırlama (Klavye ile Kurtarma)
Olası bir kilitlenmede veya farenin tıklamayı reddettiği olağanüstü durumlarda, fareye hiç dokunmadan cihazı fabrika ayarlarına döndürebilirsiniz:
- **Terminalden (CLI):**
  ```bash
  mcontrol reset --force
  ```
- **Grafik Arayüz Açıkken (GUI):**
  Klavyeden `Ctrl + Shift + R` kısayoluna basarak acil durum sıfırlamasını tetikleyebilirsiniz.

---

## Öne Çıkan Özellikler

- **Donanım Düzeyinde Doğrudan İletişim:** Özel Windows sürücüsüne veya Wine katmanına gerek kalmadan yerel Linux HID sürücüsü ile çalışır.
- **Dinamik Bağlantı Algılama:** Kablolu USB, 2.4 GHz kablosuz ve 4K alıcı modları arasında geçiş yapıldığında aktif arayüzü otomatik algılar ve terfi ettirir.
- **Canlı ve Çift Yönlü Senkronizasyon (Input Report 0x04):** Fare üzerindeki fiziksel DPI tuşuna basıldığında arayüzdeki aktif kademe ve göstergeler anında güncellenir.
- **Kapsamlı DPI Yönetimi:**
  - 6 kademeli bağımsız DPI ayarı (50 – 26.000 DPI, 50 DPI adımlarla).
  - İstenen kademeleri devre dışı bırakabilme / etkinleştirebilme (kademe maskesi).
  - Her kademe için bağımsız 24-bit RGB gösterge rengi seçimi.
  - Hızlı profil şablonları (Espor, Varsayılan, Maksimum).
- **Sensör & Performans İnce Ayarları:**
  - **Yoklama Hızı (Polling Rate):** 125 Hz, 250 Hz, 500 Hz, 1000 Hz.
  - **Kalkış Mesafesi (LOD):** 1 mm (Rekabetçi / Düşük) veya 2 mm (Standart).
  - **Tuş Gecikmesi (Debounce):** 0 – 30 ms hassas gecikme ayarı.
  - **PAW3395 Sensör Algoritmaları:** Motion Sync, Angle Snapping (Açı Düzeltme) ve Ripple Control (Dalgalanma Önleme).
- **Güç Yönetimi & Aydınlatma:**
  - Kablosuz uyku süresi zamanlayıcısı (1 – 30 dakika).
  - Hareket halinde LED aydınlatmayı otomatik kapatma (pil tasarruf modu).
  - RGB ışıklandırma modları (Kapalı, Sabit, Nefes Alma, Gökkuşağı) ve 4 kademeli parlaklık ayarı.
- **Tuş Haritalama:**
  - 6 adet programlanabilir fiziksel tuş ataması.
  - Donanım güvenliği: Sol tık koruma kilidi.
- **Çift Arayüz Desteği:**
  - **Modern Qt6 GUI:** Karanlık tema, gerçek zamanlı teşhis paneli, acil kurtarma kısayolu (`Ctrl+Shift+R`) ve anında canlı uygulama seçeneği.
  - **Gelişmiş CLI:** Komut satırından ayar değiştirme, acil kurtarma (`mcontrol reset --force`) ve Waybar/Polybar durum çubukları için pil telemetrisi (`mcontrol battery`).

---

## Kurulum

### 1. udev Kuralları (Root Yetkisi Olmadan Donanım Erişimi)

Cihaza `sudo` gereksinimi olmadan erişebilmek için udev kuralını sisteme kopyalayın ve kuralları yenileyin:

```bash
sudo cp 70-m-control.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### 2. Ortam Hazırlığı ve Kurulum

Sanal ortam (venv) oluşturup uygulamayı kurun:

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e .
```

---

## Kullanım

### Grafiksel Arayüz (GUI)

Uygulama arayüzünü başlatmak için:

```bash
mcontrol-gui
```
*(Fare yanıt vermezse arayüz açıkken klavyeden `Ctrl + Shift + R` ile fabrika ayarlarına sıfırlayabilirsiniz.)*

### Komut Satırı Arayüzü (CLI)

Betikler, oyun başlatma komutları veya durum çubukları için:

```bash
# Donanım ve ayar durumunu tam detaylı listeleme
mcontrol status

# Durum çubuğu (Waybar / Polybar) için pil yüzdesi
mcontrol battery
mcontrol battery --raw

# DPI ayarı (aktif kademe veya belirli bir kademe)
mcontrol set-dpi 1600
mcontrol set-dpi 800 --stage 1

# Yoklama hızını (Hz) değiştirme
mcontrol set-rate 1000

# Kalkış mesafesini (LOD) değiştirme (1 veya 2 mm)
mcontrol set-lod 1

# Tuş gecikmesini (Debounce) ayarlama (0 - 30 ms)
mcontrol set-debounce 4

# Acil Kurtarma: Fare tıklamıyorsa fareye dokunmadan fabrika ayarlarına sıfırlama
mcontrol reset --force
```

---

## Testler

Projenin test paketini çalıştırmak için:

```bash
pytest -v
```

---

## Lisans

Bu proje [MIT Lisansı](LICENSE) kapsamında dağıtılmaktadır.
