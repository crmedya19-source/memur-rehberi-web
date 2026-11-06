"""haberler.json'a yeni haber eklenince Firebase Cloud Messaging ile bildirim gönderir.
Anahtar: GitHub gizli değişkeni FCM_SERVICE_ACCOUNT (Firebase hizmet hesabı JSON'u). Yoksa sadece ne gönderileceğini yazar."""
import json, os, subprocess, datetime, sys

def load_prev():
    try:
        return json.loads(subprocess.check_output(["git", "show", "HEAD~1:haberler.json"], stderr=subprocess.DEVNULL))
    except Exception:
        return {"items": []}

def short(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"

def build_messages(cur, prev, today):
    old_keys = {(x.get("d"), x.get("t")) for x in prev.get("items", [])}
    old_titles = {x.get("t") for x in prev.get("items", [])}
    cutoff = (today - datetime.timedelta(days=2)).isoformat()
    new = [x for x in cur.get("items", []) if (x.get("d"), x.get("t")) not in old_keys and x.get("t") not in old_titles and x.get("d", "") >= cutoff]
    msgs = []
    def one(items, target):
        if not items:
            return
        if len(items) == 1:
            t, b = "📰 " + short(items[0]["t"], 70), short(items[0].get("s", ""), 160)
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
    return 1 if bad else 0

if __name__ == "__main__":
    title, body, target = os.environ.get("BASLIK", "").strip(), os.environ.get("METIN", "").strip(), os.environ.get("HEDEF", "").strip() or "haberler"
    if title:
        msgs = [({"topic": target}, short(title, 80), short(body, 200))]
    else:
        cur = json.load(open("haberler.json", encoding="utf-8"))
        new, msgs = build_messages(cur, load_prev(), datetime.date.today())
        print("Yeni haber:", len(new))
    for tg, t, b in msgs:
        print("->", tg, "|", t, "|", b)
    sys.exit(send(msgs) if msgs else 0)
