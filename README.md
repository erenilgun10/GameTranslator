# GameTranslator

RPG Maker **MV ve MZ** oyunlarının metinlerini dosya üzerinden çevirmek için
Windows masaüstü uygulaması ve komut satırı aracı. Oyunu tarar, çevirileri ayrı
bir projede saklar ve incelenmiş çevirilerden geri alınabilir bir yama oluşturur.

Manuel çeviri çevrimdışı çalışır; API anahtarı, GPU veya model indirmesi gerekmez.
DeepL isteğe bağlıdır. Python 3.12+, Tkinter ve SQLite kullanılır; uygulamanın
çalışma zamanı için ek pip bağımlılığı yoktur.

## Windows'ta çalıştırma

1. [Releases](https://github.com/erenilgun10/GameTranslator/releases) sayfasından
   Windows ZIP paketini ve `.sha256` dosyasını indir.
2. ZIP'in SHA-256 değerini `Get-FileHash` ile hesaplayıp `.sha256` dosyasındaki
   değerle karşılaştır. ZIP'in tamamını bir klasöre çıkar.
3. `GameTranslator.exe` dosyasını çalıştır. Hazır pakette Python kurulumu gerekmez.

İsteğe bağlı klasör kurulumu için çıkarılan paketin içindeki
`Install-GameTranslator.ps1` betiğini kullanabilirsin. Varsayılan hedef
`%LOCALAPPDATA%\Programs\GameTranslator` klasörüdür; mevcut bir kurulumun üzerine
yazılmaz. Kaldırmak için uygulama klasörünü silebilirsin; çeviri projeleri ve
yedekler ayrı tutulur. Paket imzasız olduğundan Windows SmartScreen uyarısı çıkabilir.

## Nasıl kullanılır?

1. **Oyun seç ve tara:** İzin sahibi olduğun MV/MZ oyun klasörünü seç. MV'nin
   `www` yerleşimi otomatik algılanır. Tarama oyun dosyalarını değiştirmez.
2. **Yeni proje:** Kaynak/hedef dil kodlarını seç ve oyunun dışında yeni bir proje
   klasörü oluştur. Metinler, çeviriler ve geçmiş SQLite içinde saklanır;
   daha sonra **Proje aç** ile devam edebilirsin.
3. **Çevir ve kaydet:** Bir satır seç, çevirisini yaz, kontrol ettikten sonra
   **İncelendi** işaretle ve **Kaydet**. `\V[1]`, `\N[2]`, `%1` gibi oyun
   kodlarını ve sıralarını koru. **Kilitli**, kaydı otomatik çeviriden korur.
4. **Filtre, geçmiş ve bellek:** Metin/durum filtresiyle ara; önceki kayıtları
   **Geçmiş** ile gör. Onaylı çevirilerden **Bellekten getir** ile yararlanabilir,
   **Glossary** üzerinden terim karşılıkları tanımlayabilirsin. Bellekten gelen
   metni inceleyip ayrıca kaydet. Hedef dillerin çevirileri, belleği ve terimleri
   aynı projede ayrı tutulur; kaynak dil proje oluşturulurken belirlenir.
5. **Patch hazırla:** Yalnızca incelenmiş çevirilerden yeni bir yama klasörü
   oluşturur ve değişiklik önizlemesini gösterir. Bu adım oyuna yazmaz.
6. **Patch uygula:** Oyunu ve dosyalarını düzenleyen diğer araçları kapat.
   Yamayı seç, değişiklikleri incele ve oyun/yama klasörlerinin dışında yeni bir
   yedek klasörü belirleyerek onayla. Dosyalar ve kaynak hash'leri doğrulanır;
   özgün dosyalar yedeklendikten sonra yama uygulanır.
7. **Geri al:** İlgili yedek klasörünü seçerek özgün dosyaları birebir geri yükle.
   Çakışan oyun değişikliği veya bozuk yedek varsa işlem reddedilir. Kesintiye
   uğrayan uygulamalarda da ilgili yedeğin işlem kaydı üzerinden geri alabilirsin.

Satır, proje veya hedef dil değiştirirken, yama hazırlarken ve kapatırken
kaydedilmemiş değişiklikler için kaydet/atla/iptal seçeneği sunulur. Filtre satırı
gizlese de **Kaydet** düzenlediğin satıra aittir. Çalışan işlem varken kapatma,
sonucun kaydedilmesini bekler. Oyun güncellendiğinde yeniden tara ve yeni proje
oluştur; eski çeviriler otomatik olarak yeni sürüme taşınmaz.

## İsteğe bağlı DeepL çevirisi

`DEEPL_API_KEY` ortam değişkenini uygulamayı başlatmadan önce tanımla. Anahtarı
Git'e, proje dosyalarına veya komut satırı argümanlarına yazma. Anahtar yoksa
manuel çeviri ve yama akışı kullanılmaya devam eder.

**DeepL ile çevir** seçili metni, **Toplu başlat/devam** bekleyen metinleri açık
onayından sonra DeepL'e gönderir. Dış servise veri aktarılır ve ücret doğabilir.
**Duraklat**, sürmekte olan yanıtı kaydeder ve sonraki isteğe geçmeden durur;
aynı iş daha sonra devam ettirilebilir. Kilitli kayıtların üzerine yazılmaz.

Raporlar para tutarı yerine sağlayıcının bildirdiği karakter sayısını gösterir.
Eksik kullanım bilgisi veya belirsiz ağ hatası sıfır ücret anlamına gelmez;
CLI raporunda bilinmeyen kullanım `null` olarak gösterilir. Yeniden denemeden
önce gerekiyorsa sağlayıcı hesabını kontrol et.

## Kaynak koddan kurulum

Python 3.12 veya üzeri ve Tkinter gerekir. PowerShell'de depo klasöründe:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m game_translator gui
```

## Komut satırı

Hazır pakette `GameTranslator-CLI.exe`, kaynak kurulumda
`.\.venv\Scripts\python.exe -m game_translator` kullanılır. Her komutun
`--help` seçeneği vardır. Aşağıdaki büyük harfli adlar yer tutucudur; gerçek
klasörleri ve `status` / `jobs` çıktısından aldığın kimlikleri kullan.

```text
GameTranslator-CLI.exe scan GAME
GameTranslator-CLI.exe new GAME PROJECT --source EN --target TR
GameTranslator-CLI.exe status PROJECT
GameTranslator-CLI.exe edit PROJECT SEGMENT_ID "çeviri" --reviewed --lock
GameTranslator-CLI.exe glossary PROJECT Potion İksir
GameTranslator-CLI.exe status PROJECT --target DE
GameTranslator-CLI.exe translate PROJECT --allow-cloud
GameTranslator-CLI.exe jobs PROJECT
GameTranslator-CLI.exe translate PROJECT --job JOB_ID --allow-cloud
GameTranslator-CLI.exe stage PROJECT PATCH_DIRECTORY
GameTranslator-CLI.exe apply GAME PATCH_DIRECTORY NEW_BACKUP_DIRECTORY --approve
GameTranslator-CLI.exe restore GAME BACKUP_DIRECTORY --approve
```

## Destek kapsamı

| İçerik | Davranış |
|---|---|
| MV/MZ kök klasörü ve MV `www` | JSON dosyalarından metin çıkarma, yama ve geri alma |
| Haritalar ve olaylar | Görünen harita adı, diyalog, seçenek, kayan metin ve desteklenen karakter metinleri |
| Karakterler, sınıflar, eşyalar, silahlar, zırhlar | Desteklenen ad, açıklama, takma ad ve profil alanları |
| Yetenekler, durumlar, düşmanlar | Adlar, açıklamalar ve desteklenen mesajlar |
| System | Oyun başlığı, para birimi, tür adları ve bilinen terim grupları |
| JavaScript, HTML, eklenti komutları ve bilinmeyen şemalar | Atlanır; genel metin değiştirme yapılmaz |
| Görseller, şifreli arşivler, ikili dosyalar ve diğer motorlar | Desteklenmez |

JSON girdileri UTF-8 olmalı; BOM kabul edilir ve dosya sınırı 32 MiB'dır.
Geçersiz JSON, tekrarlanan anahtarlar, güvenli olmayan yollar ve symlink/junction
yerleşimleri reddedilir. OCR, oyun üstü overlay ve yerel AI bu sürümde bulunmaz.

`examples/` altındaki örnekler özgün sentetik metin ve motor işaretçisi içerir;
oynanabilir oyun veya RPG Maker çalışma zamanı değildir. Yama denemek için
örneği uygulama klasörünün dışına kopyala ve proje/yama/yedeği ayrı oluştur.

Bu sürüm bir **1.0 sürüm adayıdır**. Sentetik testler her oyunda uyumluluk
garantisi vermez. Gerçek oyunlarda oynanış ve ekran taşması, temiz Windows
istemcisi ve canlı DeepL kabulü henüz tamamlanmamıştır. Yalnız kullanma ve
değiştirme iznin olan oyunlarla çalış; proje ve yedekler oyun metni içerebilir.

## Geliştirme ve Windows paketi

Sabitlenmiş test/paketleme araçlarını kurup testleri çalıştırmak için:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pytest -q
```

Windows GUI/CLI paketi oluşturmak için:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

Betik testleri çalıştırır, PyInstaller ile GUI/CLI üretir, sentetik MV/MZ
akışlarını kontrol eder ve `release/` altında ZIP ile SHA-256 dosyası oluşturur.
GitHub Actions kaynak testlerini Windows/Linux ve Python 3.12/3.13 üzerinde
çalıştırır. Ayrı Windows paket iş akışı, ZIP'i ikinci bir ortamda kurup izole
uygulama ortamında doğrular. Linux masaüstü testleri ekran sunucusu gerektirir.

| Klasör | İçerik |
|---|---|
| `src/game_translator/` | Tarama, çeviri, proje, iş yönetimi, yama, CLI ve masaüstü |
| `tests/` | Sentetik veriyle işlev, güvenlik ve toparlanma testleri |
| `scripts/` | Windows paketleme, kurulum ve paket kabul betikleri |
| `examples/` | MV/MZ için sentetik örnekler |
| `licenses/` | Paketleme için üçüncü taraf lisans bildirimi |
| `.github/` | Test ve paketleme iş akışları |

## Lisans

Proje [MIT lisansı](LICENSE) ile sunulur. Windows paketindeki Python, Tcl ve Tk
lisans bildirimleri `licenses/` içinde dağıtılır. Oyun dosyaları ve API anahtarları
depoya dahil değildir.
