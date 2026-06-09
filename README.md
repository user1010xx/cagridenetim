# Invekto PBX Kalite Kontrol Telegram Botu

Invekto PBX API üzerinden çağrı raporu alır, departman bazlı kurallara göre personel ihlallerini kontrol eder ve Telegram grubuna rapor gönderir.

## Railway Environment Variables

Railway üzerinde global/gizli bilgiler Environment Variables alanından girilmelidir. Bu değerler GitHub reposunda tutulmaz.

Departman, `companyCode`, personel ve kurallar Telegram bot komutlarıyla veritabanına kaydedilir.

Railway'de SQLite kullanacaksanız kalıcı volume ekleyin. Kalıcı volume kullanılmazsa departman/kural kayıtları yeniden deploy sonrası kaybolabilir.

## Railway Deploy Notları

1. Railway'de GitHub repo üzerinden yeni servis oluşturun.
2. Servise bir volume ekleyin ve mount path değerini `/data` yapın.
3. Gerekli Environment Variables değerlerini Railway arayüzünden girin.
4. Özel sohbet erişimi için Telegram kullanıcı ID değerlerini Railway arayüzünden tanımlayın.
5. Botun grup içinde herkes tarafından kullanılabilmesi için izinli grup adlarını Railway arayüzünden tanımlayın.
6. Invekto tarafında Railway outbound IP adresinin whitelist edilmesi gerekir.
7. Deploy sonrası Telegram'da `/start` ve `/departmanekle` ile kurulum yapılabilir.

## Önemli Invekto Notu

Invekto dokümanına göre API isteğinin başarılı olması için isteği yapan IP adresinin firma için tanımlanmış olması gerekir. Railway servis IP adresi Invekto tarafında whitelist edilmelidir.

## Komutlar

```text
/chat_id
/departmanekle
/departman_listele
/kuralayarla
/personelekle
/companycodeayarla
/chatayarla
/izin
/iziniptal
/haftalikizin
/haftalikizinduzenle
/haftalikiziniptal
/sorumluekle
/sorumlusil
/sorumlulistele
/personel_listele Satış
/rapor
/rapor Satış
```

Departman eklerken chat ID verilmezse komutun yazıldığı grup chat ID olarak kaydedilir.

`/departmanekle`, `/personelekle`, `/companycodeayarla`, `/chatayarla` ve `/kuralayarla` komutları bilgileri adım adım sorar. İşlemi iptal etmek için `/iptal` yazılabilir.

`/kuralayarla` komutu kuralları adım adım sorar. Bir kural uygulanmayacaksa ilgili adımda `boş` yazılmalıdır.

`/izin` ve `/iziniptal` aralığında personel kontrol edilmez. `/haftalikizin` ile tanımlı haftalık izin günlerinde personel tüm gün kontrol dışı kalır. `/sorumluekle` ile departman sorumluları raporlarda etiketlenir.

## Kural Mantığı

- `reportType=5` görüşme raporu kullanılır.
- `EventType` 1 ve 2 olan, `CallTimeSecond > 0` çağrılar değerlendirilir.
- İlk çağrı mesai başlangıcından sonra ise ihlal sayılır.
- İki çağrı arası bekleme süresi mola aralığı düşüldükten sonra limitten büyükse ihlal sayılır.
- Mola öncesi çağrı bırakma ve mola sonrası çağrı başlangıç kuralları departman bazlı açılıp kapatılabilir.
- Kontrol saati mesai bitişinden sonra ise mesai bitişi ve sonrasında süren/başlayan en az bir çağrı aranır.
- Personel listesi tanımlıysa hiç çağrısı olmayan personel de ihlal olarak yakalanır.
- `boş` yazılan kurallar ilgili departman için uygulanmaz.

## Çalıştırma

```bash
pip install -r requirements.txt
python -m bot.main
```