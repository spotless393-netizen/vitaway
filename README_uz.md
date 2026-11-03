# Vitaway natija bot: o'rnatish yo'riqnomasi

Bot nima qiladi:
1. Ota-ona `/start` bosadi, mahsulotni va boshlagan sanasini tanlaydi.
2. 20 kun o'tgach bot animatsiyali so'rovnoma orqali natijani so'raydi va otzivdan foydalanishga rozilik oladi.
3. Xohlovchidan ovozli xabar, video yoki rasm qabul qiladi.
4. O'yin taklif qiladi: **«Ha, sinab ko'raman»** yoki **«Keyingi safar»**. «Keyingi safar» bosilsa, 2 kundan keyin bir marta qayta eslatadi.
5. Xarid qilingan raqamni so'raydi va tasdiqlatadi.
6. «Tayyorlaning!» xabaridan keyin o'yin ochiladi. 5 daraja: 3% → 7% → 11% → 15% → 20%.
7. Chegirma kodi beradi (masalan `VW-15-4832`), u 10 kun amal qiladi.
8. Adminga Excel fayl beradi: har bir mijozning chegirma foizi, xarid raqami, otzivlari.

Papkalar:
- `bot.py`: botning o'zi (faqat Python kerak).
- `webapp/`: o'yin (`game.html`) va so'rovnoma (`natija.html`).
- `assets/`: logotip, bot avatari, qadoq rasmlari va bot animatsiyalari (MP4).
- `tools/make_assets.py`: animatsiyalarni qayta yasash uchun (shart emas).
- `.env.example`: sozlamalar namunasi.

---

## 1-qadam. Bot yaratish (5 daqiqa)

1. Telegramda **@BotFather** ni oching va `/newbot` deb yozing.
2. Botga nom bering (masalan, *Vitaway natija*) va username tanlang (masalan, `vitaway_natija_bot`).
3. BotFather bergan **tokenni** saqlab qo'ying.
4. **@userinfobot** ga yozib, o'zingizning **Telegram ID** raqamingizni bilib oling.

## 2-qadam. Fayllarni GitHub'ga joylash (bepul)

1. **github.com** da ro'yxatdan o'ting.
2. **New repository** ni bosing, nomini `vitaway` qo'ying, **Public** ni tanlang va **Create** ni bosing.
3. **uploading an existing file** havolasini bosing va `vitaway_bot` papkasi ichidagi hamma narsani (`bot.py`, `webapp`, `assets`, `tools` va boshqalarni) sudrab tashlang. Keyin **Commit changes** ni bosing.
4. **Settings → Pages** bo'limiga kiring. **Branch: main**, papka **/ (root)** ni tanlab, **Save** ni bosing.
5. 1–2 daqiqadan keyin quyidagi manzil ochilishi kerak: `https://LOGIN.github.io/vitaway/webapp/game.html`

## 3-qadam. Botni serverda ishga tushirish

Server sifatida oyiga 3–5 dollarlik VPS (Ubuntu 22.04 yoki 24.04) kifoya.

```bash
apt update && apt install -y python3 python3-pip python3-openpyxl git
git clone https://github.com/LOGIN/vitaway.git /opt/vitaway_bot
cd /opt/vitaway_bot
nano .env        # quyidagi qatorlarni yozing, keyin Ctrl+O, Enter, Ctrl+X
python3 bot.py   # "Bot ishga tushdi" chiqishi kerak, keyin Ctrl+C
cp vitaway-bot.service /etc/systemd/system/
systemctl enable --now vitaway-bot
```

`.env` fayli:
```
BOT_TOKEN=7123456789:AAH...xyz
ADMIN_IDS=123456789
BOT_TITLE=Vitaway Kids Club
WEBAPP_URL=https://LOGIN.github.io/vitaway/webapp
```

**Bot rasmi (avatar):** @BotFather → `/setuserpic` → botingizni tanlang → `assets/avatar.png` faylini yuboring.

**Bot nomi:** `BOT_TITLE` da yozilgan nom bot ishga tushganda Telegram'da o'zi o'rnatiladi. Nomni o'zgartirish uchun `.env` dagi `BOT_TITLE` ni o'zgartirib, `systemctl restart vitaway-bot` deb yozing.

**Yangilash:** GitHub'ga yangi faylni yuklagach, serverda quyidagini yozing:
`cd /opt/vitaway_bot && git pull && systemctl restart vitaway-bot`

## 4-qadam. Sinab ko'rish

1. Botga `/start` deb yozing va mahsulot hamda sanani tanlang.
2. `/test` deb yozing. Bot sizga 20-kun so'rovnomasini darhol yuboradi (bu buyruq faqat adminda ishlaydi).
3. So'rovnoma → media → o'yin taklifi → raqam → o'yin: hammasini o'tib ko'ring.
4. Qaytadan sinash uchun avval `/reset`, keyin `/start` deb yozing.

---

## Admin buyruqlari

| Buyruq | Nima qiladi |
|---|---|
| `/admin` | Buyruqlar ro'yxati |
| `/stat` | Statistika: nechta natija, nechta chegirma, foizlar bo'yicha taqsimot |
| `/excel` | Excel fayl: Mijozlar, Natijalar, Media, O'yinlar |
| `/otzivlar` | Oxirgi 10 ta ovozli xabar, video va rasm (`/otzivlar 30`: oxirgi 30 tasi) |
| `/kod VW-15-1234` | Kodni tekshirish va «Ishlatildi» deb belgilash |
| `/mijozlar` | Xaridorlar ro'yxatini yuklash (pastga qarang) |

**Kuratorlar** ham kodni tekshirishi uchun ularning Telegram ID raqamlarini `ADMIN_IDS` ga vergul bilan qo'shing.

**Xaridorlar ro'yxati (ixtiyoriy):** Excel yoki CSV faylni botga yuboring va izohiga `mijozlar` deb yozing. Bot fayldagi barcha telefon raqamlarni oladi. Keyin Excel'dagi «Ro'yxatda bormi» ustunida mijoz yozgan raqam ro'yxatda bor-yo'qligi ko'rinadi.

## Kurator havolasi

Har bir mahsulot uchun alohida havola berish mumkin. Bunda bot mahsulotni so'ramaydi:
- `https://t.me/BOT_USERNAME?start=antihelmo`
- `https://t.me/BOT_USERNAME?start=neuro`
- `https://t.me/BOT_USERNAME?start=immuno`
- `https://t.me/BOT_USERNAME?start=osteo`

## Sozlanadigan narsalar (`bot.py` boshida)

| O'zgaruvchi | Hozir | Ma'nosi |
|---|---|---|
| `RESULT_DAY` | 20 | Natija necha kundan keyin so'raladi |
| `GAME_DAYS` | 5 | O'yin necha kun ochiq turadi |
| `DAILY_ATTEMPTS` | 3 | Kunlik urinishlar soni (ishlatilmagani keyingi kunga o'tadi, eng ko'pi 9 ta) |
| `CODE_DAYS` | 10 | Kod o'yin ochilgan kundan boshlab necha kun amal qiladi |
| `OFFER_REMIND_DAYS` | 2 | «Keyingi safar» dan keyin necha kunda eslatiladi |
| `PCT` | 3/7/11/15/20 | Darajalar bo'yicha chegirma foizlari |

Foizlarni o'zgartirsangiz, `webapp/game.html` dagi `LV` ro'yxatida ham `pct` qiymatlarini o'zgartiring.

## Himoya

- Bitta Telegram akkauntga bitta kod beriladi. Natija yaxshilansa, kod yangilanadi.
- Imkonsiz darajada tez o'tilgan o'yin hisobga olinmaydi va adminga «Shubhali» deb xabar keladi.
- Hech qanday darajani o'ta olmagan, lekin hamma urinishlarini ishlatgan ota-onaga ishtirok uchun 3% beriladi.
- Kod faqat admin «Ishlatildi» deb belgilagunicha amal qiladi.
