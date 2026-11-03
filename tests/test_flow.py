# Botni Telegram'siz sinash: api() soxta, vaqt boshqariladi.
import json, os, sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["BOT_TOKEN"] = "TEST"; os.environ["ADMIN_IDS"] = "999"; os.environ["WEBAPP_URL"] = "https://ex.github.io/vw"
import bot

SENT = []
def fake_api(method, **p):
    SENT.append((method, p))
    if method == "getFile": return None
    return {"message_id": len(SENT)}
bot.api = fake_api
def fake_file(method, field, name, content, **k):
    if method == "sendAnimation":
        SENT.append(("sendAnimation", {"chat_id": int(k["chat_id"]), "text": k.get("caption", ""), "reply_markup": k.get("reply_markup"), "file": name}))
        return {"animation": {"file_id": "FID_" + name}}
    SENT.append((method, {"name": name, "size": len(content)}))
bot.api_file = fake_file

CLOCK = [datetime(2026, 11, 2, 11, 0, tzinfo=bot.TZ)]
bot.now = lambda: CLOCK[0]
bot.today = lambda: CLOCK[0].date()
bot.db_init(":memory:")

U = 1001
uid_counter = [0]
def msg(text=None, uid=U, **extra):
    uid_counter[0] += 1
    m = {"message_id": uid_counter[0], "from": {"id": uid, "first_name": "Dilnoza", "username": "dilnoza"},
         "chat": {"id": uid, "type": "private"}}
    if text is not None: m["text"] = text
    m.update(extra)
    bot.handle_update({"message": m})
def cb(data, uid=U):
    bot.handle_update({"callback_query": {"id": "x", "from": {"id": uid}, "data": data, "message": {"message_id": 1}}})
def texts(n=None):
    out = [p.get("text", "") or p.get("caption", "") for m, p in SENT if m in ("sendMessage", "sendAnimation") and p.get("chat_id") == U]
    return out if n is None else out[-n:]
def last_kb():
    for m, p in reversed(SENT):
        if m in ("sendMessage", "sendAnimation") and p.get("chat_id") == U and p.get("reply_markup"):
            return p["reply_markup"]
def st(): return bot.get_user(U)
def webapp(data): msg(None, web_app_data={"data": json.dumps(data)})

# 1) /start va ro'yxat
msg("/start")
assert st()["state"] == "reg_product", st()["state"]
cb("p:antihelmo"); assert st()["product"] == "antihelmo"
cb("d:manual"); msg("99.99.2026"); assert "kk.oo.yyyy" in texts(1)[0]
msg("25.10.2026"); assert st()["start_date"] == "2026-10-25" and st()["state"] == "active"
print("1 ro'yxat OK:", texts(1)[0][:60].replace("\n", " "))

# 2) 20-kun hali kelmagan
bot.scheduler_tick(); assert st()["state"] == "active"
# 14.11 soat 9:00 -> hali yubormaydi (soat 10 dan)
CLOCK[0] = datetime(2026, 11, 14, 9, 0, tzinfo=bot.TZ); bot.scheduler_tick(); assert st()["state"] == "active"
CLOCK[0] = datetime(2026, 11, 14, 10, 5, tzinfo=bot.TZ); bot.scheduler_tick()
assert st()["state"] == "natija"
kb = last_kb(); url = kb["keyboard"][0][0]["web_app"]["url"]
assert url.endswith("natija.html?p=antihelmo"), url
print("2 20-kun so'rovi OK:", url)

# 3) natija keladi
webapp({"t": "natija", "p": "antihelmo", "who": "Onasi", "child": "Madina", "age": "4–6",
        "sc": {"ishtaha": 3, "qorin": 2, "tish": 1, "uyqu": 3}, "text": "Ishtahasi ochildi", "stars": 5,
        "rec": "Ha, albatta", "ok": "Ha, ismim bilan"})
assert st()["state"] == "media"
assert any("3 ta" in t for t in texts(3)), texts(3)
# admin xabari
assert any(p.get("chat_id") == 999 and "Yangi natija" in p.get("text", "") for m, p in SENT)
# ovozli xabar
msg(None, voice={"file_id": "VOICE1"}); assert bot.db.execute("SELECT COUNT(*) FROM media").fetchone()[0] == 1
cb("media:skip"); assert st()["state"] == "offer"
print("3 natija + media OK")

# 4) Keyingi safar -> 2 kundan keyin eslatma
cb("offer:later"); assert st()["offer_status"] == "later"
CLOCK[0] += timedelta(days=1); bot.scheduler_tick(); assert st()["offer_reminded"] == 0
CLOCK[0] += timedelta(days=1, minutes=1); bot.scheduler_tick(); assert st()["offer_reminded"] == 1
assert "sovg'amiz" in texts(1)[0]
# yana eslatmaydi
n = len(texts()); CLOCK[0] += timedelta(days=3); bot.scheduler_tick()
print("4 qayta eslatma OK")

# 5) Ha -> raqam
CLOCK[0] = datetime(2026, 11, 17, 12, 0, tzinfo=bot.TZ)
cb("offer:yes"); assert st()["state"] == "phone"
msg("12345"); assert "noto'g'ri" in texts(1)[0]
msg("90 123 45 67"); assert st()["state"] == "phone_confirm" and st()["buy_phone"] == "+998901234567"
assert any("+998 90 123 45 67" in t for t in texts(2))
cb("ph:no"); assert st()["state"] == "phone"
msg(None, contact={"phone_number": "998901112233", "user_id": U}); assert st()["buy_phone"] == "+998901112233"
cb("ph:yes"); u = st()
assert u["state"] == "ready" and u["phone_ok"] == 1 and u["attempts_left"] == 3
url = last_kb()["keyboard"][0][0]["web_app"]["url"]; assert "start=1&best=0&att=3" in url, url
print("5 raqam + tayyorlaning OK:", url)

# 6) O'yin natijalari
lv = lambda a, b: [{"l": i, "ok": 1, "s": 20} for i in range(a, b + 1)]
webapp({"t": "game", "start": 1, "reached": 2, "pct": 7, "how": "stop", "dur": 60, "lv": lv(1, 2)})
u = st(); assert u["best_level"] == 2 and u["best_pct"] == 7 and u["code"].startswith("VW-7-") and u["attempts_left"] == 2
assert u["code_exp"] == "2026-11-27", u["code_exp"]
assert any("7% chegirma" in t for t in texts(3))
url = last_kb()["keyboard"][0][0]["web_app"]["url"]; assert "start=3&best=7&att=2" in url, url
# shubhali: juda tez
webapp({"t": "game", "start": 3, "reached": 5, "pct": 20, "how": "all", "dur": 10, "lv": [{"l": 3, "ok": 1, "s": 2}, {"l": 4, "ok": 1, "s": 2}, {"l": 5, "ok": 1, "s": 2}]})
assert st()["best_pct"] == 7 and st()["attempts_left"] == 1
assert any(p.get("chat_id") == 999 and "Shubhali" in p.get("text", "") for m, p in SENT)
# yutqazdi
webapp({"t": "game", "start": 3, "reached": 0, "pct": 0, "how": "fail", "dur": 30, "lv": [{"l": 3, "ok": 0, "s": 25}]})
assert st()["attempts_left"] == 0 and "Ertaga" in texts(1)[0], texts(2)
# urinish yo'q -> qabul qilinmaydi
webapp({"t": "game", "start": 3, "reached": 3, "pct": 11, "how": "stop", "dur": 30, "lv": lv(3, 3)})
assert st()["best_pct"] == 7
print("6 o'yin natijalari OK")

# 7) Ertasi kun: urinish qo'shiladi, kechki eslatma
CLOCK[0] = datetime(2026, 11, 18, 20, 35, tzinfo=bot.TZ); bot.scheduler_tick()
assert st()["attempts_left"] == 3, st()["attempts_left"]
assert "urinishlaringiz tayyor" in texts(1)[0], texts(1)
n = len(texts()); bot.scheduler_tick(); assert len(texts()) == n  # kuniga bir marta
webapp({"t": "game", "start": 3, "reached": 5, "pct": 20, "how": "all", "dur": 120, "lv": lv(3, 5)})
u = st(); assert u["best_pct"] == 20 and u["state"] == "done" and u["code"].startswith("VW-20-")
print("7 ertasi kun + 20% OK:", u["code"])

# 8) Kod tekshirish, ishlatildi
code = u["code"]
msg("/kod " + code.lower(), uid=999)
admin_txt = [p.get("text", "") for m, p in SENT if m == "sendMessage" and p.get("chat_id") == 999][-1]
assert "Amalda" in admin_txt, admin_txt
cb("use:" + code, uid=999); assert st()["code_used"] == 1
msg("/kod " + code, uid=999)
admin_txt = [p.get("text", "") for m, p in SENT if m == "sendMessage" and p.get("chat_id") == 999][-1]
assert "Ishlatilgan" in admin_txt
print("8 kod OK")

# 9) Ishtirok uchun 3% (hech daraja o'tmasa)
U2 = 2002
def m2(text=None, **e): msg(text, uid=U2, **e)
m2("/start antihelmo"); assert bot.get_user(U2)["state"] == "reg_date"
cb("d:0", uid=U2)
bot.upd(U2, start_date=(bot.today() - timedelta(days=20)).isoformat())
CLOCK[0] = datetime(2026, 11, 18, 11, 0, tzinfo=bot.TZ); bot.scheduler_tick()
assert bot.get_user(U2)["state"] == "natija"
m2(None, web_app_data={"data": json.dumps({"t": "natija", "sc": {}, "stars": 4})})
cb("media:skip", uid=U2); cb("offer:yes", uid=U2); m2("+998 97 000 11 22"); cb("ph:yes", uid=U2)
for i in range(3):
    m2(None, web_app_data={"data": json.dumps({"t": "game", "start": 1, "reached": 0, "how": "fail", "dur": 20, "lv": [{"l": 1, "ok": 0, "s": 20}]})})
u2 = bot.get_user(U2); assert u2["best_pct"] == 3 and u2["code"].startswith("VW-3-"), dict(u2)
print("9 ishtirok 3% OK")

# 10) Xaridorlar ro'yxati va Excel
bot.db.execute("INSERT INTO buyers VALUES('+998901112233')"); bot.db.commit()
msg("/stat", uid=999)
stat = [p.get("text", "") for m, p in SENT if m == "sendMessage" and p.get("chat_id") == 999][-1]
assert "Natija yuborgan: <b>2</b>" in stat, stat
name, content = bot.build_excel()
open(os.path.join(os.path.dirname(__file__), name), "wb").write(content)
print("10 statistika + Excel OK:", name, len(content), "bayt")

# 11) Muddat tugashidan 3 kun oldin eslatma (U2 kodi)
exp = bot.parse_date(bot.get_user(U2)["code_exp"])
CLOCK[0] = datetime.combine(exp - timedelta(days=3), datetime.min.time()).replace(hour=20, minute=40, tzinfo=bot.TZ)
bot.scheduler_tick()
t2 = [p.get("text", "") or p.get("caption", "") for m, p in SENT if m in ("sendMessage", "sendAnimation") and p.get("chat_id") == U2][-1]
assert "3 kundan keyin tugaydi" in t2, t2
print("11 kod muddati eslatmasi OK")
anims = [(p.get("file") or p.get("animation")) for m, p in SENT if m == "sendAnimation"]
print("animatsiyalar:", anims[:6], "...", len(anims), "ta")
assert "welcome.mp4" in anims and "day20.mp4" in anims and "offer.mp4" in anims and "win.mp4" in anims
assert "FID_welcome.mp4" in anims  # ikkinchi marta file_id bilan
print("\nHAMMASI O'TDI ✅")
