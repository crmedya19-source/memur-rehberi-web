"""haberler.json'a yeni haber eklenince Firebase Cloud Messaging ile bildirim gönderir.
Anahtar: GitHub gizli değişkeni FCM_SERVICE_ACCOUNT (Firebase hizmet hesabı JSON'u). Yoksa sadece ne gönderileceğini yazar."""
import json, os, subprocess, datetime, sys, hashlib
from zoneinfo import ZoneInfo

KAYIT = ".github/bildirim_kayit.json"
OZET = ("📋", "☀️")

def tr_today():
    return datetime.datetime.now(ZoneInfo("Europe/Istanbul")).date()

def key(x):
    return hashlib.sha1((x.get("t", "") + "|" + x.get("s", "")).encode("utf-8")).hexdigest()[:16]

def load_kayit():
    try:
        return json.load(open(KAYIT, encoding="utf-8"))
    except Exception:
        return {"gonderilen": []}

def save_kayit(k, items):
    now = datetime.datetime.now(ZoneInfo("Europe/Istanbul")).isoformat(timespec="minutes")
    for x in items:
        k["gonderilen"].append({"t": x.get("t", ""), "k": key(x), "d": x.get("d", ""), "at": now})
    k["gonderilen"] = k["gonderilen"][-150:]
    json.dump(k, open(KAYIT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def load_prev():
    try:
        dirty = subprocess.call(["git", "diff", "--quiet", "HEAD", "--", "haberler.json"]) != 0
        ref = "HEAD" if dirty else "HEAD~1"
        return json.loads(subprocess.check_output(["git", "show", ref + ":haberler.json"], stderr=subprocess.DEVNULL))
    except Exception:
        return {"items": []}

def short(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"

def build_messages(cur, prev, today):
    old_keys = {(x.get("d"), x.get("t")) for x in prev.get("items", [])}
    old_titles = {x.get("t") for x in prev.get("items", [])}
    cutoff = (today - datetime.timedelta(days=2)).isoformat()
    old_k = {key(x) for x in prev.get("items", [])}
    sent = {g["k"] for g in load_kayit().get("gonderilen", [])}
    def is_new(x):
        if x.get("d", "") < cutoff or key(x) in sent:
            return False
        if x.get("t", "").startswith(OZET):
            # Günün özeti: başlık aynı kalsa da metni değiştiyse yeni sayılır
            return key(x) not in old_k
        return (x.get("d"), x.get("t")) not in old_keys and x.get("t") not in old_titles
    new = [x for x in cur.get("items", []) if is_new(x)]
    msgs = []
    def one(items, target):
        if not items:
            return
        if len(items) == 1:
            t0 = items[0]["t"]; t, b = (t0 if not t0[:1].isalnum() else "📰 " + t0), short(items[0].get("s", ""), 160); t = short(t, 75)
        else:
            t = "📰 %d yeni memur haberi" % len(items)
            b = short(" • ".join(x["t"] for x in items[:3]), 160)
        msgs.append((target, t, b))
    general = [x for x in new if not x.get("p")]
    one(general, {"topic": "haberler"})
    spec = [x for x in new if x.get("p")]
    if spec:
        letters = sorted({c for x in spec for c in x["p"]})
        for i in range(0, len(letters), 5):
            grp = letters[i:i + 5]
            items = [x for x in spec if any(c in x["p"] for c in grp)]
            cond = " || ".join("'meslek_%s' in topics" % c for c in grp)
            one(items, {"condition": cond})
    return new, msgs

def send(msgs):
    raw = os.environ.get("FCM_SERVICE_ACCOUNT", "").strip()
    if not raw:
        print("FCM_SERVICE_ACCOUNT yok: bildirim gönderilmedi (deneme modu).")
        return 0
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    info = json.loads(raw)
    cred = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/firebase.messaging"])
    ses = AuthorizedSession(cred)
    url = "https://fcm.googleapis.com/v1/projects/%s/messages:send" % info["project_id"]
    bad = 0
    for target, t, b in msgs:
        m = dict(target)
        m.update({"notification": {"title": t, "body": b},
                  "android": {"priority": "high", "notification": {"channel_id": "duyuru", "icon": "ic_stat_icon", "color": "#1d4f91"}},
                  "data": {"sayfa": "gundem"}})
        r = ses.post(url, json={"message": m}, timeout=30)
        print(r.status_code, r.text[:300])
        if r.status_code != 200:
            bad += 1
    return bad

if __name__ == "__main__":
    title, body, target = os.environ.get("BASLIK", "").strip(), os.environ.get("METIN", "").strip(), os.environ.get("HEDEF", "").strip() or "haberler"
    mod = os.environ.get("MOD", "").strip()
    today = tr_today()
    logged = []
    if title:
        msgs = [({"topic": target}, short(title, 80), short(body, 200))]
        logged = [{"t": title, "s": body, "d": today.isoformat()}]
    elif mod == "kontrol":
        # Saat 09:20 ve 20:20 güvencesi: günün özeti bildirim olarak gitmediyse şimdi gönder
        cur = json.load(open("haberler.json", encoding="utf-8"))
        hour = datetime.datetime.now(ZoneInfo("Europe/Istanbul")).hour
        emo = "☀️" if hour < 14 else "📋"
        sent_today = [g for g in load_kayit().get("gonderilen", []) if g.get("t", "").startswith(emo) and g.get("d") == today.isoformat()]
        oz = [x for x in cur.get("items", []) if x.get("d") == today.isoformat() and x.get("t", "").startswith(emo)]
        msgs = []
        if sent_today:
            print("Bugünün", emo, "bildirimi zaten gitmiş:", sent_today[-1]["t"])
        elif oz:
            x = oz[0]
            msgs = [({"topic": "haberler"}, short(x["t"], 75), short(x.get("s", ""), 160))]
            logged = [x]
            print("Özet vardı ama bildirimi gitmemişti; şimdi gönderiliyor.")
        else:
            yday = (today - datetime.timedelta(days=1)).isoformat()
            top = [x for x in cur.get("items", []) if x.get("d", "") >= yday and not x.get("t", "").startswith(OZET)][:3]
            if top:
                ay = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"][today.month - 1]
                t = "%s %d %s: Günün memur başlıkları" % (emo, today.day, ay)
                b = short(" • ".join(x["t"] for x in top), 160)
                msgs = [({"topic": "haberler"}, t, b)]
                logged = [{"t": t, "s": b, "d": today.isoformat()}]
                print("Günün özeti hazırlanamamış; yedek bildirim gönderiliyor.")
            else:
                print("Gönderilecek haber yok.")
    else:
        cur = json.load(open("haberler.json", encoding="utf-8"))
        new, msgs = build_messages(cur, load_prev(), today)
        logged = new
        print("Yeni haber:", len(new))
    for tg, t, b in msgs:
        print("->", tg, "|", t, "|", b)
    bad = send(msgs) if msgs else 0
    if msgs and not bad and os.environ.get("FCM_SERVICE_ACCOUNT", "").strip():
        save_kayit(load_kayit(), logged)
    sys.exit(1 if bad else 0)
