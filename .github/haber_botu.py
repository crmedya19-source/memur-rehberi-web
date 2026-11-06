"""Haber botu: Google Haberler ve Memurlar.net akışlarından memurları ilgilendiren başlıkları
haberler.json'a ekler; büyük gelişmelerde (zam, maaş, izin, tatil...) bildirim gönderir.
Özet yazmaz (s boş kalır); özetleri akşam Claude'un günlük gündem görevi ekler."""
import json, os, re, sys, time, difflib, datetime, urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
import requests

TZ = datetime.timezone(datetime.timedelta(hours=3))
NOW = datetime.datetime.now(TZ)
UA = {"User-Agent": "MemurRehberiHaberBotu/1.0 (+https://github.com/crmedya19-source/memur-rehberi-web)"}

def gnews(q):
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q + " when:2d", "hl": "tr", "gl": "TR", "ceid": "TR:tr"})

FEEDS = [gnews(q) for q in ["memur", "memur maaş zam", "kamu personeli", "memurlara idari izin", "öğretmen MEB duyuru", "ek gösterge", "toplu sözleşme memur", "Resmi Gazete memur"]]
FEEDS += ["https://www.memurlar.net/rss/", "https://www.memurlar.net/rss/haber/"]

KEY = ["memur", "kamu personel", "kamu çalışan", "kamu görevli", "ek gösterge", "toplu sözleşme", "idari izin", "enflasyon farkı",
       "maaş katsayı", "memur emekli", "öğretmen", "meb ", "sağlık personel", "polis", "infaz koruma", "zabıta", "din görevli", "imam",
       "görevde yükselme", "657", "kadro", "ikramiye", "ek ödeme", "nöbet ücret", "fazla mesai", "yönetmelik"]
EXCL = ["alımı", "alacak", "alım ilan", "iş ilanı", "personel alım", "başvuru şart", "kpss tercih", "sözleşmeli personel alı", "burç", "fal",
        "gözaltı", "tutuklan", "cinayet", "kaza", "öldü", "hayatını kaybet", "operasyon", "rüşvet", "darp", "intihar", "maç", "bahis"]
BIG = ["zam", "maaş", "ikramiye", "ek gösterge", "idari izin", "tatil", "enflasyon farkı", "katsayı", "toplu sözleşme", "bayram", "ek ödeme", "seyyanen"]
CAP_NOTIFY = 5

def norm(t):
    t = t.lower().replace("ı", "i").replace("İ", "i")
    return re.sub(r"[^a-z0-9çğöşü ]", " ", t)

def similar(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio() > 0.72

def guess_c(t):
    l = t.lower()
    if any(k in l for k in ["zam", "maaş", "ikramiye", "ek gösterge", "enflasyon", "katsayı", "toplu sözleşme", "ek ödeme", "ücret"]): return "maas"
    if any(k in l for k in ["öğretmen", "meb", "okul", "ara tatil", "eğitim"]): return "egitim"
    if any(k in l for k in ["yönetmelik", "kanun", "resmi gazete", "resmî gazete", "genelge", "düzenleme", "anayasa mahkemesi", "danıştay"]): return "mevzuat"
    return "gundem"

def guess_p(t):
    l = t.lower(); p = ""
    if "öğretmen" in l and "memur" not in l: p += "o"
    if any(k in l for k in ["hemşire", "hekim", "sağlık personel", "sağlıkçı"]) and "memur" not in l: p += "s"
    if any(k in l for k in ["polis", "emniyet"]) and "memur" not in l: p += "p"
    if "infaz koruma" in l: p += "i"
    if any(k in l for k in ["imam", "müezzin", "din görevli"]): p += "d"
    return p

def fetch(url):
    try:
        r = requests.get(url, headers=UA, timeout=25)
        if r.status_code != 200 or b"<rss" not in r.content[:500].lower() and b"<feed" not in r.content[:500].lower():
            print("akış yok:", url[:80], r.status_code); return []
        root = ET.fromstring(r.content)
    except Exception as e:
        print("hata:", url[:80], e); return []
    out = []
    for it in root.iter("item"):
        t = (it.findtext("title") or "").strip(); u = (it.findtext("link") or "").strip()
        pd = it.findtext("pubDate"); src = (it.findtext("source") or "").strip()
        if not t or not u.startswith("https://"): continue
        try: dt = parsedate_to_datetime(pd).astimezone(TZ)
        except Exception: dt = NOW
        if "news.google.com" in url and " - " in t:
            t, s2 = t.rsplit(" - ", 1); src = src or s2
        if not src: src = "Memurlar.net" if "memurlar.net" in url else urllib.parse.urlparse(u).netloc
        out.append({"t": " ".join(t.split()), "u": u, "src": src.strip()[:40], "dt": dt})
    return out

def relevant(x):
    l = " " + x["t"].lower() + " "
    if any(k in l for k in EXCL): return False
    if not any(k in l for k in KEY): return False
    return (NOW - x["dt"]).total_seconds() < 36 * 3600 and x["dt"] <= NOW + datetime.timedelta(hours=1)

def main():
    j = json.load(open("haberler.json", encoding="utf-8"))
    items = j["items"]
    st_path = ".github/bot_durum.json"
    try: st = json.load(open(st_path, encoding="utf-8"))
    except Exception: st = {}
    seen = set(st.get("seen", []))
    today = NOW.date().isoformat()
    if st.get("gun") != today: st["gun"], st["bildirim"] = today, 0
    cand = []
    for f in FEEDS:
        cand += [x for x in fetch(f) if relevant(x)]
        time.sleep(1)
    cand.sort(key=lambda x: x["dt"], reverse=True)
    if os.environ.get("DENE") == "1":
        print("DENEME MODU - aday sayısı", len(cand))
        for x in cand[:40]:
            dup = any(similar(x["t"], y["t"]) for y in items)
            print(("  (var) " if dup else "  YENI  ") + x["dt"].strftime("%d.%m %H:%M") + " | " + x["src"] + " | " + x["t"] + (" | BILDIRIM" if any(k in x["t"].lower() for k in BIG) else ""))
        return
    added = []
    for x in cand:
        if x["u"] in seen: continue
        seen.add(x["u"])
        if any(similar(x["t"], y["t"]) for y in items + added): continue
        added.append({"d": x["dt"].date().isoformat(), "t": x["t"][:110], "s": "", "src": x["src"], "u": x["u"], "c": guess_c(x["t"]), "p": guess_p(x["t"]), "a": 1})
        if len(added) >= 3: break
    st["seen"] = list(seen)[-600:]
    json.dump(st, open(st_path, "w", encoding="utf-8"), ensure_ascii=False)
    if not added:
        print("Yeni haber yok."); return
    items = added + items
    items.sort(key=lambda x: x["d"], reverse=True)
    while len(items) > 20:
        auto = [i for i, x in enumerate(items) if x.get("a")]
        items.pop(auto[-1] if auto else len(items) - 1)
    j["items"] = items; j["updated"] = today
    json.dump(j, open("haberler.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for x in added: print("+", x["d"], x["src"], "|", x["t"])
    # büyük gelişmeler için bildirim
    sys.path.insert(0, ".github"); import bildirim
    msgs = []
    for x in added:
        if st["bildirim"] >= CAP_NOTIFY: break
        if any(k in x["t"].lower() for k in BIG):
            tgt = {"topic": "haberler"} if not x["p"] else {"condition": " || ".join("'meslek_%s' in topics" % c for c in x["p"][:5])}
            msgs.append((tgt, "📰 " + bildirim.short(x["t"], 70), x["src"] + " · dokun ve oku"))
            st["bildirim"] += 1
    json.dump(st, open(st_path, "w", encoding="utf-8"), ensure_ascii=False)
    for m in msgs: print("bildirim ->", m)
    if msgs: bildirim.send(msgs)

if __name__ == "__main__":
    main()
