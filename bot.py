# -*- coding: utf-8 -*-
"""
Vitaway Bolajon bot.

Mahsulotni 20 kun ichgan mijozlarga beriladi:
  1) xarid raqami  2) 20 kunlik natija (animatsiyali so'rovnoma)  3) o'yin taklifi
  4) 21-kundan boshlab har kuni holat so'raladi:
     yaxshi  -> xursandlik + otzivlar guruhiga
     yomon   -> mutaxassislar guruhiga murojaat, mutaxassis javobi mijozga yetkaziladi
     ikkala holatda ham o'yin chiroyli taklif qilinadi.

Faqat Python 3.9+ standart kutubxonasi kerak. Excel uchun: pip install openpyxl
"""
import json
import os
import random
import re
import sqlite3
import sys
import time
import traceback
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------ sozlamalar
def load_env(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env(os.path.join(HERE, ".env"))

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in re.findall(r"-?\d+", os.environ.get("ADMIN_IDS", ""))}
WEBAPP_URL = os.environ.get("WEBAPP_URL", "").rstrip("/")
BOT_TITLE = os.environ.get("BOT_TITLE", "Vitaway Bolajon")
DB_PATH = os.environ.get("DB_PATH", os.path.join(HERE, "vitaway.db"))
TZ = timezone(timedelta(hours=int(os.environ.get("TZ_HOURS", "5"))))
ASSETS = os.path.join(HERE, "assets")
DEFAULT_WEBAPP = "https://spotless393-netizen.github.io/vitaway/webapp"

START_DAY = 20           # bot mijozga mahsulotning nechanchi kunida beriladi
DAILY_DAYS = 10          # 20-kundan keyin necha kun har kuni holat so'raladi (21..30)
CHECKIN_HOUR = int(os.environ.get("CHECKIN_HOUR", "19"))  # kunlik so'rov soati
STOP_AFTER_MISSES = 3    # ketma-ket shuncha javobsiz qolsa, kunlik so'rov to'xtaydi
GAME_DAYS = 10           # o'yin ochilgandan keyin necha kun o'ynash mumkin
DAILY_ATTEMPTS = 3
MAX_ATTEMPTS = 9
CODE_HOURS = 48          # chegirma kodi necha soat amal qiladi
REMIND_LEFT_HOURS = 12   # tugashiga shuncha soat qolganda bir marta eslatiladi
SEND_GAP = 0.05          # ko'p xabar ketma-ket yuborilganda oraliq (Telegram limiti uchun)
PCT = {0: 0, 1: 3, 2: 7, 3: 11, 4: 15, 5: 20}
MIN_LEVEL_SEC = 8

AREA_NAMES = {
    "ishtaha": "Ishtaha", "qorin": "Qorin og'rig'i", "kasal": "Kasallanish", "diqqat": "Diqqat",
    "uyqu": "Uyqu", "harakat": "Faollik", "kayfiyat": "Kayfiyat", "asab": "Asabiylik",
    "oyoq": "Oyoq og'rig'i", "tish": "Tish g'ichirlatish",
}
SCALE_NAMES = {3: "Ancha yaxshilandi", 2: "Biroz yaxshilandi", 1: "O'zgarmadi", 0: "Yomonlashdi"}
MOODS = {4: ("😍", "Juda yaxshi"), 3: ("🙂", "Yaxshi"), 2: ("😐", "O'zgarish sezmadim"), 1: ("😟", "Yomonroq")}

# Menyu tugmalari
B_GAME = "🎮 O'yin"
B_CODE = "🎟 Chegirmam"
B_HELP = "💬 Mutaxassis"
B_ABOUT = "ℹ️ Vitaway haqida"
B_RESULT = "📝 Natijani ulashish"

HAPPY = ["Bundan juda xursandmiz! 🥰", "Qanday yaxshi! Bu biz uchun eng katta quvonch 💚",
         "Ajoyib yangilik! Farzandingiz bilan faxrlanamiz 🌟", "Zo'r! Har bir yaxshi kun muhim 💚"]


def now():
    return datetime.now(TZ)


def today():
    return now().date()


def log(*a):
    print(now().strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


# ------------------------------------------------------------------ Telegram API
API = "https://api.telegram.org/bot{}/{}"


def api(method, _try=0, **params):
    data = json.dumps({k: v for k, v in params.items() if v is not None}).encode()
    req = urllib.request.Request(API.format(BOT_TOKEN, method), data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            res = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            res = json.loads(e.read().decode() or "{}")
        except Exception:
            res = {}
    except Exception as e:
        if method != "getUpdates" and _try < 2:   # vaqtinchalik internet uzilishi: yana urinib ko'ramiz
            time.sleep(1 + _try)
            return api(method, _try + 1, **params)
        log("Tarmoq xatosi", method, e)
        return None
    if not res.get("ok"):
        wait = (res.get("parameters") or {}).get("retry_after")
        if res.get("error_code") == 429 and wait and _try < 3:   # Telegram «sekinroq» dedi: kutib, qayta yuboramiz
            log(f"Telegram limiti: {wait} s kutamiz", method)
            time.sleep(min(int(wait), 30) + 0.5)
            return api(method, _try + 1, **params)
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


def typing(chat_id, pause=0.0):
    api("sendChatAction", chat_id=chat_id, action="typing")
    if pause:
        time.sleep(min(pause, 0.3))   # ko'p mijoz bir vaqtda yozganda bot sekinlashmasin


def send_anim(chat_id, key, caption, kb=None):
    """assets/<key>.mp4 ni matn bilan yuboradi; birinchi marta yuklaydi, keyin file_id ishlatadi."""
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


def send_video(chat_id, key, caption, kb=None):
    """assets/<key>.mp4 ni ovozli video sifatida yuboradi (file_id keshlanadi)."""
    path = os.path.join(ASSETS, key + ".mp4")
    ck = "video:" + key + ":" + str(os.path.getsize(path) if os.path.exists(path) else 0)  # video yangilansa, kesh ham yangilanadi
    fid = kv_get(ck)
    if fid:
        r = api("sendVideo", chat_id=chat_id, video=fid, caption=caption, parse_mode="HTML",
                reply_markup=kb, supports_streaming=True)
        if r:
            return r
    if os.path.exists(path):
        with open(path, "rb") as f:
            r = api_file("sendVideo", "video", key + ".mp4", f.read(), chat_id=str(chat_id), caption=caption,
                         parse_mode="HTML", reply_markup=kb, width="640", height="640", supports_streaming="true")
        if r and r.get("video"):
            kv_set(ck, r["video"]["file_id"])
            return r
    return send_anim(chat_id, "welcome", caption, kb)


def ikb(*rows):
    out = []
    for row in rows:
        r = []
        for t, d in row:
            r.append({"text": t, "url": d[4:]} if d.startswith("url:") else {"text": t, "callback_data": d})
        out.append(r)
    return {"inline_keyboard": out}


def webapp_kb(text, url):
    return {"keyboard": [[{"text": text, "web_app": {"url": url}}]], "resize_keyboard": True, "is_persistent": True}


REMOVE_KB = {"remove_keyboard": True}

# ------------------------------------------------------------------ ma'lumotlar bazasi
db = None

TABLES = {
    "users": """id INTEGER PRIMARY KEY, first_name TEXT, username TEXT, created_at TEXT, state TEXT,
        start_date TEXT, buy_phone TEXT, tg_phone TEXT, phone_ok INTEGER DEFAULT 0, in_list INTEGER,
        result_asked_at TEXT, result_reminded INTEGER DEFAULT 0, result_done_at TEXT,
        offer_status TEXT DEFAULT '', offer_at TEXT,
        game_open_at TEXT, attempts_left INTEGER DEFAULT 0, attempts_day TEXT,
        best_level INTEGER DEFAULT 0, best_pct INTEGER DEFAULT 0,
        code TEXT, code_exp TEXT, code_used INTEGER DEFAULT 0, code_used_by INTEGER, code_used_at TEXT,
        checkin_last TEXT, checkin_answered TEXT, checkin_misses INTEGER DEFAULT 0, checkin_stop INTEGER DEFAULT 0,
        pending TEXT, pending_ref INTEGER, last_remind TEXT, blocked INTEGER DEFAULT 0""",
    "results": """id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, created_at TEXT, who TEXT, child TEXT,
        age TEXT, scores TEXT, text TEXT, stars INTEGER, rec TEXT, consent TEXT, raw TEXT""",
    "checkins": """id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, created_at TEXT, day_no INTEGER,
        mood INTEGER, text TEXT""",
    "tickets": """id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, created_at TEXT, source TEXT, text TEXT,
        status TEXT DEFAULT 'yangi', handled_by TEXT, handled_at TEXT""",
    "relay": """msg_id INTEGER PRIMARY KEY, user_id INTEGER, ticket_id INTEGER""",
    "orders": """id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, created_at TEXT, code TEXT, pct INTEGER,
        code_exp TEXT, status TEXT DEFAULT 'yangi', handled_by TEXT, handled_at TEXT""",
    "media": """id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, created_at TEXT, kind TEXT, file_id TEXT,
        text TEXT, source TEXT""",
    "plays": """id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, created_at TEXT, start INTEGER, reached INTEGER,
        pct INTEGER, dur INTEGER, how TEXT, suspicious INTEGER DEFAULT 0, raw TEXT""",
    "buyers": """phone TEXT PRIMARY KEY""",
    "kv": """k TEXT PRIMARY KEY, v TEXT""",
}


def db_init(path=None):
    """Jadvallarni yaratadi va eski bazaga yetishmayotgan ustunlarni qo'shadi."""
    global db
    db = sqlite3.connect(path or DB_PATH)
    db.row_factory = sqlite3.Row
    for name, cols in TABLES.items():
        db.execute(f"CREATE TABLE IF NOT EXISTS {name}({cols})")
        have = {r[1] for r in db.execute(f"PRAGMA table_info({name})")}
        for col in cols.split(","):
            parts = col.strip().split()
            if parts and parts[0] not in have and "PRIMARY" not in col:
                db.execute(f"ALTER TABLE {name} ADD COLUMN {' '.join(parts)}")
    db.commit()


def get_user(uid):
    return db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def upd(uid, **f):
    if f:
        db.execute(f"UPDATE users SET {', '.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), uid))
        db.commit()


def kv_get(k, default=None):
    r = db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return r["v"] if r else default


def kv_set(k, v):
    db.execute("INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)", (k, str(v)))
    db.commit()


# ------------------------------------------------------------------ yordamchilar
def d2s(d):
    return d.strftime("%d.%m.%Y") if d else ""


def parse_date(s):
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def code_deadline(s):
    """Chegirma tugash vaqti (datetime). Eski bazada faqat sana bo'lsa: o'sha kun oxiri."""
    if not s:
        return None
    try:
        if "T" in s:
            return datetime.fromisoformat(s)
        return datetime.combine(date.fromisoformat(s), datetime.max.time().replace(microsecond=0), tzinfo=TZ)
    except Exception:
        return None


def dt2s(dt):
    return dt.strftime("%d.%m.%Y, %H:%M") if dt else ""


def left_str(dt):
    sec = int((dt - now()).total_seconds()) if dt else 0
    if sec <= 0:
        return "muddati tugagan"
    h, m = sec // 3600, sec % 3600 // 60
    return f"{h} soat {m} daqiqa" if h else f"{m} daqiqa"


def code_state(u):
    """'used' | 'expired' | 'active' | None"""
    if not u["code"]:
        return None
    if u["code_used"]:
        return "used"
    dl = code_deadline(u["code_exp"])
    return "expired" if not dl or dl <= now() else "active"


def open_order(u):
    return db.execute("SELECT * FROM orders WHERE user_id=? AND code=? ORDER BY id DESC LIMIT 1",
                      (u["id"], u["code"])).fetchone() if u["code"] else None


def iso(dt):
    return dt.isoformat(timespec="seconds")


def from_iso(s):
    return datetime.fromisoformat(s) if s else None


def norm_phone(s):
    d = re.sub(r"\D", "", s or "")
    if len(d) == 9:
        d = "998" + d
    return "+" + d if len(d) == 12 and d.startswith("998") else None


def pretty_phone(p):
    d = re.sub(r"\D", "", p or "")
    return f"+{d[:3]} {d[3:5]} {d[5:8]} {d[8:10]} {d[10:12]}" if len(d) == 12 else (p or "")


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def is_admin(uid):
    return uid in ADMIN_IDS


def day_no(u):
    d = parse_date(u["start_date"])
    return (today() - d).days if d else START_DAY


def who(u):
    name = esc(u["first_name"] or "Mijoz")
    un = f" (@{u['username']})" if u["username"] else ""
    return f"{name}{un}"


def otziv_chat():
    v = kv_get("otziv_chat") or os.environ.get("OTZIV_CHAT_ID", "")
    return int(v) if re.fullmatch(r"-?\d+", str(v or "")) else None


def qayta_targets():
    v = kv_get("qayta_chat") or os.environ.get("QAYTA_CHAT_ID", "")
    return [int(v)] if re.fullmatch(r"-?\d+", str(v or "")) else sorted(ADMIN_IDS)


def specialist_targets():
    v = kv_get("mutaxassis_chat") or os.environ.get("MUTAXASSIS_CHAT_ID", "")
    return [int(v)] if re.fullmatch(r"-?\d+", str(v or "")) else sorted(ADMIN_IDS)


def new_code(pct):
    while True:
        c = f"VW-{pct}-{random.randint(1000, 9999)}"
        if not db.execute("SELECT 1 FROM users WHERE code=?", (c,)).fetchone():
            return c


def game_url(u):
    return (f"{WEBAPP_URL}/game.html?start={min(5, (u['best_level'] or 0) + 1)}"
            f"&best={u['best_pct'] or 0}&att={u['attempts_left'] or 0}")


def natija_url(u):
    return f"{WEBAPP_URL}/natija.html?p=vitaway"


def game_open(u):
    if not u["game_open_at"]:
        return False
    return today() <= from_iso(u["game_open_at"]).date() + timedelta(days=GAME_DAYS - 1)


def can_play(u):
    return bool(u["game_open_at"]) and game_open(u) and (u["best_level"] or 0) < 5 and (u["attempts_left"] or 0) > 0


def refresh_attempts(u):
    if not u["game_open_at"] or not game_open(u):
        return u
    last = parse_date(u["attempts_day"]) or today()
    days = (today() - last).days
    if days > 0:
        upd(u["id"], attempts_left=min(MAX_ATTEMPTS, (u["attempts_left"] or 0) + DAILY_ATTEMPTS * days),
            attempts_day=today().isoformat())
        u = get_user(u["id"])
    return u


def menu_kb(u):
    """Doimiy menyu. O'yin ochiq bo'lsa, «O'yin» tugmasi o'yinni to'g'ridan-to'g'ri ochadi."""
    u = refresh_attempts(u)
    if not u["result_done_at"]:
        first = {"text": B_RESULT, "web_app": {"url": natija_url(u)}}
    elif can_play(u):
        first = {"text": B_GAME, "web_app": {"url": game_url(u)}}
    else:
        first = {"text": B_GAME}
    return {"keyboard": [[first], [{"text": B_CODE}, {"text": B_HELP}], [{"text": B_ABOUT}]],
            "resize_keyboard": True, "is_persistent": True}


def set_pending(uid, what=None, ref=None):
    upd(uid, pending=what, pending_ref=ref)


# ------------------------------------------------------------------ 1. Boshlash va raqam
def start_cmd(msg):
    uid = msg["from"]["id"]
    fr = msg["from"]
    u = get_user(uid)
    if not u:
        db.execute("INSERT INTO users(id, first_name, username, created_at, state, start_date) VALUES(?,?,?,?,?,?)",
                   (uid, fr.get("first_name", ""), fr.get("username", ""), iso(now()), "phone",
                    (today() - timedelta(days=START_DAY)).isoformat()))
        db.commit()
        u = get_user(uid)
    else:
        upd(uid, first_name=fr.get("first_name", ""), username=fr.get("username", ""))
        if u["phone_ok"]:
            return home(u, greet=True)

    send_video(uid, "intro",
               f"Assalomu alaykum, <b>{esc(fr.get('first_name', ''))}</b>! 👋\n\n"
               "Vitaway'ni ichishni boshlaganingizga ancha bo'ldi 💚\n"
               "<b>Kichkintoyimizning holati qanday?</b> Ishtahasi, uyqusi, kayfiyati o'zgardimi?\n\n"
               "Keling, birga ko'rib chiqamiz. Sizni esa kichik sovg'a kutmoqda 🎁\n\n"
               "🔊 <i>Videoni ovoz bilan ko'ring</i>", REMOVE_KB)
    typing(uid, 1.5)
    ask_phone(uid)


def ask_phone(uid):
    upd(uid, state="phone")
    send(uid, "📱 Boshlashdan oldin bitta savol: mahsulotni <b>qaysi telefon raqamidan</b> xarid qilgansiz?\n\n"
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
        return send(uid, "❗️ Raqam noto'g'ri ko'rinadi. Iltimos, shunday yozing: <b>+998 90 123 45 67</b>")
    upd(uid, buy_phone=p, state="phone_confirm")
    send(uid, "Rahmat!", REMOVE_KB)
    send(uid, f"📞 <b>{pretty_phone(p)}</b>\n\nMahsulotni aynan shu raqamdan xarid qilganmisiz?",
         ikb([("✅ Ha, to'g'ri", "ph:yes")], [("✏️ Yo'q, o'zgartiraman", "ph:no")]))


def phone_confirmed(uid):
    u = get_user(uid)
    in_list = None
    if db.execute("SELECT 1 FROM buyers LIMIT 1").fetchone():
        in_list = 1 if db.execute("SELECT 1 FROM buyers WHERE phone=?", (u["buy_phone"],)).fetchone() else 0
    upd(uid, phone_ok=1, in_list=in_list)
    u = get_user(uid)
    if u["result_done_at"]:
        return start_game(u)
    ask_result(u)


# ------------------------------------------------------------------ 2. 20 kunlik natija
def ask_result(u, again=False):
    uid = u["id"]
    if not again:
        upd(uid, state="natija", result_asked_at=iso(now()))
    kb = webapp_kb(B_RESULT, natija_url(get_user(uid)))
    if again:
        return send(uid, "📝 Kichkintoyimizdagi natijani ulashish uchun pastdagi "
                         "<b>«📝 Natijani ulashish»</b> tugmasini bosing 👇", kb)
    typing(uid, 0.8)
    send(uid, "Rahmat! ✅\n\nEndi kichkintoyimizdagi o'zgarishlarni bilib olamiz. Pastdagi "
              "<b>«📝 Natijani ulashish»</b> tugmasini bosing: 6 ta oddiy savol, bor-yo'g'i 1 daqiqa 💚", kb)


def on_natija(u, data):
    uid = u["id"]
    sc = {k: v for k, v in (data.get("sc") or {}).items() if isinstance(v, int)}
    db.execute("INSERT INTO results(user_id, created_at, who, child, age, scores, text, stars, rec, consent, raw)"
               " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
               (uid, iso(now()), str(data.get("who", ""))[:40], str(data.get("child", ""))[:60],
                str(data.get("age", ""))[:10], json.dumps(sc, ensure_ascii=False), str(data.get("text", ""))[:2000],
                int(data.get("stars") or 0), str(data.get("rec", ""))[:40], str(data.get("ok", ""))[:40],
                json.dumps(data, ensure_ascii=False)[:4000]))
    db.commit()
    upd(uid, result_done_at=iso(now()))
    better = sum(1 for v in sc.values() if v >= 2)
    worse = sum(1 for v in sc.values() if v == 0)
    stars = int(data.get("stars") or 0)

    txt = "💚 <b>Rahmat! Natijangiz saqlandi.</b>"
    if better:
        txt += f"\n\nSiz <b>{len(sc)} ta</b> yo'nalishdan <b>{better} tasida</b> yaxshilanish sezdingiz. Bu ajoyib natija! 👏"
    send(uid, txt, REMOVE_KB)

    # Otzivlar guruhiga
    lines = [f"📝 <b>20 kunlik natija</b> · {who(u)}", f"📞 {pretty_phone(u['buy_phone'])}"]
    if data.get("child") or data.get("age"):
        lines.append(f"👶 {esc(str(data.get('child', '')))} {esc(str(data.get('age', '')))} yosh".strip())
    for k, v in sc.items():
        lines.append(f"• {AREA_NAMES.get(k, k)}: {SCALE_NAMES.get(v, v)}")
    if stars:
        lines.append("⭐" * stars)
    if data.get("text"):
        lines.append(f"💬 «{esc(str(data['text']))[:900]}»")
    lines.append(f"📣 Rozilik: {esc(str(data.get('ok', '-')))}")
    post_otziv("\n".join(lines))

    if worse or (stars and stars <= 2):
        make_ticket(u, "20 kunlik natija", "So'rovnomada norozilik: " + ", ".join(
            AREA_NAMES.get(k, k) for k, v in sc.items() if v == 0) + (f"; {stars}⭐" if stars else ""))
        send(uid, "🤝 Ba'zi yo'nalishlarda o'zgarish sezmaganingizni ko'rdik. "
                  "Mutaxassisimiz siz bilan bog'lanib, maslahat beradi.")
    upd(uid, state="idle")
    typing(uid, 0.8)
    offer_game(get_user(uid))
    typing(uid, 0.5)
    send(uid, "🎙 <i>Kichkintoyimiz haqida ovozli xabar, video yoki rasm yubormoqchi bo'lsangiz, "
              "istalgan payt shu chatga tashlang. Boshqa ota-onalarga katta yordam bo'ladi 🙏</i>")


def ask_media(uid, voice_first=False):
    upd(uid, state="media")
    t = ("🎙 Xohlasangiz, farzandingiz haqida qisqa <b>ovozli xabar</b>, <b>video</b> yoki <b>rasm</b> yuboring.\n\n"
         "Sizning tajribangiz boshqa ota-onalarga katta yordam beradi 🙏")
    if voice_first:
        t = "🎙 Ovozli xabar yuborishni aytgan edingiz, hoziroq yozib yuborishingiz mumkin!\n\n" + t
    send(uid, t, ikb([("O'tkazib yuborish ➡️", "media:skip")]))


def save_media(u, msg, source):
    """Xabardan media yoki matnni ajratib saqlaydi. (kind, file_id, text) qaytaradi yoki None."""
    kind, fid, text = None, None, msg.get("caption") or ""
    for k in ("voice", "video_note", "video", "audio", "document"):
        if k in msg:
            kind, fid = k, msg[k]["file_id"]
            break
    else:
        if "photo" in msg:
            kind, fid = "photo", msg["photo"][-1]["file_id"]
        elif msg.get("text"):
            kind, text = "text", msg["text"]
    if not kind:
        return None
    db.execute("INSERT INTO media(user_id, created_at, kind, file_id, text, source) VALUES(?,?,?,?,?,?)",
               (u["id"], iso(now()), kind, fid, text[:2000], source))
    db.commit()
    return kind, fid, text


# ------------------------------------------------------------------ otziv va mutaxassis guruhlari
def post_otziv(text, copy_from=None):
    chat = otziv_chat()
    targets = [chat] if chat else sorted(ADMIN_IDS)
    for t in targets:
        send(t, text)
        if copy_from:
            api("copyMessage", chat_id=t, from_chat_id=copy_from[0], message_id=copy_from[1])


def make_ticket(u, source, text, copy_from=None):
    db.execute("INSERT INTO tickets(user_id, created_at, source, text) VALUES(?,?,?,?)",
               (u["id"], iso(now()), source, (text or "")[:2000]))
    db.commit()
    tid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    body = (f"🆘 <b>Murojaat #{tid}</b> · {esc(source)}\n"
            f"👤 {who(u)}\n📞 <b>{pretty_phone(u['buy_phone'] or u['tg_phone'])}</b>\n"
            f"📅 Mahsulotning {day_no(u)}-kuni\n\n{esc(text or '')}\n\n"
            "↩️ <i>Shu xabarga javob (Reply) yozsangiz, javobingiz mijozga yetkaziladi.</i>")
    kb = ikb([("✅ Bog'lanildi", f"tk:{tid}")])
    for chat in specialist_targets():
        r = send(chat, body, kb)
        if r:
            db.execute("INSERT OR REPLACE INTO relay(msg_id, user_id, ticket_id) VALUES(?,?,?)", (r["message_id"], u["id"], tid))
        if copy_from:
            c = api("copyMessage", chat_id=chat, from_chat_id=copy_from[0], message_id=copy_from[1])
            if c:
                db.execute("INSERT OR REPLACE INTO relay(msg_id, user_id, ticket_id) VALUES(?,?,?)", (c["message_id"], u["id"], tid))
    db.commit()
    return tid


def add_to_ticket(u, tid, msg):
    """Mijozning qo'shimcha xabarini mavjud murojaatga ilova qiladi."""
    got = save_media(u, msg, "murojaat")
    if not got:
        return
    kind, _, text = got
    if text:
        db.execute("UPDATE tickets SET text=COALESCE(text,'') || ? WHERE id=?", ("\n" + text[:1500], tid))
        db.commit()
    for chat in specialist_targets():
        r = send(chat, f"➕ <b>Murojaat #{tid}</b> davomi · {who(u)}" + (f"\n\n{esc(text)}" if kind == "text" else ""))
        if r:
            db.execute("INSERT OR REPLACE INTO relay(msg_id, user_id, ticket_id) VALUES(?,?,?)", (r["message_id"], u["id"], tid))
        if kind != "text":
            c = api("copyMessage", chat_id=chat, from_chat_id=u["id"], message_id=msg["message_id"])
            if c:
                db.execute("INSERT OR REPLACE INTO relay(msg_id, user_id, ticket_id) VALUES(?,?,?)", (c["message_id"], u["id"], tid))
    db.commit()


# ------------------------------------------------------------------ 3. O'yin
def offer_game(u, intro=None):
    """O'yinni holatga qarab chiroyli taklif qiladi. Hech narsa taklif qilinmasa False."""
    uid = u["id"]
    u = refresh_attempts(u)
    if (u["best_level"] or 0) >= 5:
        return False
    if not u["game_open_at"]:
        upd(uid, state="offer", offer_at=iso(now()))
        send_anim(uid, "offer", (intro + "\n\n" if intro else "") +
                  "🎁 <b>Sizga sovg'amiz bor!</b>\n\nXohlasangiz, qiziqarli o'yinimizni o'ynab, yangi Vitaway uchun "
                  "<b>20% gacha chegirma</b> yutib olishingiz mumkin 🧺",
                  ikb([("🎮 Ha, sinab ko'raman", "offer:yes")], [("⏰ Keyingi safar", "offer:later")]))
        return True
    if can_play(u):
        nxt = PCT[(u["best_level"] or 0) + 1]
        send(uid, (intro + "\n\n" if intro else "") +
             f"🎮 Bugun <b>{u['attempts_left']} ta</b> urinishingiz bor. Hozirgi chegirmangiz: <b>{u['best_pct'] or 0}%</b>, "
             f"keyingi daraja <b>{nxt}%</b> gacha oshiradi!\n\nPastdagi <b>«{B_GAME}»</b> tugmasini bosing 👇",
             menu_kb(u))
        return True
    return False


def start_game(u):
    uid = u["id"]
    f = dict(state="idle", offer_status="yes")
    if not u["game_open_at"]:
        f.update(game_open_at=iso(now()), attempts_left=DAILY_ATTEMPTS, attempts_day=today().isoformat())
    upd(uid, **f)
    u = get_user(uid)
    typing(uid, 0.6)
    send(uid, "🧺 <b>Tayyorlaning!</b>\n\n"
              "Tepadan Vitaway mahsulotlari tushadi, siz ularni savatchaga yig'asiz. "
              "Har bir daraja chegirmani oshiradi: <b>3% → 7% → 11% → 15% → 20%</b>\n\n"
              f"🎮 Urinishlar: <b>{u['attempts_left']}</b> ta (har kuni yana 3 ta qo'shiladi)\n"
              "Qoidalar o'yin ichida tushuntiriladi.\n\n"
              f"O'yinni boshlashga tayyormisiz? Pastdagi <b>«{B_GAME}»</b> tugmasini bosing 👇", menu_kb(u))


def game_button(u):
    u = refresh_attempts(u)
    if not u["result_done_at"]:
        return ask_result(u, again=True)
    if (u["best_level"] or 0) >= 5:
        return send(uid_of(u), f"🏆 Siz eng yuqori natijaga erishgansiz!\n🎟 Kodingiz: <code>{u['code']}</code> ({u['best_pct']}%)", menu_kb(u))
    if not u["game_open_at"]:
        return offer_game(u)
    if not game_open(u):
        t = "⌛️ O'yin muddati tugagan."
        if u["code"]:
            t += f"\n🎟 Chegirma kodingiz: <code>{u['code']}</code> ({u['best_pct']}%)"
        return send(u["id"], t, menu_kb(u))
    if (u["attempts_left"] or 0) <= 0:
        return send(u["id"], "Bugungi urinishlar tugadi. Ertaga yana 3 ta urinish beriladi 😊", menu_kb(u))
    send(u["id"], "Pastdagi <b>«🎮 O'yin»</b> tugmasini bosing 👇", menu_kb(u))


def uid_of(u):
    return u["id"]


def on_game(u, data):
    uid = u["id"]
    u = refresh_attempts(u)
    if not can_play(u):
        return game_button(u)
    start = int(data.get("start") or 1)
    reached = int(data.get("reached") or 0)
    lv = data.get("lv") or []
    best = u["best_level"] or 0
    ok_levels = [x for x in lv if isinstance(x, dict) and x.get("ok")]
    suspicious = int(bool(
        (reached and (reached < start or reached > 5 or start > best + 1)) or
        (reached and len(ok_levels) != reached - start + 1) or
        any(int(x.get("s") or 0) < MIN_LEVEL_SEC for x in ok_levels)))
    db.execute("INSERT INTO plays(user_id, created_at, start, reached, pct, dur, how, suspicious, raw) VALUES(?,?,?,?,?,?,?,?,?)",
               (uid, iso(now()), start, reached, PCT.get(reached, 0), int(data.get("dur") or 0),
                str(data.get("how", ""))[:10], suspicious, json.dumps(data)[:3000]))
    db.commit()
    left = (u["attempts_left"] or 0) - 1
    upd(uid, attempts_left=left)
    if suspicious:
        for aid in ADMIN_IDS:
            send(aid, f"⚠️ Shubhali o'yin natijasi: {who(u)}, {reached}-daraja. /excel → O'yinlar")
        return send(uid, "🔎 Natijangiz tekshiruvga yuborildi. Iltimos, yana bir bor o'ynab ko'ring.", menu_kb(get_user(uid)))

    improved = reached > best
    consolation = (not improved) and best == 0 and left <= 0
    if improved or consolation:
        best = reached if improved else 1
        pct = PCT[best]
        exp = now() + timedelta(hours=CODE_HOURS)
        upd(uid, best_level=best, best_pct=pct, code=new_code(pct), code_exp=iso(exp), last_remind=None)
    u = get_user(uid)

    if improved or consolation:
        head = "🎉 <b>Tabriklaymiz!</b>" if improved else "💚 Ishtirokingiz uchun rahmat!"
        txt = (f"{head}\n\nSiz <b>{u['best_pct']}% chegirma</b> qo'lga kiritdingiz!\n\n"
               f"🎟 Chegirma kodingiz: <code>{u['code']}</code>\n"
               f"⏳ Faqat <b>{CODE_HOURS} soat</b> amal qiladi: <b>{dt2s(code_deadline(u['code_exp']))}</b> gacha\n\n"
               "Chegirmadan hoziroq foydalanmoqchi bo'lsangiz, pastdagi <b>«🛒 Qayta xarid»</b> tugmasini bosing, "
               "menejerimiz siz bilan bog'lanib, buyurtmani chegirma bilan rasmiylashtiradi 👇")
        (send_anim(uid, "win", txt, BUY_KB) if improved else send(uid, txt, BUY_KB))
        for aid in ADMIN_IDS:
            send(aid, f"🎟 {who(u)} — <b>{u['best_pct']}%</b> chegirma ({u['code']}), 📞 {pretty_phone(u['buy_phone'])}")
    else:
        send(uid, f"Bu safar natija o'zgarmadi. Joriy chegirmangiz: <b>{u['best_pct'] or 0}%</b>")

    if best >= 5:
        return send(uid, "🏆 Siz eng yuqori natijaga erishdingiz! Barakalla!", menu_kb(u))
    if left > 0:
        return send(uid, f"🎮 Yana <b>{left}</b> ta urinishingiz bor. Keyingi darajada <b>{PCT[best + 1]}%</b> gacha "
                         "oshirishingiz mumkin! 💪", menu_kb(u))
    send(uid, "Bugungi urinishlar tugadi. Ertaga yana 3 ta urinish beriladi 😊", menu_kb(u))


# ------------------------------------------------------------------ 4. Kunlik holat
def send_checkin(u):
    uid = u["id"]
    upd(uid, checkin_last=today().isoformat())
    n = day_no(u)
    send(uid, "☀️ Assalomu alaykum! Farzandingizning bugungi holati qanday?",
         ikb([(f"{MOODS[4][0]} {MOODS[4][1]}", "mood:4"), (f"{MOODS[3][0]} {MOODS[3][1]}", "mood:3")],
             [(f"{MOODS[2][0]} {MOODS[2][1]}", "mood:2"), (f"{MOODS[1][0]} {MOODS[1][1]}", "mood:1")]))


def on_mood(u, mood):
    uid = u["id"]
    n = day_no(u)
    db.execute("INSERT INTO checkins(user_id, created_at, day_no, mood) VALUES(?,?,?,?)", (uid, iso(now()), n, mood))
    db.commit()
    cid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    upd(uid, checkin_answered=today().isoformat(), checkin_misses=0)
    emoji, label = MOODS[mood]

    if mood >= 3:
        post_otziv(f"{emoji} <b>{label}</b> · {n}-kun\n👤 {who(u)} · 📞 {pretty_phone(u['buy_phone'])}")
        set_pending(uid, "good", cid)
        send(uid, f"{random.choice(HAPPY)}\n\nFarzandingizda bugun nimani sezdingiz? Bir-ikki so'z yozing "
                  "yoki ovozli xabar yuboring 🎙", ikb([("Keyinroq ➡️", "pend:skip")]))
    elif mood == 2:
        set_pending(uid, "neutral", cid)
        send(uid, "Tushunamiz 🤍 Har bir bolada natija o'z sur'atida ko'rinadi, ba'zan biroz ko'proq vaqt kerak bo'ladi.\n\n"
                  "Sizni biror narsa xavotirga solyaptimi? Yozib qoldiring, mutaxassisimiz maslahat beradi.",
             ikb([("💬 Mutaxassisga yozaman", "pend:help")], [("Hammasi joyida ➡️", "pend:skip")]))
    else:
        tid = make_ticket(u, f"Kunlik holat ({n}-kun): {label}", "Mijoz bugungi holatni «Yomonroq» deb belgiladi.")
        set_pending(uid, "bad", tid)
        send(uid, "Bu haqda eshitganimizdan afsusdamiz 😔\n\n"
                  "<b>Mutaxassislarimiz tez orada siz bilan bog'lanadi.</b> Nima bo'lganini qisqacha yozing "
                  "yoki ovozli xabar yuboring, uni darhol mutaxassisga yetkazamiz.\n\n"
                  "⚠️ Isitma baland bo'lsa, nafas qisilsa yoki kuchli og'riq bo'lsa, kutmasdan shifokorga murojaat qiling (103).",
             ikb([("Keyinroq ➡️", "pend:skip")]))


def on_pending(u, msg):
    """Kunlik holatdan keyingi matn/ovozli xabar."""
    uid = u["id"]
    kind = u["pending"]
    ref = u["pending_ref"]
    if kind == "good":
        got = save_media(u, msg, "kunlik otziv")
        if not got:
            return False
        if got[2]:
            db.execute("UPDATE checkins SET text=? WHERE id=?", (got[2][:2000], ref))
            db.commit()
        n = day_no(u)
        if got[0] == "text":
            post_otziv(f"💬 <b>Otziv</b> · {n}-kun · {who(u)}\n«{esc(got[2])[:1500]}»")
        else:
            post_otziv(f"🎙 <b>Otziv ({got[0]})</b> · {n}-kun · {who(u)}", copy_from=(uid, msg["message_id"]))
        set_pending(uid)
        send(uid, "Rahmat! Fikringiz Vitaway jamoasiga yetkazildi 💚")
        after_checkin(get_user(uid), "good")
        return True
    if kind in ("bad", "neutral", "help", "support"):
        if kind == "bad" and ref:
            tid = ref  # «Yomonroq» bosilganda murojaat allaqachon ochilgan
        else:
            src = {"neutral": f"Kunlik holat ({day_no(u)}-kun): o'zgarish sezmadim",
                   "help": f"Kunlik holat ({day_no(u)}-kun): xavotir"}.get(kind, "Mijoz savoli")
            tid = make_ticket(u, src, "")
        add_to_ticket(u, tid, msg)
        if msg.get("text") and kind in ("bad", "neutral", "help"):
            db.execute("UPDATE checkins SET text=? WHERE id=(SELECT MAX(id) FROM checkins WHERE user_id=?)", (msg["text"][:2000], uid))
            db.commit()
        set_pending(uid)
        send(uid, "✅ Xabaringiz mutaxassisga yetkazildi. Tez orada siz bilan bog'lanamiz 🤝", menu_kb(get_user(uid)))
        if kind in ("bad", "neutral", "help"):
            after_checkin(get_user(uid), "bad" if kind == "bad" else "neutral")
        return True
    return False


def after_checkin(u, mood_kind):
    intro = {"good": "Shunday quvonchli kunda kichik sovg'a ham yarashadi 😊",
             "neutral": "Aytgancha, sizni kichik sovg'a ham kutmoqda 😊",
             "bad": "Kayfiyatni biroz ko'tarish uchun sizni kichik sovg'a kutmoqda 🤍"}[mood_kind]
    typing(u["id"], 0.6)
    if not offer_game(u, intro):
        send(u["id"], "Ertaga yana so'raymiz. Sog'-salomat bo'linglar! 💚", menu_kb(u))


# ------------------------------------------------------------------ menyu
def about(u):
    send(u["id"], "💚 <b>Vitaway: Naturally for kids</b>\n\n"
                  "Bitta qutida 4 ta kompleks, bola hammasini birga ichadi:\n\n"
                  "🍏 <b>Neuro Complex</b> — nerv tizimi\n"
                  "🍌 <b>Immuno Complex</b> — immunitet\n"
                  "🍊 <b>Osteo Complex</b> — suyaklar\n"
                  "🍫 <b>Antihelmo Complex</b> — gijjaga qarshi\n\n"
                  "Qabul tartibi qutidagi yo'riqnomada. Savollaringiz bo'lsa, "
                  f"<b>«{B_HELP}»</b> tugmasini bosing.", menu_kb(u))


def my_code(u):
    if u["code"]:
        dl = code_deadline(u["code_exp"])
        stt = code_state(u)
        o = open_order(u)
        st = {"used": "✅ Ishlatilgan", "expired": "⌛️ Muddati tugagan",
              "active": f"🟢 Amalda, tugashiga <b>{left_str(dl)}</b> qoldi"}[stt]
        txt = (f"🎟 Chegirma kodingiz: <code>{u['code']}</code>\n"
               f"💰 Chegirma: <b>{u['best_pct']}%</b>\n⏳ Muddati: {dt2s(dl)} gacha\n{st}")
        if stt == "active" and o:
            return send(u["id"], txt + "\n\n🛒 Qayta xarid so'rovingiz qabul qilingan, menejerimiz siz bilan bog'lanadi.", menu_kb(u))
        if stt == "active":
            return send(u["id"], txt + "\n\nHoziroq foydalanish uchun <b>«🛒 Qayta xarid»</b> ni bosing 👇", BUY_KB)
        return send(u["id"], txt, menu_kb(u))
    send(u["id"], "Hozircha chegirma kodingiz yo'q. O'yinni o'ynab, 20% gacha chegirma yutib oling! 🎮", menu_kb(u))
    if u["result_done_at"]:
        game_button(u)


BUY_KB = {"inline_keyboard": [[{"text": "🛒 Qayta xarid", "callback_data": "buy"}]]}


def request_buy(u):
    """Mijoz «Qayta xarid» ni bosdi: so'rov «qayta xarid» guruhiga tushadi."""
    uid = u["id"]
    stt = code_state(u)
    if stt is None:
        return send(uid, "Hozircha chegirma kodingiz yo'q. O'yinni o'ynab, chegirma yutib oling! 🎮", menu_kb(u))
    if stt == "used":
        return send(uid, "Bu chegirma kodi allaqachon ishlatilgan ✅", menu_kb(u))
    if stt == "expired":
        return send(uid, "Afsuski, bu chegirmaning muddati tugagan ⌛️\n"
                         f"Savollaringiz bo'lsa, <b>«{B_HELP}»</b> tugmasi orqali yozing.", menu_kb(u))
    if open_order(u):
        return send(uid, "✅ So'rovingiz allaqachon qabul qilingan. Menejerimiz tez orada siz bilan bog'lanadi 🤝", menu_kb(u))
    dl = code_deadline(u["code_exp"])
    db.execute("INSERT INTO orders(user_id, created_at, code, pct, code_exp) VALUES(?,?,?,?,?)",
               (uid, iso(now()), u["code"], u["best_pct"], u["code_exp"]))
    db.commit()
    oid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    body = (f"🛒 <b>Qayta xarid #{oid}</b>\n"
            f"👤 {who(u)}\n📞 <b>{pretty_phone(u['buy_phone'] or u['tg_phone'])}</b>\n"
            f"🎟 Kod: <code>{u['code']}</code> · <b>{u['best_pct']}%</b> chegirma\n"
            f"⏳ Amal qiladi: {dt2s(dl)} gacha ({left_str(dl)} qoldi)\n\n"
            "Mijoz chegirmadan <b>hoziroq</b> foydalanmoqchi. Iltimos, tezroq qo'ng'iroq qiling.\n"
            "↩️ <i>Shu xabarga javob (Reply) yozsangiz, mijozga yetkaziladi.</i>")
    kb = ikb([("✅ Bog'lanildi", f"ob:{oid}")])
    for chat in qayta_targets():
        r = send(chat, body, kb)
        if r:
            db.execute("INSERT OR REPLACE INTO relay(msg_id, user_id, ticket_id) VALUES(?,?,?)", (r["message_id"], uid, -oid))
    db.commit()
    send(uid, f"✅ <b>So'rovingiz qabul qilindi!</b>\n\nMenejerimiz tez orada siz bilan bog'lanadi va buyurtmangizni "
              f"<b>{u['best_pct']}% chegirma</b> bilan rasmiylashtiradi 💚\n\n"
              f"📞 Raqamingiz: {pretty_phone(u['buy_phone'] or u['tg_phone'])}", menu_kb(u))


def help_button(u):
    set_pending(u["id"], "support", None)
    send(u["id"], "💬 Savolingiz yoki muammoingizni yozing (ovozli xabar ham bo'ladi). "
                  "Mutaxassisimiz shu yerning o'zida javob beradi.", ikb([("Bekor qilish", "pend:cancel")]))


def home(u, greet=False):
    uid = u["id"]
    if not u["phone_ok"]:
        return ask_phone(uid)
    if not u["result_done_at"]:
        return ask_result(u, again=True)
    if u["state"] == "media":
        return ask_media(uid)
    send(uid, ("Qaytganingizdan xursandmiz! 👋\n\n" if greet else "") + "Quyidagi menyudan foydalaning 👇", menu_kb(u))


# ------------------------------------------------------------------ admin
def admin_help(uid):
    send(uid, "<b>Admin buyruqlari</b>\n\n"
              "/stat — statistika\n"
              "/excel — hamma ma'lumotlar Excel'da\n"
              "/otzivlar — oxirgi ovozli xabar, video, rasmlar\n"
              "/kod VW-15-1234 — kodni tekshirish va «ishlatildi» deb belgilash\n"
              "/mijozlar — xaridorlar ro'yxatini yuklash\n"
              "/zaxira — bazaning nusxasini olish (vitaway.db faylini yuborsangiz, baza tiklanadi)\n\n"
              "<b>Guruhlarni ulash</b> (botni guruhga qo'shib, guruhda yozasiz):\n"
              "/ulash_otziv — yaxshi fikrlar shu guruhga tushadi\n"
              "/ulash_mutaxassis — murojaatlar shu guruhga tushadi\n"
              "/ulash_qaytaxarid — «🛒 Qayta xarid» so'rovlari shu guruhga tushadi\n\n"
              "<b>Sinov</b>:\n/test — o'zingizni yangi mijoz sifatida boshlash\n"
              "/kunlik — kunlik holat savolini hozir olish")


def admin_stat(uid):
    q = lambda sql: db.execute(sql).fetchone()[0]
    moods = db.execute("SELECT mood, COUNT(*) c FROM checkins GROUP BY mood ORDER BY mood DESC").fetchall()
    dist = db.execute("SELECT best_pct, COUNT(*) c FROM users WHERE best_pct>0 GROUP BY best_pct ORDER BY best_pct").fetchall()
    total = q("SELECT COUNT(*) FROM users")
    results = q("SELECT COUNT(DISTINCT user_id) FROM results")
    checks = q("SELECT COUNT(*) FROM checkins")
    tickets = q("SELECT COUNT(*) FROM tickets")
    new_t = q("SELECT COUNT(*) FROM tickets WHERE status='yangi'")
    media = q("SELECT COUNT(*) FROM media WHERE kind!='text'")
    opened = q("SELECT COUNT(*) FROM users WHERE game_open_at IS NOT NULL")
    won = q("SELECT COUNT(*) FROM users WHERE best_pct>0")
    used = q("SELECT COUNT(*) FROM users WHERE code_used=1")
    orders = q("SELECT COUNT(*) FROM orders")
    new_o = q("SELECT COUNT(*) FROM orders WHERE status='yangi'")
    send(uid, "📊 <b>Statistika</b>\n\n"
              f"👥 Mijozlar: <b>{total}</b>\n"
              f"📝 Natija yuborgan: <b>{results}</b>\n"
              f"☀️ Kunlik javoblar: <b>{checks}</b>\n"
              + "".join(f"   {MOODS[r['mood']][0]} {MOODS[r['mood']][1]} — {r['c']}\n" for r in moods if r['mood'] in MOODS) +
              f"🆘 Murojaatlar: <b>{tickets}</b> (javobsiz: {new_t})\n"
              f"🎙 Media otzivlar: <b>{media}</b>\n"
              f"🎮 O'yin ochgan: <b>{opened}</b>\n"
              f"🎟 Chegirma olgan: <b>{won}</b>\n"
              + "".join(f"   • {r['best_pct']}% — {r['c']} ta\n" for r in dist) +
              f"🛒 Qayta xarid so'rovlari: <b>{orders}</b> (bog'lanilmagan: {new_o})\n"
              f"✅ Kodni ishlatgan: <b>{used}</b>")


def build_excel():
    users = db.execute("SELECT * FROM users ORDER BY created_at").fetchall()
    res = db.execute("SELECT r.*, u.first_name, u.username, u.buy_phone FROM results r LEFT JOIN users u ON u.id=r.user_id ORDER BY r.id").fetchall()
    chk = db.execute("SELECT c.*, u.first_name, u.username, u.buy_phone FROM checkins c LEFT JOIN users u ON u.id=c.user_id ORDER BY c.id").fetchall()
    tks = db.execute("SELECT t.*, u.first_name, u.username, u.buy_phone, u.tg_phone FROM tickets t LEFT JOIN users u ON u.id=t.user_id ORDER BY t.id").fetchall()
    med = db.execute("SELECT m.*, u.first_name, u.username FROM media m LEFT JOIN users u ON u.id=m.user_id ORDER BY m.id").fetchall()
    plays = db.execute("SELECT p.*, u.first_name FROM plays p LEFT JOIN users u ON u.id=p.user_id ORDER BY p.id").fetchall()
    ords = db.execute("SELECT o.*, u.first_name, u.username, u.buy_phone, u.tg_phone, u.code_used FROM orders o "
                      "LEFT JOIN users u ON u.id=o.user_id ORDER BY o.id").fetchall()
    consent = {r["user_id"]: r["consent"] for r in res}
    at = lambda s: (s or "")[:16].replace("T", " ")
    un = lambda r: ("@" + r["username"]) if r["username"] else ""
    area_keys = list(AREA_NAMES)
    sheets = [
        ("Mijozlar", ["Telegram ID", "Ism", "Username", "Xarid raqami", "Ro'yxatda bormi", "Qo'shilgan",
                      "20 kunlik natija", "Oxirgi kunlik javob", "Daraja", "Chegirma %", "Kod", "Kod muddati", "Kod ishlatildi"],
         [[u["id"], u["first_name"], un(u), pretty_phone(u["buy_phone"]), {1: "Ha", 0: "Yo'q"}.get(u["in_list"], ""),
           at(u["created_at"]), "Ha" if u["result_done_at"] else "Yo'q", d2s(parse_date(u["checkin_answered"])),
           u["best_level"] or 0, u["best_pct"] or 0, u["code"] or "", dt2s(code_deadline(u["code_exp"])),
           "Ha" if u["code_used"] else ""] for u in users]),
        ("20 kunlik natija", ["Sana", "Ism", "Username", "Xarid raqami", "Kim to'ldirdi", "Bola ismi", "Yoshi"]
         + [AREA_NAMES[k] for k in area_keys] + ["Otziv matni", "Yulduz", "Tavsiya", "Foydalanishga rozilik"],
         [[at(r["created_at"]), r["first_name"], un(r), pretty_phone(r["buy_phone"]), r["who"], r["child"], r["age"]]
          + [SCALE_NAMES.get(json.loads(r["scores"] or "{}").get(k), "") for k in area_keys]
          + [r["text"], r["stars"], r["rec"], r["consent"]] for r in res]),
        ("Kunlik holat", ["Sana", "Ism", "Username", "Xarid raqami", "Mahsulot kuni", "Holat", "Izoh"],
         [[at(c["created_at"]), c["first_name"], un(c), pretty_phone(c["buy_phone"]), c["day_no"],
           " ".join(MOODS.get(c["mood"], ("", ""))), c["text"]] for c in chk]),
        ("Murojaatlar", ["№", "Sana", "Ism", "Username", "Telefon", "Sabab", "Matn", "Holati", "Kim bog'landi", "Qachon"],
         [[t["id"], at(t["created_at"]), t["first_name"], un(t), pretty_phone(t["buy_phone"] or t["tg_phone"]),
           t["source"], t["text"], t["status"], t["handled_by"], at(t["handled_at"])] for t in tks]),
        ("Media", ["Sana", "Ism", "Username", "Turi", "Qayerdan", "Matn", "Rozilik", "file_id"],
         [[at(m["created_at"]), m["first_name"], un(m), m["kind"], m["source"], m["text"], consent.get(m["user_id"], ""),
           m["file_id"]] for m in med]),
        ("O'yinlar", ["Sana", "Ism", "Boshlagan daraja", "Yetgan daraja", "Foiz", "Davomiyligi (s)", "Yakun", "Shubhali"],
         [[at(p["created_at"]), p["first_name"], p["start"], p["reached"], p["pct"], p["dur"], p["how"],
           "Ha" if p["suspicious"] else ""] for p in plays]),
        ("Qayta xarid", ["№", "Sana", "Ism", "Username", "Telefon", "Kod", "Chegirma %", "Kod muddati", "Holati",
                         "Kim bog'landi", "Qachon", "Kod ishlatildi"],
         [[o["id"], at(o["created_at"]), o["first_name"], un(o), pretty_phone(o["buy_phone"] or o["tg_phone"]), o["code"],
           o["pct"], dt2s(code_deadline(o["code_exp"])), o["status"], o["handled_by"], at(o["handled_at"]),
           "Ha" if o["code_used"] else ""] for o in ords]),
    ]
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
            w.writerow([f"== {name} =="]); w.writerow(head); w.writerows(rows); w.writerow([])
        return f"vitaway_{today().isoformat()}.csv", out.getvalue().encode("utf-8-sig")


def admin_excel(uid):
    send(uid, "⏳ Fayl tayyorlanmoqda...")
    name, content = build_excel()
    api_file("sendDocument", "document", name, content, chat_id=str(uid),
             caption="📥 Vitaway: mijozlar, natijalar, kunlik holat, murojaatlar, media, o'yinlar va qayta xarid")


def admin_otzivlar(uid, arg):
    n = int(arg) if arg and arg.isdigit() else 10
    rows = db.execute("SELECT m.*, u.first_name FROM media m LEFT JOIN users u ON u.id=m.user_id "
                      "WHERE m.kind!='text' ORDER BY m.id DESC LIMIT ?", (n,)).fetchall()
    if not rows:
        return send(uid, "Hozircha media otzivlar yo'q.")
    method = {"voice": ("sendVoice", "voice"), "video": ("sendVideo", "video"), "photo": ("sendPhoto", "photo"),
              "audio": ("sendAudio", "audio"), "document": ("sendDocument", "document")}
    for m in reversed(rows):
        c = db.execute("SELECT consent FROM results WHERE user_id=? ORDER BY id DESC LIMIT 1", (m["user_id"],)).fetchone()
        cap = f"👤 {esc(m['first_name'])} · {esc(m['source'] or '')}\n📣 Rozilik: {c['consent'] if c else '-'}\n{esc(m['text'] or '')}"
        if m["kind"] == "video_note":
            api("sendVideoNote", chat_id=uid, video_note=m["file_id"])
            send(uid, cap)
        elif m["kind"] in method:
            meth, field = method[m["kind"]]
            api(meth, chat_id=uid, caption=cap[:1000], parse_mode="HTML", **{field: m["file_id"]})


def admin_kod(uid, arg):
    code = (arg or "").strip().upper()
    if not code:
        return send(uid, "Kodni yozing: /kod VW-15-1234")
    u = db.execute("SELECT * FROM users WHERE code=?", (code,)).fetchone()
    if not u:
        return send(uid, "❌ Bunday kod topilmadi.")
    dl = code_deadline(u["code_exp"])
    st = {"used": "✅ Ishlatilgan", "expired": "⌛️ Muddati tugagan", "active": "🟢 Amalda"}[code_state(u)]
    send(uid, f"🎟 <b>{code}</b> — {u['best_pct']}%\n{st}\n\n👤 {who(u)}\n📞 {pretty_phone(u['buy_phone'])}\n"
              f"⏳ Muddati: {dt2s(dl)}", None if u["code_used"] else ikb([("✅ Ishlatildi deb belgilash", f"use:{code}")]))


def admin_buyers_doc(uid, msg):
    doc = msg["document"]
    f = api("getFile", file_id=doc["file_id"])
    if not f:
        return send(uid, "Faylni yuklab bo'lmadi.")
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{f['file_path']}", timeout=60) as r:
        content = r.read()
    if doc.get("file_name", "").lower().endswith((".xlsx", ".xlsm")):
        try:
            from io import BytesIO
            from openpyxl import load_workbook
            wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
            text = " ".join(str(c) for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for c in row if c is not None)
        except ImportError:
            return send(uid, "Excel o'qish uchun openpyxl kerak. CSV yoki TXT yuboring.")
    else:
        text = content.decode("utf-8", "ignore")
    phones = {norm_phone(m) for m in re.findall(r"\+?\d[\d\s\-()]{7,16}\d", text)} - {None}
    db.executemany("INSERT OR IGNORE INTO buyers(phone) VALUES(?)", [(p,) for p in phones])
    db.commit()
    send(uid, f"✅ {len(phones)} ta raqam qo'shildi. Ro'yxatda jami: {db.execute('SELECT COUNT(*) FROM buyers').fetchone()[0]} ta.")


def admin_backup(uid):
    """Bazaning nusxasini adminga yuboradi (zaxira yoki boshqa joyga ko'chirish uchun)."""
    db.commit()
    tmp = DB_PATH + ".zaxira"
    if os.path.exists(tmp):
        os.remove(tmp)
    bk = sqlite3.connect(tmp)
    db.backup(bk)
    bk.close()
    with open(tmp, "rb") as f:
        content = f.read()
    os.remove(tmp)
    api_file("sendDocument", "document", "vitaway.db", content, chat_id=str(uid),
             caption="💾 Bot bazasining zaxira nusxasi. Boshqa joyga ko'chirish uchun shu faylni yangi botga yuboring.")


def admin_restore(uid, msg):
    """Admin yuborgan vitaway.db faylini joriy baza o'rniga qo'yadi."""
    global db
    f = api("getFile", file_id=msg["document"]["file_id"])
    if not f:
        return send(uid, "Faylni yuklab bo'lmadi (20 MB dan katta bo'lmasin).")
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{f['file_path']}", timeout=60) as r:
        content = r.read()
    tmp = DB_PATH + ".yangi"
    with open(tmp, "wb") as fh:
        fh.write(content)
    try:
        t = sqlite3.connect(tmp)
        n = t.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        t.close()
    except Exception:
        os.remove(tmp)
        return send(uid, "❌ Bu fayl bot bazasi emas. vitaway.db faylini yuboring.")
    db.commit()
    src = sqlite3.connect(tmp)
    src.backup(db)
    src.close()
    os.remove(tmp)
    db_init()
    send(uid, f"✅ Baza tiklandi: {n} ta mijoz, guruh ulanishlari ham ko'chdi.")


def reset_user(uid):
    for t in ("results", "media", "plays", "checkins", "tickets", "relay", "orders"):
        db.execute(f"DELETE FROM {t} WHERE user_id=?", (uid,))
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit()


# ------------------------------------------------------------------ guruhlar
CONNECT = {"/ulash_otziv": ("otziv_chat", "Yaxshi fikrlar va otzivlar"),
           "/ulash_mutaxassis": ("mutaxassis_chat", "Mijozlar murojaatlari (muammosi va raqami bilan)"),
           "/ulash_qaytaxarid": ("qayta_chat", "«🛒 Qayta xarid» so'rovlari (chegirma kodi va raqami bilan)")}


def handle_group(msg):
    chat = msg["chat"]
    cid = chat["id"]
    uid = msg.get("from", {}).get("id")
    text = (msg.get("text") or "").strip()
    cmd = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
    if cmd == "/chatid":
        return send(cid, f"Bu guruh ID: <code>{cid}</code>")
    if cmd in CONNECT:
        if not is_admin(uid):
            return send(cid, "Bu buyruq faqat bot admini uchun.")
        key, what = CONNECT[cmd]
        kv_set(key, cid)
        for aid in ADMIN_IDS:
            send(aid, f"✅ «{esc(chat.get('title', ''))}» guruhi ulandi: {what.lower()}.")
        return send(cid, f"✅ Ulandi! {what} endi shu guruhga tushadi.")
    # Mutaxassis javobi: bot xabariga Reply
    rep = msg.get("reply_to_message")
    if rep and (cid in specialist_targets() or cid in qayta_targets()):
        row = db.execute("SELECT * FROM relay WHERE msg_id=?", (rep["message_id"],)).fetchone()
        if row:
            is_order = (row["ticket_id"] or 0) < 0
            send(row["user_id"], "🛒 <b>Vitaway menejeri:</b>" if is_order else "👩‍⚕️ <b>Mutaxassis javobi:</b>")
            r = api("copyMessage", chat_id=row["user_id"], from_chat_id=cid, message_id=msg["message_id"])
            if r:
                handler = msg.get("from", {}).get("first_name", "")
                if is_order:
                    db.execute("UPDATE orders SET status='javob berildi', handled_by=?, handled_at=? WHERE id=? AND status='yangi'",
                               (handler, iso(now()), -row["ticket_id"]))
                else:
                    db.execute("UPDATE tickets SET status='javob berildi', handled_by=?, handled_at=? WHERE id=? AND status='yangi'",
                               (handler, iso(now()), row["ticket_id"]))
                db.execute("INSERT OR REPLACE INTO relay(msg_id, user_id, ticket_id) VALUES(?,?,?)",
                           (msg["message_id"], row["user_id"], row["ticket_id"]))
                db.commit()
                api("setMessageReaction", chat_id=cid, message_id=msg["message_id"],
                    reaction=[{"type": "emoji", "emoji": "👍"}])
            else:
                send(cid, "❗️ Mijozga yetkazib bo'lmadi (botni bloklagan bo'lishi mumkin).")


# ------------------------------------------------------------------ xabarlar
def handle_message(msg):
    chat_type = msg.get("chat", {}).get("type")
    if chat_type in ("group", "supergroup"):
        return handle_group(msg)
    if chat_type != "private":
        return
    uid = msg["from"]["id"]
    text = (msg.get("text") or "").strip()

    if text.startswith("/"):
        cmd, _, arg = text.partition(" ")
        cmd = cmd.split("@")[0].lower()
        if cmd == "/start":
            return start_cmd(msg)
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
            if cmd == "/zaxira":
                return admin_backup(uid)
            if cmd == "/mijozlar":
                return send(uid, "Xaridorlar raqamlari bor Excel, CSV yoki TXT faylni yuboring, izohiga <b>mijozlar</b> deb yozing.")
            if cmd == "/test":
                reset_user(uid)
                return start_cmd(msg)
            if cmd == "/reset":
                reset_user(uid)
                return send(uid, "🗑 Ma'lumotlaringiz o'chirildi. /start", REMOVE_KB)
            if cmd == "/kunlik":
                u = get_user(uid)
                if u and u["result_done_at"]:
                    return send_checkin(u)
                return send(uid, "Avval natijani yuboring (/start).")
        u = get_user(uid)
        if not u:
            return start_cmd(msg)
        if cmd in ("/oyin", "/game"):
            return game_button(u)
        if cmd in ("/kodim", "/code"):
            return my_code(u)
        if cmd in ("/yordam", "/help"):
            return help_button(u)
        return home(u)

    if is_admin(uid) and "document" in msg and "mijoz" in (msg.get("caption") or "").lower():
        return admin_buyers_doc(uid, msg)
    if is_admin(uid) and "document" in msg and msg["document"].get("file_name", "").lower().endswith(".db"):
        return admin_restore(uid, msg)

    u = get_user(uid)
    if not u:
        return start_cmd(msg)
    if u["checkin_stop"]:
        upd(uid, checkin_stop=0, checkin_misses=0)  # mijoz qaytdi: kunlik so'rov davom etadi
        u = get_user(uid)

    if "web_app_data" in msg:
        try:
            data = json.loads(msg["web_app_data"]["data"])
        except Exception:
            return send(uid, "Ma'lumotni o'qib bo'lmadi, qaytadan urinib ko'ring.")
        if data.get("t") == "natija" and not u["result_done_at"]:
            return on_natija(u, data)
        if data.get("t") == "game":
            return on_game(u, data)
        return

    st = u["state"]
    if st == "phone":
        if "contact" in msg:
            if msg["contact"].get("user_id") not in (None, uid):
                return send(uid, "Iltimos, o'z raqamingizni yuboring yoki yozing.")
            return on_phone(u, contact=msg["contact"])
        if text:
            return on_phone(u, text=text)
        return ask_phone(uid)
    if st == "phone_confirm":
        return send(uid, "Iltimos, raqamni tasdiqlang 👆")

    # Menyu tugmalari
    if text == B_GAME:
        set_pending(uid)
        return game_button(u)
    if text == B_CODE:
        return my_code(u)
    if text == B_HELP:
        return help_button(u)
    if text == B_ABOUT:
        return about(u)
    if text == B_RESULT:
        return ask_result(u, again=True)

    if u["pending"] and on_pending(u, msg):
        return
    if st == "media":
        got = save_media(u, msg, "20 kunlik otziv")
        if got:
            if got[0] == "text":
                post_otziv(f"💬 <b>Otziv</b> · 20-kun · {who(u)}\n«{esc(got[2])[:1500]}»")
            else:
                post_otziv(f"🎙 <b>Otziv ({got[0]})</b> · 20-kun · {who(u)}", copy_from=(uid, msg["message_id"]))
            return send(uid, "✅ Qabul qilindi, rahmat! Yana yuborishingiz yoki davom etishingiz mumkin.",
                        ikb([("Davom etish ➡️", "media:skip")]))
    if st == "natija":
        return ask_result(u, again=True)
    # Ovozli xabar, video, rasm -> otziv sifatida otzivlar guruhiga
    if any(k in msg for k in ("voice", "video", "video_note", "photo")) and u["result_done_at"]:
        got = save_media(u, msg, "otziv")
        if got:
            post_otziv(f"🎙 <b>Otziv ({got[0]})</b> · {day_no(u)}-kun · {who(u)}" +
                       (f"\n«{esc(got[2])[:500]}»" if got[2] else ""), copy_from=(uid, msg["message_id"]))
            return send(uid, "💚 Rahmat! Otzivingiz Vitaway jamoasiga yetkazildi.", menu_kb(get_user(uid)))
    # Boshqa erkin matnli xabar mutaxassisga yo'naltiriladi
    if any(k in msg for k in ("text", "audio")) and u["result_done_at"]:
        set_pending(uid, "support", None)
        return on_pending(get_user(uid), msg)
    home(u)


def handle_callback(cq):
    uid = cq["from"]["id"]
    data = cq.get("data") or ""
    msg = cq.get("message") or {}
    chat_id = msg.get("chat", {}).get("id", uid)
    mid = msg.get("message_id")
    api("answerCallbackQuery", callback_query_id=cq["id"])
    clear = lambda: api("editMessageReplyMarkup", chat_id=chat_id, message_id=mid, reply_markup={"inline_keyboard": []})

    if data.startswith("tk:"):
        tid = int(data[3:])
        name = cq["from"].get("first_name", "")
        db.execute("UPDATE tickets SET status=?, handled_by=?, handled_at=? WHERE id=?", ("bog'lanildi", name, iso(now()), tid))
        db.commit()
        clear()
        return send(chat_id, f"✅ Murojaat #{tid}: {esc(name)} bog'landi.", reply_to_message_id=mid)
    if data.startswith("ob:"):
        oid = int(data[3:])
        name = cq["from"].get("first_name", "")
        db.execute("UPDATE orders SET status=?, handled_by=?, handled_at=? WHERE id=?", ("bog'lanildi", name, iso(now()), oid))
        db.commit()
        clear()
        return send(chat_id, f"✅ Qayta xarid #{oid}: {esc(name)} bog'landi.", reply_to_message_id=mid)
    if data.startswith("use:") and is_admin(uid):
        code = data[4:]
        db.execute("UPDATE users SET code_used=1, code_used_by=?, code_used_at=? WHERE code=?", (uid, iso(now()), code))
        db.commit()
        clear()
        return send(chat_id, f"✅ {code} ishlatildi deb belgilandi.")

    u = get_user(uid)
    if not u:
        return
    if data == "buy":
        clear()
        return request_buy(u)
    if data.startswith("ph:") and u["state"] == "phone_confirm":
        clear()
        return ask_phone(uid) if data == "ph:no" else phone_confirmed(uid)
    if data == "media:skip" and u["state"] == "media":
        clear()
        upd(uid, state="idle")
        return offer_game(get_user(uid)) or home(get_user(uid))
    if data.startswith("offer:"):
        clear()
        if data == "offer:later":
            upd(uid, offer_status="later", state="idle")
            return send(uid, "Mayli 😊 Ertaga yana eslatamiz. Xohlagan paytingizda menyudagi "
                             f"<b>«{B_GAME}»</b> tugmasini bosishingiz mumkin.", menu_kb(get_user(uid)))
        return start_game(get_user(uid))
    if data.startswith("mood:"):
        if u["checkin_answered"] == today().isoformat():
            return
        clear()
        return on_mood(u, int(data[5:]))
    if data.startswith("pend:"):
        clear()
        kind = u["pending"]
        if data == "pend:cancel":
            set_pending(uid)
            return send(uid, "Bekor qilindi.", menu_kb(u))
        if data == "pend:help":
            set_pending(uid, "help", None)
            return send(uid, "💬 Xavotiringizni yozing yoki ovozli xabar yuboring, mutaxassisga yetkazamiz.")
        set_pending(uid)
        if kind in ("good", "neutral", "bad"):
            return after_checkin(get_user(uid), kind)
        return home(get_user(uid))


def handle_channel(post):
    """Kanal ichida /ulash_otziv, /ulash_mutaxassis yoki /ulash_qaytaxarid yozilganda (kanalga faqat adminlar yoza oladi)."""
    cid = post["chat"]["id"]
    text = (post.get("text") or "").strip()
    cmd = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
    if cmd == "/chatid":
        return send(cid, f"Bu kanal ID: <code>{cid}</code>")
    if cmd in CONNECT:
        key, what = CONNECT[cmd]
        kv_set(key, cid)
        api("deleteMessage", chat_id=cid, message_id=post["message_id"])
        send(cid, f"✅ Ulandi! {what} endi shu yerga tushadi.")
        for aid in ADMIN_IDS:
            send(aid, f"✅ «{esc(post['chat'].get('title', ''))}» kanali ulandi: {what.lower()}.")


def handle_update(up):
    try:
        if "channel_post" in up:
            handle_channel(up["channel_post"])
        elif "message" in up:
            handle_message(up["message"])
        elif "callback_query" in up:
            handle_callback(up["callback_query"])
        elif "my_chat_member" in up:
            m = up["my_chat_member"]
            if m.get("chat", {}).get("type") == "private" and m.get("new_chat_member", {}).get("status") == "kicked":
                upd(m["from"]["id"], blocked=1)
    except Exception:
        log("Xato:", traceback.format_exc())


# ------------------------------------------------------------------ rejalashtirilgan ishlar
def scheduler_tick():
    n = now()
    t = n.date()
    if not (9 <= n.hour < 22):
        return
    # 1) natija yuborilmagan bo'lsa, 1 kundan keyin bir marta eslatish
    for u in db.execute("SELECT * FROM users WHERE state='natija' AND result_reminded=0 AND blocked=0 "
                        "AND result_done_at IS NULL").fetchall():
        if u["result_asked_at"] and from_iso(u["result_asked_at"]) + timedelta(days=1) <= n:
            upd(u["id"], result_reminded=1)
            send(u["id"], "👋 Farzandingizdagi natijani hali yubormadingiz. "
                          "1 daqiqa vaqt ajratsangiz, sizni sovg'a kutmoqda 🎁", webapp_kb(B_RESULT, natija_url(u)))

    # 2) kunlik holat
    if n.hour >= CHECKIN_HOUR:
        for u in db.execute("SELECT * FROM users WHERE blocked=0 AND checkin_stop=0 AND result_done_at IS NOT NULL "
                            "AND (checkin_last IS NULL OR checkin_last<?)", (t.isoformat(),)).fetchall():
            d = day_no(u)
            if d <= START_DAY or d > START_DAY + DAILY_DAYS:
                continue
            if from_iso(u["result_done_at"]).date() >= t:
                continue  # natijani bugun yuborgan bo'lsa, ertadan boshlanadi
            last, ans = u["checkin_last"], u["checkin_answered"]
            misses = (u["checkin_misses"] or 0) + (1 if last and (not ans or ans < last) else 0)
            if misses >= STOP_AFTER_MISSES:
                upd(u["id"], checkin_stop=1, checkin_misses=misses)
                continue
            upd(u["id"], checkin_misses=misses)
            send_checkin(get_user(u["id"]))
            time.sleep(SEND_GAP)

    # 3) chegirma tugashiga oz qolganda (bir marta), agar mijoz hali «Qayta xarid» ni bosmagan bo'lsa
    for u in db.execute("SELECT * FROM users WHERE blocked=0 AND code IS NOT NULL AND code_used=0 "
                        "AND (last_remind IS NULL OR last_remind!=code)").fetchall():
        dl = code_deadline(u["code_exp"])
        if not dl or not (now() < dl <= now() + timedelta(hours=REMIND_LEFT_HOURS)) or open_order(u):
            continue
        upd(u["id"], last_remind=u["code"])
        send(u["id"], f"⏰ <b>{u['best_pct']}% chegirmangiz tugashiga {left_str(dl)} qoldi!</b>\n\n"
                      f"Kod: <code>{u['code']}</code>\nChegirmadan foydalanib qolish uchun <b>«🛒 Qayta xarid»</b> ni bosing 👇",
             BUY_KB)
        time.sleep(SEND_GAP)


# ------------------------------------------------------------------ ishga tushirish
def first_setup():
    global BOT_TOKEN, ADMIN_IDS, WEBAPP_URL, BOT_TITLE
    print("=" * 60)
    print("  VITAWAY BOT: birinchi sozlash")
    print("=" * 60)
    while True:
        tok = input("\n1) BotFather bergan TOKENni qo'ying va Enter bosing:\n> ").strip().strip('"')
        if re.match(r"^\d{6,}:[A-Za-z0-9_-]{30,}$", tok):
            BOT_TOKEN = tok
            me = api("getMe")
            if me:
                print(f"   OK! Bot topildi: @{me.get('username')}")
                break
            print("   Bu token ishlamadi. BotFather'dagi tokenni qaytadan nusxalang.")
        else:
            print("   Token noto'g'ri ko'rinadi. U shunday bo'ladi: 7123456789:AAH... (uzun)")
    while True:
        found = re.findall(r"\d{5,}", input("\n2) @userinfobot bergan ID raqamingizni yozing va Enter bosing:\n> "))
        if found:
            ADMIN_IDS = {int(x) for x in found}
            break
        print("   Faqat raqam yozing, masalan: 8612019405")
    t = input(f"\n3) Bot nomi: {BOT_TITLE}. O'zgartirmasangiz, faqat Enter bosing:\n> ").strip()
    BOT_TITLE = t or BOT_TITLE
    w = input(f"\n4) O'yin manzili. Hech narsa yozmang, faqat Enter bosing:\n> ").strip().rstrip("/")
    WEBAPP_URL = w if w.startswith("https://") else DEFAULT_WEBAPP
    with open(os.path.join(HERE, ".env"), "w", encoding="utf-8") as f:
        f.write(f"BOT_TOKEN={BOT_TOKEN}\nADMIN_IDS={','.join(map(str, ADMIN_IDS))}\n"
                f"BOT_TITLE={BOT_TITLE}\nWEBAPP_URL={WEBAPP_URL}\nTZ_HOURS=5\n")
    print("\nSozlamalar saqlandi. Keyingi safar hech narsa so'ralmaydi.\n")


def main():
    global WEBAPP_URL
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if not BOT_TOKEN:
        if sys.stdin and sys.stdin.isatty():
            first_setup()
        else:
            sys.exit("BOT_TOKEN topilmadi. .env faylini to'ldiring.")
    if not WEBAPP_URL.startswith("https://"):
        if WEBAPP_URL:
            log("Diqqat: o'yin manzili noto'g'ri edi, standart manzil ishlatiladi:", DEFAULT_WEBAPP)
        WEBAPP_URL = DEFAULT_WEBAPP
    db_init()
    me = api("getMe")
    if not me:
        sys.exit("Telegram'ga ulanib bo'lmadi: internet yoki tokenni tekshiring (.env faylini o'chirib, qayta sozlang).")
    log("Bot ishga tushdi:", me.get("username"))
    print("\nBot ishlayapti. Bu oynani YOPMANG. To'xtatish uchun Ctrl+C.\n", flush=True)
    cur = api("getMyName") or {}
    if cur.get("name") != BOT_TITLE:
        api("setMyName", name=BOT_TITLE)
    api("setMyShortDescription", short_description="Farzandingizning Vitaway bilan natijasi va sovg'ali o'yin 🎁")
    api("setMyDescription", description=(f"{BOT_TITLE} 💚\n\nFarzandingizning Vitaway bilan natijasini "
                                         "birga kuzatamiz, har kuni holatini so'raymiz va savollaringizga mutaxassis "
                                         "javob beradi. Qiziqarli o'yinda 20% gacha chegirma yutib oling!"))
    api("setMyCommands", commands=[{"command": "start", "description": "Bosh menyu"},
                                   {"command": "oyin", "description": "O'yin"},
                                   {"command": "kodim", "description": "Chegirma kodim"},
                                   {"command": "yordam", "description": "Mutaxassisga yozish"}])
    offset = int(kv_get("offset", "0"))
    last_tick = 0
    while True:
        try:
            ups = api("getUpdates", offset=offset, timeout=25,
                      allowed_updates=["message", "channel_post", "callback_query", "my_chat_member"]) or []
            for up in ups:
                offset = up["update_id"] + 1
                handle_update(up)
            if ups:
                kv_set("offset", offset)
        except KeyboardInterrupt:
            raise
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
    try:
        main()
    except KeyboardInterrupt:
        print("\nBot to'xtatildi.")
