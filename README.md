# Invekto PBX Kalite Kontrol Telegram Botu

Invekto PBX API üzerinden çağrı raporu alır, departman bazlı kurallara göre personel ihlallerini kontrol eder ve Telegram grubuna rapor gönderir.

## Railway Environment Variables

| Değişken | Zorunlu | Açıklama |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Evet | Telegram bot token |
| `ADMIN_USER_IDS` | Önerilir | Virgülle ayrılmış admin Telegram kullanıcı ID listesi |
| `ALLOWED_GROUP_NAMES` | Önerilir | Kurulum öncesi izinli grup adları (case-insensitive) |
| `DATABASE_PATH` | Hayır | Varsayılan: `data/bot.sqlite3`. Railway için `/data/bot.sqlite3` |
| `INVEKTO_API_URL` | Hayır | Varsayılan: `https://app.invekto.com/invekto/pbxreport` |
| `TIMEZONE` | Hayır | Varsayılan: `Europe/Istanbul` |
| `REPORT_INTERVAL_MINUTES` | Hayır | Varsayılan: `60` |
| `REQUEST_TIMEOUT_SECONDS` | Hayır | Varsayılan: `60` |
| `SCHEDULER_START_TIME` | Hayır | Varsayılan: `11:30` |
| `SCHEDULER_END_TIME` | Hayır | Varsayılan: `19:00` |
| `PORT` | Hayır | Tanımlanırsa basit HTTP health endpoint açılır |

Departman, `companyCode`, personel ve kurallar Telegram bot komutlarıyla veritabanına kaydedilir.

Railway'de SQLite kullanacaksanız kalıcı volume ekleyin. Kalıcı volume kullanılmazsa departman/kural kayıtları yeniden deploy sonrası kaybolabilir.

## Railway Deploy Notları

1. Railway'de GitHub repo üzerinden yeni servis oluşturun.
2. Servise bir volume ekleyin ve mount path değerini `/data` yapın.
3. `DATABASE_PATH=/data/bot.sqlite3` ayarlayın.
4. Gerekli Environment Variables değerlerini Railway arayüzünden girin.
5. Özel sohbet erişimi için Telegram kullanıcı ID değerlerini `ADMIN_USER_IDS` içine yazın.
6. Botun grup içinde kullanılabilmesi için izinli grup adlarını `ALLOWED_GROUP_NAMES` içine yazın veya departman chat ID kaydı yapın.
7. Invekto tarafında Railway outbound IP adresinin whitelist edilmesi gerekir.
8. Deploy sonrası Telegram'da `/start` ve `/departmanekle` ile kurulum yapılabilir.

## Önemli Invekto Notu

Invekto dokümanına göre API isteğinin başarılı olması için isteği yapan IP adresinin firma için tanımlanmış olması gerekir. Railway servis IP adresi Invekto tarafında whitelist edilmelidir.

## Komutlar

```text
/start, /help
/chat_id
/kimim
/departmanekle
/departman_listele
/departman_sil
/departman_aktif
/departman_pasif
/companycodeayarla
/chatayarla
/kuralayarla
/kurallistele
/personelekle
/personeltopluekle
/personel_listele
/personel_sil
/personel_pasif
/personel_aktif
/izin
/iziniptal
/izinlistele
/haftalikizin
/haftalikizinduzenle
/haftalikiziniptal
/sorumluekle
/sorumlusil
/sorumlulistele
/rapor
/kontrolinvekto
/iptal
```

- Admin komutları yalnızca `ADMIN_USER_IDS` içindeki kullanıcılar tarafından çalıştırılabilir.
- Departman eklerken chat ID verilmezse komutun yazıldığı grup chat ID olarak kaydedilir.
- `/departmanekle`, `/personelekle`, `/companycodeayarla`, `/chatayarla` ve `/kuralayarla` komutları bilgileri adım adım sorar. İşlemi iptal etmek için `/iptal` yazılabilir.
- `/kuralayarla` komutu kuralları adım adım sorar. Bir kural uygulanmayacaksa ilgili adımda `boş` yazılmalıdır.
- `/izin` ve `/iziniptal` aralığında personel kontrol edilmez. Kayıtlı personel adı zorunludur.
- `/haftalikizin` departmanın haftalık izin gününü ekler. Bu günlerde otomatik saatlik rapor ve manuel `/rapor` atlanır.
- `/haftalikizinduzenle` mevcut günleri gösterir, yeni gün ekler veya `tümünü kaldır` ile temizler.
- `/sorumluekle` ile departman sorumluları raporlarda etiketlenir.

## Kural Mantığı

- `reportType=5` görüşme raporu kullanılır.
- `EventType` 1 ve 2 olan, süresi > 0 çağrılar değerlendirilir.
- İlk çağrı mesai başlangıcından sonra ise ihlal sayılır.
- İki çağrı arası bekleme süresi mola aralığı düşüldükten sonra limitten büyükse ihlal sayılır.
- Mola öncesi çağrı bırakma ve mola sonrası çağrı başlangıç kuralları departman bazlı açılıp kapatılabilir.
- Kontrol saati mesai bitişinden sonra ise mesai bitişi ve sonrasında süren/başlayan en az bir çağrı aranır.
- Personel listesi tanımlıysa hiç çağrısı olmayan personel de ihlal olarak yakalanır.
- Invekto 0 kayıt döndürürse kural değerlendirmesi yapılmaz, alarm mesajı gönderilir.
- `boş` yazılan kurallar ilgili departman için uygulanmaz.

## Zamanlanmış Rapor Davranışı

- Scheduler yalnızca yeni ihlal, 0 çağrı alarmı veya API işleme sorunu olduğunda mesaj gönderir.
- Daha önce bildirilen ihlaller tekrar gönderilmez.
- Zamanlanmış rapor hatası oluşursa admin kullanıcılara ayrıca bildirim gider.

## Çalıştırma

```bash
pip install -r requirements.txt
python -m bot.main
```

Testler:

```bash
pip install pytest
python -m pytest tests/ -q
```
