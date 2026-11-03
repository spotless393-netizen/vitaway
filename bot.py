# -*- coding: utf-8 -*-
"""
Vitaway natija bot.

20 kunlik natijani so'raydi, otziv va media yig'adi, o'yin orqali
20% gacha chegirma beradi va hammasini adminga Excel qilib beradi.

Faqat Python 3.9+ standart kutubxonasi kerak.
Excel eksport uchun: pip install openpyxl (bo'lmasa CSV beriladi).
"""
import json
import os
import random
import re
import sqlite3
import string
import sys
import time
import traceback
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone

# ------------------------------------------------------------------ sozlamalar
def load_env(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_env(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in re.findall(r"-?\d+", os.environ.get("ADMIN_IDS", ""))}
WEBAPP_URL = os.environ.get("WEBAPP_URL", "").rstrip("/")
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "vitaway.db"))
TZ = timezone(timedelta(hours=int(os.environ.get("TZ_HOURS", "5"))))
BOT_TITLE = os.environ.get("BOT_TITLE", "Vitaway Kids Club")
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

RESULT_DAY = 20          # natija necha kundan keyin so'raladi
GAME_DAYS = 5            # o'yin necha kun ochiq turadi
DAILY_ATTEMPTS = 3       # kunlik urinish
MAX_ATTEMPTS = 9         # yig'ilib boradigan urinishlar chegarasi
CODE_DAYS = 10           # chegirma kodi o'yin ochilganidan necha kun amal qiladi
OFFER_REMIND_DAYS = 2    # "Keyingi safar" dan keyin necha kunda eslatish
REMIND_HOUR = (20, 30)   # kechki eslatma vaqti
SEND_FROM, SEND_TO = 10, 21  # natija so'rovi yuboriladigan soatlar
PCT = {0: 0, 1: 3, 2: 7, 3: 11, 4: 15, 5: 20}
MIN_LEVEL_SEC = 8        # bitta darajani bundan tez o'tish imkonsiz

PRODUCTS = {
    "neuro":     ("🍏", "Neuro Complex",     "nerv tizimi"),
    "immuno":    ("🍌", "Immuno Complex",    "immunitet"),
    "osteo":     ("🍊", "Osteo Complex",     "suyaklar"),
    "antihelmo": ("🍫", "Antihelmo Complex", "gijjaga qarshi"),
    "multi":     ("📦", "Bir nechta mahsulot", ""),
}
AREA_NAMES = {
    "ishtaha": "Ishtaha", "uyqu": "Uyqu", "kayfiyat": "Kayfiyat/g'ayrat", "diqqat": "Diqqat",
    "asab": "Asabiylik", "kasal": "Kasallanish", "harakat": "Faollik", "oyoq": "Oyoq og'rig'i",
    "qorin": "Qorin og'rig'i", "tish": "Tish g'ichirlatish",
}
SCALE_NAMES = {3: "Ancha yaxshilandi", 2: "Biroz yaxshilandi", 1: "O'zgarmadi", 0: "Yomonlashdi"}


def now():
    return datetime.now(TZ)


def today():
    return now().date()


def log(*a):
    print(now().strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


# ------------------------------------------------------------------ Telegram API
API = "https://api.telegram.org/bot{}/{}"


def api(method, **params):
    data = json.dumps({k: v for k, v in params.items() if v is not None}).encode()
    req = urllib.request.Request(API.format(BOT_TOKEN, method), data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            res = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        res = json.loads(e.read().decode() or "{}")
    if not res.get("ok"):
        log("API xato", method, res.get("description"))
    return res.get("result")


def api_file(method, field, filename, content, **params):
    boundary = uuid.uuid4().hex
    body = b""
    for k, v in params.items():
        if v is None:
            continue
        if not isinstance(v, str):
            v = json.dumps(v)
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
             f"Content-Type: application/octet-stream\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(API.format(BOT_TOKEN, method), data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode()).get("result")
    except Exception as e:
        log("Fayl yuborishda xato", e)


def send(chat_id, text, kb=None, **kw):
    return api("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
               reply_markup=kb, disable_web_page_preview=True, **kw)


def typing(chat_id):
    api("sendChatAction", chat_id=chat_id, action="typing")


def send_anim(chat_id, key, caption, kb=None):
    """assets/<key>.mp4 animatsiyasini matn bilan yuboradi. Birinchi marta yuklaydi, keyin file_id dan foydalanadi."""
    fid = kv_get("anim:" + key)
    if fid:
        r = api("sendAnimation", chat_id=chat_id, animation=fid, caption=caption, parse_mode="HTML", reply_markup=kb)
        if r:
            return r
    path = os.path.join(ASSETS, key + ".mp4")
    if os.path.exists(path):
        with open(path, "rb") as f:
            r = api_file("sendAnimation", "animation", key + ".mp4", f.read(), chat_id=str(chat_id),
                         caption=caption, parse_mode="HTML", reply_markup=kb, width="512", height="512")
        if r and r.get("animation"):
            kv_set("anim:" + key, r["animation"]["file_id"])
            return r
    return send(chat_id, caption, kb)


def ikb(*rows):
    """Inline tugmalar: ikb([("Matn", "data"), ...], ...)"""
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}


def webapp_kb(text, url):
    return {"keyboard": [[{"text": text, "web_app": {"url": url}}]], "resize_keyboard": True, "is_persistent": True}


REMOVE_KB = {"remove_keyboard": True}

# ------------------------------------------------------------------ ma'lumotlar bazasi
db = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, first_name TEXT, username TEXT, tg_phone TEXT,
  product TEXT, start_date TEXT, state TEXT, created_at TEXT,
  result_asked_at TEXT, result_reminded INTEGER DEFAULT 0, result_done_at TEXT,
  offer_status TEXT DEFAULT '', offer_at TEXT, offer_reminded INTEGER DEFAULT 0,
  buy_phone TEXT, phone_ok INTEGER DEFAULT 0, in_list INTEGER,
  game_open_at TEXT, attempts_left INTEGER DEFAULT 0, attempts_day TEXT,
  best_level INTEGER DEFAULT 0, best_pct INTEGER DEFAULT 0,
  code TEXT, code_exp TEXT, code_used INTEGER DEFAULT 0, code_used_by INTEGER, code_used_at TEXT,
  last_remind TEXT, blocked INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS results(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, created_at TEXT, product TEXT,
  who TEXT, child TEXT, age TEXT, scores TEXT, text TEXT, stars INTEGER, rec TEXT, consent TEXT, raw TEXT
);
CREATE TABLE IF NOT EXISTS media(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, created_at TEXT, kind TEXT, file_id TEXT, text TEXT
);
CREATE TABLE IF NOT EXISTS plays(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, created_at TEXT, start INTEGER, reached INTEGER,
  pct INTEGER, dur INTEGER, how TEXT, suspicious INTEGER DEFAULT 0, raw TEXT
);
CREATE TABLE IF NOT EXISTS buyers(phone TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
"""


def db_init(path=None):
    global db
    db = sqlite3.connect(path or DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    db.commit()


def get_user(uid):
    return db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def upd(uid, **f):
    if not f:
        return
    cols = ", ".join(f"{k}=?" for k in f)
    db.execute(f"UPDATE users SET {cols} WHERE id=?", (*f.values(), uid))
    db.commit()


def kv_get(k, default=None):
    r = db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return r["v"] if r else default


def kv_set(k, v):
    db.execute("INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)", (k, str(v)))
    db.commit()


# ------------------------------------------------------------------ yordamchilar
def d2s(d):
    return d.strftime("%d.%m.%Y")


def parse_date(s):
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def iso(dt):
    return dt.isoformat(timespec="seconds")


def from_iso(s):
    return datetime.fromisoformat(s) if s else None


def norm_phone(s):
    d = re.sub(r"\D", "", s or "")
    if len(d) == 9:
        d = "998" + d
    if len(d) == 12 and d.startswith("998"):
        return "+" + d
    return None


def pretty_phone(p):
    d = re.sub(r"\D", "", p)
    return f"+{d[:3]} {d[3:5]} {d[5:8]} {d[8:10]} {d[10:12]}" if len(d) == 12 else p


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def prod_name(key):
    e, n, _ = PRODUCTS.get(key or "multi", PRODUCTS["multi"])
    return f"{e} {n}"


def new_code(pct):
    while True:
        c = f"VW-{pct}-{random.randint(1000, 9999)}"
        if not db.execute("SELECT 1 FROM users WHERE code=?", (c,)).fetchone():
            return c


def game_url(u):
    return f"{WEBAPP_URL}/game.html?start={min(5, (u['best_level'] or 0) + 1)}&best={u['best_pct'] or 0}&att={u['attempts_left'] or 0}"


def natija_url(u):
    return f"{WEBAPP_URL}/natija.html?p={u['product'] or 'multi'}"


def game_open(u):
    """O'yin hali ochiqmi (5 kunlik oyna)."""
    if not u["game_open_at"]:
        return False
    return today() <= from_iso(u["game_open_at"]).date() + timedelta(days=GAME_DAYS - 1)


def refresh_attempts(u):
    """Yangi kun boshlansa, urinishlar qo'shiladi (yig'ilib boradi)."""
    if not u["game_open_at"] or not game_open(u):
        return u
    last = parse_date(u["attempts_day"]) or today()
    days = (today() - last).days
    if days > 0:
        left = min(MAX_ATTEMPTS, (u["attempts_left"] or 0) + DAILY_ATTEMPTS * days)
        upd(u["id"], attempts_left=left, attempts_day=today().isoformat())
        u = get_user(u["id"])
    return u


def is_admin(uid):
    return uid in ADMIN_IDS


# ------------------------------------------------------------------ foydalanuvchi oqimi
def start_cmd(msg, payload):
    uid = msg["from"]["id"]
    fr = msg["from"]
    u = get_user(uid)
    if not u:
        db.execute("INSERT INTO users(id, first_name, username, state, created_at) VALUES(?,?,?,?,?)",
                   (uid, fr.get("first_name", ""), fr.get("username", ""), "reg_product", iso(now())))
        db.commit()
        u = get_user(uid)
    else:
        upd(uid, first_name=fr.get("first_name", ""), username=fr.get("username", ""))

    if u["start_date"] and u["state"] not in ("reg_product", "reg_date"):
        return status_msg(u)

    send_anim(uid, "welcome", f"Assalomu alaykum, <b>{esc(fr.get('first_name', ''))}</b>! 👋\n\n"
              f"<b>{esc(BOT_TITLE)}</b> ga xush kelibsiz 💚\n"
              "Bu bot farzandingizning 20 kunlik natijasini kuzatib boradi va "
              "sizni yoqimli sovg'alar kutmoqda 🎁", REMOVE_KB)
    if payload in PRODUCTS:
        upd(uid, product=payload)
        return ask_date(uid)
    upd(uid, state="reg_product")
    send(uid, "Farzandingiz qaysi mahsulotni ichyapti?", ikb(
        [("🍏 Neuro (nerv tizimi)", "p:neuro")],
        [("🍌 Immuno (immunitet)", "p:immuno")],
        [("🍊 Osteo (suyaklar)", "p:osteo")],
        [("🍫 Antihelmo (gijjaga qarshi)", "p:antihelmo")],
        [("📦 Bir nechtasini", "p:multi")]))


def ask_date(uid):
    upd(uid, state="reg_date")
    send(uid, "📅 Farzandingiz mahsulotni qachondan ichishni boshladi?", ikb(
        [("Bugun", "d:0"), ("Kecha", "d:1")],
        [("✍️ Sanani yozaman", "d:manual")]))


def set_start(uid, d):
    upd(uid, start_date=d.isoformat(), state="active")
    day20 = d + timedelta(days=RESULT_DAY)
    left = (day20 - today()).days
    txt = (f"Ajoyib! ✅ Boshlangan sana: <b>{d2s(d)}</b>\n\n"
           f"<b>{d2s(day20)}</b> kuni farzandingizdagi o'zgarishlarni so'raymiz.\n"
           "Mahsulotni har kuni berishni unutmang 💚")
    if left <= 0:
        txt = f"Boshlangan sana: <b>{d2s(d)}</b> ✅\n\n20 kun allaqachon o'tibdi, hoziroq natijani so'raymiz!"
    send(uid, txt)
    if left <= 0:
        ask_result(get_user(uid))


def status_msg(u):
    uid = u["id"]
    st = u["state"]
    if st == "active":
        day20 = parse_date(u["start_date"]) + timedelta(days=RESULT_DAY)
        left = (day20 - today()).days
        return send(uid, f"⏳ Natijani so'rashimizga <b>{max(left, 0)}</b> kun qoldi ({d2s(day20)}).\n"
                         f"Mahsulot: {prod_name(u['product'])}")
    if st == "natija":
        return ask_result(u, again=True)
    if st == "media":
        return ask_media(uid)
    if st in ("offer",):
        return send_offer(uid)
    if st in ("phone", "phone_confirm"):
        return ask_phone(uid)
    if st in ("ready", "done"):
        return game_cmd(u)
    send(uid, "Salom! 👋")


def ask_result(u, again=False):
    uid = u["id"]
    if not WEBAPP_URL:
        log("WEBAPP_URL sozlanmagan")
    if not again:
        upd(uid, state="natija", result_asked_at=iso(now()))
    txt = ("🎉 <b>Tabriklaymiz, 20 kun to'ldi!</b>\n\n"
           "Farzandingizda qanday o'zgarishlarni sezdingiz? Pastdagi "
           "<b>«📝 Natijani ulashish»</b> tugmasini bosing. Bor-yo'g'i 1 daqiqa vaqt oladi 💚")
    kb = webapp_kb("📝 Natijani ulashish", natija_url(get_user(uid)))
    if again:
        return send(uid, txt, kb)
    send_anim(uid, "day20", txt, kb)


def on_natija(u, data):
    uid = u["id"]
    sc = data.get("sc") or {}
    db.execute("INSERT INTO results(user_id, created_at, product, who, child, age, scores, text, stars, rec, consent, raw)"
               " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
               (uid, iso(now()), data.get("p") or u["product"], str(data.get("who", ""))[:40],
                str(data.get("child", ""))[:60], str(data.get("age", ""))[:10], json.dumps(sc, ensure_ascii=False),
                str(data.get("text", ""))[:2000], int(data.get("stars") or 0), str(data.get("rec", ""))[:40],
                str(data.get("ok", ""))[:40], json.dumps(data, ensure_ascii=False)[:4000]))
    db.commit()
    upd(uid, result_done_at=iso(now()))
    better = sum(1 for v in sc.values() if isinstance(v, int) and v >= 2)
    txt = "💚 <b>Rahmat! Natijangiz saqlandi.</b>"
    if better:
        txt += f"\n\nSiz <b>{better} ta</b> yo'nalishda yaxshilanish sezdingiz. Bu juda zo'r natija! 👏"
    send(uid, txt, REMOVE_KB)
    for aid in ADMIN_IDS:
        send(aid, f"📝 Yangi natija: <b>{esc(u['first_name'])}</b> · {prod_name(data.get('p') or u['product'])}\n"
                  f"⭐ {data.get('stars') or '-'} · {esc(str(data.get('ok', '')))}\n"
                  f"{esc(str(data.get('text', ''))[:300])}")
    ask_media(uid, voice_first=bool(data.get("voiceLater")))


def ask_media(uid, voice_first=False):
    upd(uid, state="media")
    t = ("🎙 Xohlasangiz, farzandingiz haqida qisqa <b>ovozli xabar</b>, <b>video</b> yoki <b>rasm</b> yuboring.\n\n"
         "Sizning tajribangiz boshqa ota-onalarga katta yordam beradi 🙏")
    if voice_first:
        t = "🎙 Ovozli xabar yuborishni aytgan edingiz. Hoziroq yozib yuborishingiz mumkin!\n\n" + t
    send(uid, t, ikb([("O'tkazib yuborish ➡️", "media:skip")]))


def on_media(u, msg):
    uid = u["id"]
    kind, fid, text = None, None, msg.get("caption") or ""
    if "voice" in msg:
        kind, fid = "voice", msg["voice"]["file_id"]
    elif "video_note" in msg:
        kind, fid = "video_note", msg["video_note"]["file_id"]
    elif "video" in msg:
        kind, fid = "video", msg["video"]["file_id"]
    elif "photo" in msg:
        kind, fid = "photo", msg["photo"][-1]["file_id"]
    elif "audio" in msg:
        kind, fid = "audio", msg["audio"]["file_id"]
    elif "document" in msg:
        kind, fid = "document", msg["document"]["file_id"]
    elif "text" in msg:
        kind, text = "text", msg["text"]
    if not kind:
        return False
    db.execute("INSERT INTO media(user_id, created_at, kind, file_id, text) VALUES(?,?,?,?,?)",
               (uid, iso(now()), kind, fid, text[:2000]))
    db.commit()
    send(uid, "✅ Qabul qilindi, rahmat! Yana yuborishingiz yoki davom etishingiz mumkin.",
         ikb([("Davom etish ➡️", "media:skip")]))
    for aid in ADMIN_IDS:
        send(aid, f"🎙 Yangi media ({kind}): <b>{esc(u['first_name'])}</b>. Ko'rish: /otzivlar")
    return True


def send_offer(uid):
    upd(uid, state="offer", offer_at=iso(now()))
    send_anim(uid, "offer", "🎁 <b>Sizga sovg'amiz bor!</b>\n\n"
              "Agar xohlasangiz, qiziqarli o'yinimizni o'ynab, yangi mahsulot uchun "
              "<b>20% gacha chegirma</b>ga ega bo'lishingiz mumkin 🧺",
         ikb([("🎮 Ha, sinab ko'raman", "offer:yes")], [("⏰ Keyingi safar", "offer:later")]))


def ask_phone(uid):
    upd(uid, state="phone")
    send(uid, "📱 Mahsulotni qaysi telefon raqamidan xarid qilgansiz?\n\n"
              "Raqamni yozing, masalan: <b>+998 90 123 45 67</b>\n"
              "yoki pastdagi tugma orqali Telegram raqamingizni yuboring.",
         {"keyboard": [[{"text": "📲 Telegram raqamimni yuborish", "request_contact": True}]],
          "resize_keyboard": True, "one_time_keyboard": True})


def on_phone(u, text=None, contact=None):
    uid = u["id"]
    p = norm_phone(contact.get("phone_number") if contact else text)
    if contact:
        upd(uid, tg_phone=p or contact.get("phone_number"))
    if not p:
        return send(uid, "❗️ Raqam noto'g'ri ko'rinadi. Iltimos, quyidagicha yozing:\n<b>+998 90 123 45 67</b>")
    upd(uid, buy_phone=p, state="phone_confirm")
    send(uid, f"📞 <b>{pretty_phone(p)}</b>\n\nMahsulotni aynan shu raqamdan xarid qilganmisiz?", REMOVE_KB)
    send(uid, "Tasdiqlang 👇", ikb([("✅ Ha, to'g'ri", "ph:yes")], [("✏️ Yo'q, o'zgartiraman", "ph:no")]))


def phone_confirmed(uid):
    u = get_user(uid)
    in_list = None
    if db.execute("SELECT 1 FROM buyers LIMIT 1").fetchone():
        in_list = 1 if db.execute("SELECT 1 FROM buyers WHERE phone=?", (u["buy_phone"],)).fetchone() else 0
    f = dict(phone_ok=1, in_list=in_list, state="ready")
    if not u["game_open_at"]:
        f.update(game_open_at=iso(now()), attempts_left=DAILY_ATTEMPTS, attempts_day=today().isoformat())
    upd(uid, **f)
    get_ready(get_user(uid))


def get_ready(u):
    uid = u["id"]
    typing(uid)
    send(uid, "🧺 <b>Tayyorlaning!</b>\n\n"
              "Tepadan Vitaway mahsulotlari tushadi, siz ularni savatchaga yig'asiz. "
              "Har bir daraja chegirmani oshiradi: <b>3% → 7% → 11% → 15% → 20%</b>\n\n"
              f"🎮 Urinishlar: <b>{u['attempts_left']}</b>\n"
              "Qoidalar o'yin ichida tushuntiriladi.\n\n"
              "O'yinni boshlashga tayyormisiz? 👇",
         webapp_kb("🎮 O'yinni boshlash", game_url(u)))


def game_cmd(u):
    uid = u["id"]
    u = refresh_attempts(u)
    if not u["phone_ok"]:
        if u["result_done_at"]:
            return send_offer(uid)
        return send(uid, "O'yin 20 kunlik natijadan keyin ochiladi 😊")
    if (u["best_level"] or 0) >= 5:
        return send(uid, f"🏆 Siz eng yuqori natijaga erishgansiz!\n🎟 Kodingiz: <code>{u['code']}</code>", REMOVE_KB)
    if not game_open(u):
        t = "⌛️ O'yin muddati tugagan."
        if u["code"]:
            t += f"\n🎟 Chegirma kodingiz: <code>{u['code']}</code> ({u['best_pct']}%)"
        return send(uid, t, REMOVE_KB)
    if (u["attempts_left"] or 0) <= 0:
        return send(uid, "Bugungi urinishlar tugadi. Ertaga yana 3 ta urinish beriladi 😊")
    get_ready(u)


def on_game(u, data):
    uid = u["id"]
    u = refresh_attempts(u)
    if not u["phone_ok"] or not game_open(u) or (u["attempts_left"] or 0) <= 0:
        return game_cmd(u)
    start = int(data.get("start") or 1)
    reached = int(data.get("reached") or 0)
    lv = data.get("lv") or []
    best = u["best_level"] or 0
    # tekshiruv
    suspicious = 0
    ok_levels = [x for x in lv if isinstance(x, dict) and x.get("ok")]
    if reached and (reached < start or reached > 5 or start > best + 1):
        suspicious = 1
    if reached and len(ok_levels) != reached - start + 1:
        suspicious = 1
    if any(int(x.get("s") or 0) < MIN_LEVEL_SEC for x in ok_levels):
        suspicious = 1
    db.execute("INSERT INTO plays(user_id, created_at, start, reached, pct, dur, how, suspicious, raw) VALUES(?,?,?,?,?,?,?,?,?)",
               (uid, iso(now()), start, reached, PCT.get(reached, 0), int(data.get("dur") or 0),
                str(data.get("how", ""))[:10], suspicious, json.dumps(data)[:3000]))
    db.commit()
    left = (u["attempts_left"] or 0) - 1
    upd(uid, attempts_left=left)
    if suspicious:
        for aid in ADMIN_IDS:
            send(aid, f"⚠️ Shubhali o'yin natijasi: <b>{esc(u['first_name'])}</b> (id {uid}), {reached}-daraja. /excel → O'yinlar")
        return send(uid, "🔎 Natijangiz tekshiruvga yuborildi. Iltimos, yana bir bor o'ynab ko'ring.",
                    webapp_kb("🎮 O'yinni boshlash", game_url(get_user(uid))) if left > 0 else REMOVE_KB)

    improved = reached > best
    consolation = False
    if improved:
        best = reached
    elif best == 0 and left <= 0:
        best, consolation = 1, True  # ishtirok uchun 3%
    if improved or consolation:
        pct = PCT[best]
        code = new_code(pct)
        exp = from_iso(u["game_open_at"]).date() + timedelta(days=CODE_DAYS)
        upd(uid, best_level=best, best_pct=pct, code=code, code_exp=exp.isoformat())
    u = get_user(uid)

    if improved or consolation:
        head = ("🎉 <b>Tabriklaymiz!</b>" if improved else "💚 Ishtirokingiz uchun rahmat!")
        win_txt = (f"{head}\n\nSiz <b>{u['best_pct']}% chegirma</b> qo'lga kiritdingiz!\n\n"
                   f"🎟 Chegirma kodingiz: <code>{u['code']}</code>\n"
                   f"📅 Amal qiladi: <b>{d2s(parse_date(u['code_exp']))}</b> gacha\n\n"
                   "Yangi mahsulot buyurtma qilayotganda shu kodni kuratoringizga yuboring.")
        if improved:
            send_anim(uid, "win", win_txt)
        else:
            send(uid, win_txt)
    else:
        send(uid, f"Bu safar natija o'zgarmadi. Joriy chegirmangiz: <b>{u['best_pct'] or 0}%</b>")

    if best >= 5:
        upd(uid, state="done")
        return send(uid, "🏆 Siz eng yuqori natijaga erishdingiz! Barakalla!", REMOVE_KB)
    if left > 0:
        return send(uid, f"🎮 Yana <b>{left}</b> ta urinishingiz bor. Keyingi darajada "
                         f"<b>{PCT[best + 1]}%</b> gacha oshirishingiz mumkin! 💪",
                    webapp_kb("🎮 O'yinni boshlash", game_url(u)))
    last_day = from_iso(u["game_open_at"]).date() + timedelta(days=GAME_DAYS - 1)
    if today() < last_day:
        return send(uid, "Bugungi urinishlar tugadi. Ertaga yana 3 ta urinish beriladi 😊", REMOVE_KB)
    upd(uid, state="done")
    send(uid, "O'yin yakunlandi. Ishtirokingiz uchun rahmat! 💚", REMOVE_KB)


# ------------------------------------------------------------------ admin
def admin_help(uid):
    send(uid, "<b>Admin buyruqlari</b>\n\n"
              "/stat — umumiy statistika\n"
              "/excel — hamma ma'lumotlar Excel faylda\n"
              "/otzivlar — oxirgi ovozli xabar, video va rasmlar\n"
              "/kod VW-15-1234 — kodni tekshirish va «ishlatildi» deb belgilash\n"
              "/mijozlar — xaridorlar ro'yxatini yuklash (raqamlarni tekshirish uchun)\n"
              "/test — o'zingizda 20-kun oqimini sinash\n"
              "/reset — o'z ma'lumotingizni o'chirish (sinov uchun)")


def admin_stat(uid):
    q = lambda s: db.execute(s).fetchone()[0]
    total = q("SELECT COUNT(*) FROM users")
    waiting = q("SELECT COUNT(*) FROM users WHERE state='active'")
    results = q("SELECT COUNT(DISTINCT user_id) FROM results")
    media = q("SELECT COUNT(*) FROM media WHERE kind!='text'")
    agreed = q("SELECT COUNT(*) FROM users WHERE phone_ok=1")
    later = q("SELECT COUNT(*) FROM users WHERE offer_status='later'")
    won = q("SELECT COUNT(*) FROM users WHERE best_pct>0")
    used = q("SELECT COUNT(*) FROM users WHERE code_used=1")
    dist = db.execute("SELECT best_pct, COUNT(*) c FROM users WHERE best_pct>0 GROUP BY best_pct ORDER BY best_pct").fetchall()
    send(uid, "📊 <b>Statistika</b>\n\n"
              f"👥 Ro'yxatdan o'tgan: <b>{total}</b>\n"
              f"⏳ 20 kunni kutayotgan: <b>{waiting}</b>\n"
              f"📝 Natija yuborgan: <b>{results}</b>\n"
              f"🎙 Media otzivlar: <b>{media}</b>\n"
              f"🎮 O'yinga rozi bo'lgan: <b>{agreed}</b>\n"
              f"⏰ «Keyingi safar»: <b>{later}</b>\n"
              f"🎟 Chegirma olgan: <b>{won}</b>\n"
              + "".join(f"   • {r['best_pct']}% — {r['c']} ta\n" for r in dist) +
              f"✅ Kodni ishlatgan: <b>{used}</b>")


def build_excel():
    users = db.execute("SELECT * FROM users ORDER BY created_at").fetchall()
    res = db.execute("SELECT r.*, u.first_name, u.username, u.buy_phone FROM results r LEFT JOIN users u ON u.id=r.user_id ORDER BY r.id").fetchall()
    med = db.execute("SELECT m.*, u.first_name, u.username FROM media m LEFT JOIN users u ON u.id=m.user_id ORDER BY m.id").fetchall()
    plays = db.execute("SELECT p.*, u.first_name FROM plays p LEFT JOIN users u ON u.id=p.user_id ORDER BY p.id").fetchall()
    consent = {r["user_id"]: r["consent"] for r in res}

    sheets = []
    sheets.append(("Mijozlar", ["Telegram ID", "Ism", "Username", "Mahsulot", "Boshlagan sana", "Xarid raqami",
                                "Ro'yxatda bormi", "Natija yubordimi", "O'yin taklifi", "Daraja", "Chegirma %", "Kod",
                                "Kod muddati", "Kod ishlatildi", "Holat"],
                   [[u["id"], u["first_name"], ("@" + u["username"]) if u["username"] else "", prod_name(u["product"])[2:],
                     d2s(parse_date(u["start_date"])) if u["start_date"] else "", pretty_phone(u["buy_phone"] or ""),
                     {1: "Ha", 0: "Yo'q"}.get(u["in_list"], ""), "Ha" if u["result_done_at"] else "Yo'q",
                     {"yes": "Rozi", "later": "Keyingi safar"}.get(u["offer_status"], ""), u["best_level"] or 0,
                     u["best_pct"] or 0, u["code"] or "", d2s(parse_date(u["code_exp"])) if u["code_exp"] else "",
                     "Ha" if u["code_used"] else "", u["state"]] for u in users]))
    area_keys = list(AREA_NAMES)
    rrows = []
    for r in res:
        sc = json.loads(r["scores"] or "{}")
        rrows.append([r["created_at"][:16].replace("T", " "), r["first_name"], ("@" + r["username"]) if r["username"] else "",
                      pretty_phone(r["buy_phone"] or ""), prod_name(r["product"])[2:], r["who"], r["child"], r["age"]]
                     + [SCALE_NAMES.get(sc.get(k), "") for k in area_keys]
                     + [r["text"], r["stars"], r["rec"], r["consent"]])
    sheets.append(("Natijalar", ["Sana", "Ism", "Username", "Xarid raqami", "Mahsulot", "Kim to'ldirdi", "Bola ismi", "Yoshi"]
                   + [AREA_NAMES[k] for k in area_keys] + ["Otziv matni", "Yulduz", "Tavsiya", "Foydalanishga rozilik"], rrows))
    sheets.append(("Media", ["Sana", "Ism", "Username", "Turi", "Matn/izoh", "Rozilik", "file_id"],
                   [[m["created_at"][:16].replace("T", " "), m["first_name"], ("@" + m["username"]) if m["username"] else "",
                     m["kind"], m["text"], consent.get(m["user_id"], ""), m["file_id"]] for m in med]))
    sheets.append(("O'yinlar", ["Sana", "Ism", "Boshlagan daraja", "Yetgan daraja", "Foiz", "Davomiyligi (s)", "Yakun", "Shubhali"],
                   [[p["created_at"][:16].replace("T", " "), p["first_name"], p["start"], p["reached"], p["pct"], p["dur"],
                     p["how"], "Ha" if p["suspicious"] else ""] for p in plays]))
    try:
        from io import BytesIO
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        wb = Workbook()
        wb.remove(wb.active)
        for name, head, rows in sheets:
            ws = wb.create_sheet(name)
            ws.append(head)
            for r in rows:
                ws.append(r)
            for c in ws[1]:
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = PatternFill("solid", fgColor="1E9BEF")
                c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            for i, h in enumerate(head, 1):
                width = max([len(str(h))] + [len(str(r[i - 1] or "")) for r in rows[:200]]) + 2
                ws.column_dimensions[ws.cell(1, i).column_letter].width = min(max(width, 10), 60)
            ws.freeze_panes = "A2"
        bio = BytesIO()
        wb.save(bio)
        return f"vitaway_{today().isoformat()}.xlsx", bio.getvalue()
    except ImportError:
        import csv
        from io import StringIO
        out = StringIO()
        w = csv.writer(out)
        for name, head, rows in sheets:
            w.writerow([f"== {name} =="])
            w.writerow(head)
            w.writerows(rows)
            w.writerow([])
        return f"vitaway_{today().isoformat()}.csv", out.getvalue().encode("utf-8-sig")


def admin_excel(uid):
    send(uid, "⏳ Fayl tayyorlanmoqda...")
    name, content = build_excel()
    api_file("sendDocument", "document", name, content, chat_id=str(uid), caption="📥 Vitaway: mijozlar, natijalar, media va o'yinlar")


def admin_otzivlar(uid, arg):
    n = int(arg) if arg and arg.isdigit() else 10
    rows = db.execute("SELECT m.*, u.first_name, u.product FROM media m LEFT JOIN users u ON u.id=m.user_id "
                      "ORDER BY m.id DESC LIMIT ?", (n,)).fetchall()
    if not rows:
        return send(uid, "Hozircha media otzivlar yo'q.")
    method = {"voice": ("sendVoice", "voice"), "video": ("sendVideo", "video"), "photo": ("sendPhoto", "photo"),
              "video_note": ("sendVideoNote", "video_note"), "audio": ("sendAudio", "audio"),
              "document": ("sendDocument", "document")}
    for m in reversed(rows):
        c = db.execute("SELECT consent FROM results WHERE user_id=? ORDER BY id DESC LIMIT 1", (m["user_id"],)).fetchone()
        cap = f"👤 {esc(m['first_name'])} · {prod_name(m['product'])}\n📣 Rozilik: {c['consent'] if c else '-'}\n{esc(m['text'] or '')}"
        if m["kind"] == "text":
            send(uid, "💬 " + cap)
        elif m["kind"] == "video_note":
            api("sendVideoNote", chat_id=uid, video_note=m["file_id"])
            send(uid, cap)
        else:
            meth, field = method[m["kind"]]
            api(meth, chat_id=uid, caption=cap[:1000], parse_mode="HTML", **{field: m["file_id"]})


def admin_kod(uid, arg):
    code = (arg or "").strip().upper()
    if not code:
        return send(uid, "Kodni yozing: /kod VW-15-1234")
    u = db.execute("SELECT * FROM users WHERE code=?", (code,)).fetchone()
    if not u:
        return send(uid, "❌ Bunday kod topilmadi.")
    exp = parse_date(u["code_exp"])
    st = "✅ Ishlatilgan" if u["code_used"] else ("⌛️ Muddati o'tgan" if exp and exp < today() else "🟢 Amalda")
    txt = (f"🎟 <b>{code}</b> — {u['best_pct']}%\n{st}\n\n👤 {esc(u['first_name'])} "
           f"{('@' + u['username']) if u['username'] else ''}\n📞 {pretty_phone(u['buy_phone'] or '')}\n"
           f"📅 Muddati: {d2s(exp) if exp else '-'}")
    kb = None if u["code_used"] else ikb([("✅ Ishlatildi deb belgilash", f"use:{code}")])
    send(uid, txt, kb)


def admin_buyers_doc(uid, msg):
    doc = msg["document"]
    f = api("getFile", file_id=doc["file_id"])
    if not f:
        return send(uid, "Faylni yuklab bo'lmadi.")
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{f['file_path']}", timeout=60) as r:
        content = r.read()
    text = ""
    if doc.get("file_name", "").lower().endswith((".xlsx", ".xlsm")):
        try:
            from io import BytesIO
            from openpyxl import load_workbook
            wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
            text = " ".join(str(c) for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for c in row if c is not None)
        except ImportError:
            return send(uid, "Excel o'qish uchun serverda openpyxl kerak. CSV yoki TXT yuboring.")
    else:
        text = content.decode("utf-8", "ignore")
    phones = {norm_phone(m) for m in re.findall(r"\+?\d[\d\s\-()]{7,16}\d", text)}
    phones.discard(None)
    db.executemany("INSERT OR IGNORE INTO buyers(phone) VALUES(?)", [(p,) for p in phones])
    db.commit()
    total = db.execute("SELECT COUNT(*) FROM buyers").fetchone()[0]
    send(uid, f"✅ {len(phones)} ta raqam qo'shildi. Ro'yxatda jami: {total} ta.")


# ------------------------------------------------------------------ yangilanishlarni qayta ishlash
def handle_message(msg):
    uid = msg["from"]["id"]
    text = msg.get("text") or ""
    if msg.get("chat", {}).get("type") != "private":
        return

    if text.startswith("/"):
        cmd, _, arg = text.partition(" ")
        cmd = cmd.split("@")[0].lower()
        if cmd == "/start":
            return start_cmd(msg, arg.strip().lower())
        u = get_user(uid)
        if is_admin(uid):
            if cmd == "/admin":
                return admin_help(uid)
            if cmd == "/stat":
                return admin_stat(uid)
            if cmd == "/excel":
                return admin_excel(uid)
            if cmd == "/otzivlar":
                return admin_otzivlar(uid, arg.strip())
            if cmd == "/kod":
                return admin_kod(uid, arg)
            if cmd == "/mijozlar":
                return send(uid, "Xaridorlar raqamlari bor Excel, CSV yoki TXT faylni yuboring va izohiga <b>mijozlar</b> deb yozing.")
            if cmd == "/test":
                if not u:
                    start_cmd(msg, "")
                upd(uid, start_date=(today() - timedelta(days=RESULT_DAY)).isoformat(), state="active",
                    product=(get_user(uid)["product"] or "antihelmo"))
                return ask_result(get_user(uid))
            if cmd == "/reset":
                for t in ("results", "media", "plays"):
                    db.execute(f"DELETE FROM {t} WHERE user_id=?", (uid,))
                db.execute("DELETE FROM users WHERE id=?", (uid,))
                db.commit()
                return send(uid, "🗑 Ma'lumotlaringiz o'chirildi. /start", REMOVE_KB)
        if not u:
            return start_cmd(msg, "")
        if cmd in ("/oyin", "/game"):
            return game_cmd(u)
        if cmd in ("/kodim", "/code"):
            return send(uid, f"🎟 Kodingiz: <code>{u['code']}</code> ({u['best_pct']}%)" if u["code"] else "Hozircha chegirma kodingiz yo'q.")
        return status_msg(u)

    if is_admin(uid) and "document" in msg and "mijoz" in (msg.get("caption") or "").lower():
        return admin_buyers_doc(uid, msg)

    u = get_user(uid)
    if not u:
        return start_cmd(msg, "")

    if "web_app_data" in msg:
        try:
            data = json.loads(msg["web_app_data"]["data"])
        except Exception:
            return send(uid, "Ma'lumotni o'qib bo'lmadi, qaytadan urinib ko'ring.")
        if data.get("t") == "natija" and u["state"] in ("natija", "media", "offer") and not u["result_done_at"]:
            return on_natija(u, data)
        if data.get("t") == "game":
            return on_game(u, data)
        return

    st = u["state"]
    if st == "reg_date" and text:
        m = re.match(r"^\s*(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\s*$", text)
        if m:
            d, mo, y = int(m[1]), int(m[2]), int(m[3])
            y = y + 2000 if y < 100 else y
            try:
                dt = date(y, mo, d)
                if dt > today() or dt < today() - timedelta(days=120):
                    raise ValueError
                return set_start(uid, dt)
            except ValueError:
                pass
        return send(uid, "Sanani <b>kk.oo.yyyy</b> shaklida yozing, masalan: <b>" + d2s(today() - timedelta(days=3)) + "</b>")
    if st == "media":
        if on_media(u, msg):
            return
    if st == "phone":
        if "contact" in msg:
            if msg["contact"].get("user_id") not in (None, uid):
                return send(uid, "Iltimos, o'z raqamingizni yuboring yoki yozing.")
            return on_phone(u, contact=msg["contact"])
        if text:
            return on_phone(u, text=text)
    if st == "natija":
        return ask_result(u, again=True)
    if st in ("ready",) and text:
        return game_cmd(u)
    status_msg(u)


def handle_callback(cq):
    uid = cq["from"]["id"]
    data = cq.get("data") or ""
    mid = cq["message"]["message_id"] if cq.get("message") else None
    api("answerCallbackQuery", callback_query_id=cq["id"])
    u = get_user(uid)
    if data.startswith("use:") and is_admin(uid):
        code = data[4:]
        db.execute("UPDATE users SET code_used=1, code_used_by=?, code_used_at=? WHERE code=?", (uid, iso(now()), code))
        db.commit()
        api("editMessageReplyMarkup", chat_id=uid, message_id=mid, reply_markup={"inline_keyboard": []})
        return send(uid, f"✅ {code} ishlatildi deb belgilandi.")
    if not u:
        return
    clear = lambda: api("editMessageReplyMarkup", chat_id=uid, message_id=mid, reply_markup={"inline_keyboard": []})

    if data.startswith("p:") and u["state"] == "reg_product":
        key = data[2:]
        clear()
        upd(uid, product=key)
        send(uid, f"Tanlandi: <b>{prod_name(key)}</b> ✅")
        return ask_date(uid)
    if data.startswith("d:") and u["state"] == "reg_date":
        clear()
        if data == "d:manual":
            return send(uid, "Sanani yozing, masalan: <b>" + d2s(today() - timedelta(days=3)) + "</b>")
        return set_start(uid, today() - timedelta(days=int(data[2:])))
    if data == "media:skip" and u["state"] == "media":
        clear()
        return send_offer(uid)
    if data.startswith("offer:") and u["state"] == "offer":
        clear()
        if data == "offer:later":
            upd(uid, offer_status="later", offer_at=iso(now()))
            return send(uid, f"Mayli 😊 {OFFER_REMIND_DAYS} kundan keyin yana eslatamiz.\n"
                             "O'zingiz xohlagan paytda /oyin deb yozishingiz ham mumkin.")
        upd(uid, offer_status="yes")
        if u["phone_ok"]:
            return game_cmd(u)
        return ask_phone(uid)
    if data.startswith("ph:") and u["state"] == "phone_confirm":
        clear()
        if data == "ph:no":
            return ask_phone(uid)
        return phone_confirmed(uid)


def handle_update(up):
    try:
        if "message" in up:
            handle_message(up["message"])
        elif "callback_query" in up:
            handle_callback(up["callback_query"])
        elif "my_chat_member" in up:
            m = up["my_chat_member"]
            if m.get("new_chat_member", {}).get("status") == "kicked":
                upd(m["from"]["id"], blocked=1)
    except Exception:
        log("Xato:", traceback.format_exc())


# ------------------------------------------------------------------ rejalashtirilgan ishlar
def scheduler_tick():
    n = now()
    t = n.date()
    hour_ok = SEND_FROM <= n.hour < SEND_TO

    # 1) 20-kun: natija so'rash
    if hour_ok:
        for u in db.execute("SELECT * FROM users WHERE state='active' AND blocked=0 AND start_date IS NOT NULL").fetchall():
            if parse_date(u["start_date"]) + timedelta(days=RESULT_DAY) <= t:
                ask_result(u)
        # natija so'ralgan, 2 kun javob yo'q -> bir marta eslatish
        for u in db.execute("SELECT * FROM users WHERE state='natija' AND result_reminded=0 AND blocked=0").fetchall():
            if from_iso(u["result_asked_at"]) + timedelta(days=2) <= n:
                upd(u["id"], result_reminded=1)
                send(u["id"], "👋 Farzandingizning 20 kunlik natijasini hali yubormadingiz. "
                              "1 daqiqa vaqt ajratsangiz, sizni sovg'a kutmoqda 🎁",
                     webapp_kb("📝 Natijani ulashish", natija_url(u)))
        # "Keyingi safar" -> 2 kundan keyin bir marta qayta taklif
        for u in db.execute("SELECT * FROM users WHERE state='offer' AND offer_status='later' AND offer_reminded=0 AND blocked=0").fetchall():
            if from_iso(u["offer_at"]) + timedelta(days=OFFER_REMIND_DAYS) <= n:
                upd(u["id"], offer_reminded=1)
                send(u["id"], "👋 Eslatib qo'yamiz: o'yinimiz sizni kutmoqda!")
                send_offer(u["id"])

    # 2) Kechki eslatmalar
    if (n.hour, n.minute) >= REMIND_HOUR and n.hour < 22:
        for u in db.execute("SELECT * FROM users WHERE blocked=0 AND (last_remind IS NULL OR last_remind<?)", (t.isoformat(),)).fetchall():
            msg, kb = None, None
            if u["phone_ok"] and u["game_open_at"] and (u["best_level"] or 0) < 5 and game_open(u):
                u = refresh_attempts(u)
                opened = from_iso(u["game_open_at"]).date()
                day = (t - opened).days
                last_day = opened + timedelta(days=GAME_DAYS - 1)
                if day >= 1 and (u["attempts_left"] or 0) > 0:
                    nxt = PCT[(u["best_level"] or 0) + 1]
                    if t == last_day:
                        msg = (f"⏳ <b>Bugun o'yinning oxirgi kuni!</b>\n\nHozirgi chegirmangiz: <b>{u['best_pct'] or 0}%</b>. "
                               f"Yana {u['attempts_left']} ta urinish bilan <b>{nxt}%</b> gacha oshirishingiz mumkin 💪")
                    else:
                        msg = (f"🎮 Bugungi urinishlaringiz tayyor ({u['attempts_left']} ta)!\n\n"
                               f"Hozirgi chegirmangiz: <b>{u['best_pct'] or 0}%</b>. Keyingi daraja: <b>{nxt}%</b> 🎁")
                    kb = webapp_kb("🎮 O'yinni boshlash", game_url(u))
            if not msg and u["code"] and not u["code_used"] and u["code_exp"]:
                if parse_date(u["code_exp"]) - timedelta(days=3) == t:
                    msg = (f"🎟 <b>{u['best_pct']}% chegirma kodingiz 3 kundan keyin tugaydi!</b>\n\n"
                           f"Kod: <code>{u['code']}</code>\nYangi mahsulot buyurtma qilish uchun kuratoringizga yozing 💚")
            if msg:
                upd(u["id"], last_remind=t.isoformat())
                send(u["id"], msg, kb)
            # muddati tugagan o'yinlarni yopish
            if u["state"] == "ready" and u["game_open_at"] and not game_open(u):
                upd(u["id"], state="done")


# ------------------------------------------------------------------ ishga tushirish
def main():
    if not BOT_TOKEN:
        sys.exit("BOT_TOKEN topilmadi. .env faylini to'ldiring (README_uz.md ga qarang).")
    if not WEBAPP_URL:
        log("Diqqat: WEBAPP_URL bo'sh, o'yin va so'rovnoma ochilmaydi.")
    db_init()
    me = api("getMe")
    log("Bot ishga tushdi:", me and me.get("username"))
    api("setMyName", name=BOT_TITLE)
    api("setMyShortDescription", short_description="Farzandingizning 20 kunlik natijasi va sovg'ali o'yin 🎁")
    api("setMyDescription", description=(f"{BOT_TITLE} 💚\n\nFarzandingizning Vitaway bilan 20 kunlik natijasini kuzatamiz. "
                                         "Natijangizni ulashing va qiziqarli o'yinda 20% gacha chegirma yutib oling!"))
    api("setMyCommands", commands=[{"command": "start", "description": "Boshlash"},
                                   {"command": "oyin", "description": "O'yin"},
                                   {"command": "kodim", "description": "Chegirma kodim"}])
    offset = int(kv_get("offset", "0"))
    last_tick = 0
    while True:
        try:
            ups = api("getUpdates", offset=offset, timeout=25,
                      allowed_updates=["message", "callback_query", "my_chat_member"]) or []
            for up in ups:
                offset = up["update_id"] + 1
                handle_update(up)
            if ups:
                kv_set("offset", offset)
        except Exception:
            log("Polling xato:", traceback.format_exc())
            time.sleep(5)
        if time.time() - last_tick > 60:
            last_tick = time.time()
            try:
                scheduler_tick()
            except Exception:
                log("Scheduler xato:", traceback.format_exc())


if __name__ == "__main__":
    main()
