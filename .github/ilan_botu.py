"""ilan.gov.tr (Basın İlan Kurumu) kamu personel alım ilanlarını okuyup ilanlar.json'a yazar.
Yalnızca başlık, kurum, il, tarih ve resmî ilan bağlantısı tutulur; ilan metni kopyalanmaz.
DENE=1 ise dosyaya yazmaz, sadece gösterir."""
import json, os, re, ssl, time, datetime, html
import requests, certifi
from zoneinfo import ZoneInfo
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import ExtensionOID, AuthorityInformationAccessOID

HOST = "www.ilan.gov.tr"
API = "https://www.ilan.gov.tr/api/api/services/app/"
OUT = "ilanlar.json"
H = {"accept": "text/plain", "content-type": "application/json-patch+json", "origin": "https://www.ilan.gov.tr",
     "referer": "https://www.ilan.gov.tr/ilan/tum-ilanlar", "x-request-origin": "IGT-UI", "x-requested-with": "XMLHttpRequest",
     "user-agent": "MemurRehberi-IlanBotu/1.0 (+https://crmedya19-source.github.io/memur-rehberi-web/)"}
TODAY = datetime.datetime.now(ZoneInfo("Europe/Istanbul")).date()
AY = {"ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6, "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12}

def ca_bundle():
    # Sunucu ara sertifikayı göndermiyor; AIA adresinden indirip güven zincirine ekliyoruz (doğrulama açık kalır)
    pem = ssl.get_server_certificate((HOST, 443))
    cur = x509.load_pem_x509_certificate(pem.encode()); extra = b""
    for _ in range(3):
        try:
            aia = cur.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
        except Exception:
            break
        urls = [d.access_location.value for d in aia if d.access_method == AuthorityInformationAccessOID.CA_ISSUERS]
        if not urls:
            break
        raw = requests.get(urls[0], timeout=30).content
        try:
            c = x509.load_der_x509_certificate(raw)
        except Exception:
            c = x509.load_pem_x509_certificate(raw)
        extra += c.public_bytes(Encoding.PEM)
        if c.issuer == c.subject:
            break
        cur = c
    p = "/tmp/ilan_ca.pem"
    open(p, "wb").write(open(certifi.where(), "rb").read() + b"\n" + extra)
    return p

def tr_lower(s):
    return s.replace("I", "ı").replace("İ", "i").lower()

def meslek(t, k):
    s = tr_lower(t + " " + k)
    p = ""
    rules = [("z", r"zabıta"), ("f", r"itfaiye"), ("s", r"sağlık|hemşire|ebe\b|tabip|hekim|hastane|eczac|fizyoterap|sağlık bakanlığı|ilk defa ve yeniden atama kura"),
             ("p", r"polis|emniyet genel|bekçi"), ("j", r"jandarma|sahil güvenlik"), ("o", r"öğretmen|milli eğitim|millî eğitim"),
             ("i", r"infaz|ceza ve tevkif"), ("d", r"diyanet|imam|müezzin|kuran kursu|kur'an"), ("k", r"adalet bakanlığı|adliye|zabıt kâtib|zabıt katib|mübaşir|icra müdürlüğü|yargıtay|danıştay|hsk|hâkimler ve savcılar"),
             ("g", r"belediye|il özel idare|valilik|kaymakamlık|memur alım")]
    for c, rx in rules:
        if re.search(rx, s):
            p += c
    return p

def parse_date(s):
    s = s.strip()
    m = re.match(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.match(r"(\d{1,2})\s+([a-zçğıöşü]+)\s+(\d{4})", tr_lower(s))
        if not m or m.group(2) not in AY:
            return None
        d, mo, y = int(m.group(1)), AY[m.group(2)], int(m.group(3))
    try:
        return datetime.date(y, mo, d)
    except ValueError:
        return None

DT = r"(?<!\d)(\d{1,2}[./]\d{1,2}[./]\d{4}|\d{1,2}\s+(?:Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\s+\d{4})"

def son_basvuru(content, yayin):
    txt = html.unescape(re.sub(r"<[^>]+>", " ", content or ""))
    txt = re.sub(r"\s+", " ", txt)
    pats = [
        r"[Ss]on [Bb]aşvuru [Tt]arihi\s*[:：]?\s*" + DT,
        r"[Bb]aşvuru [Tt]arihleri?\s*[:：]?\s*" + DT + r"\s*[-–]\s*" + DT,
        "PENCERE",
        r"[Bb]aşvuru.{0,100}?" + DT + r"\s*[-–]\s*" + DT + r".{0,40}?tarihleri arasında",
        r"[Bb]aşvuru.{0,60}?(?:bitiş|son gün)\D{0,20}?" + DT,
    ]
    lo, hi = yayin - datetime.timedelta(days=3), yayin + datetime.timedelta(days=60)
    for rx in pats:
        bul = []
        if rx == "PENCERE":
            for w in re.finditer(r"[Bb]aşvurular", txt):
                win = txt[w.start():w.start() + 220]
                for m in re.finditer(DT + r"(?=.{0,50}?(?:sona erecek|bitecek|kadar))", win):
                    d = parse_date(m.group(1))
                    if d and lo <= d <= hi:
                        bul.append(d)
            if bul:
                return max(bul)
            continue
        for m in re.finditer(rx, txt):
            d = parse_date(m.groups()[-1])
            if d and lo <= d <= hi:
                bul.append(d)
        if bul:
            return max(bul)
    m = re.search(r"yayımlandığı tarihten itibaren (\d{1,2}) \(?[a-zçğıöşü ]*\)? ?(?:gün|iş günü)", tr_lower(txt))
    if m:
        return yayin + datetime.timedelta(days=int(m.group(1)))
    return None

def main():
    dene = os.environ.get("DENE") == "1"
    ca = ca_bundle()
    ads, skip = [], 0
    while skip < 600:
        r = requests.post(API + "Ad/AdsByFilter", json={"keys": {"ats": [5]}, "skipCount": skip, "maxResultCount": 20}, headers=H, timeout=45, verify=ca)
        r.raise_for_status()
        res = r.json()["result"]
        batch = res.get("ads", [])
        if not batch:
            break
        ads += batch
        skip += len(batch)
        if skip >= res.get("numFound", 0):
            break
        time.sleep(1)
    seen = set(); ads = [a for a in ads if not (str(a.get("id")) in seen or seen.add(str(a.get("id"))))]
    print("İlan.gov.tr personel ilanı:", len(ads))
    try:
        old = {x["id"]: x for x in json.load(open(OUT, encoding="utf-8")).get("items", [])}
    except Exception:
        old = {}
    items, yeni = [], 0
    for a in ads:
        aid = str(a.get("id", ""))
        t = " ".join(str(a.get("title", "")).split())
        if not aid or not t or a.get("isArchived"):
            continue
        k = " ".join(str(a.get("advertiserName", "")).split())
        f = {x.get("key"): x.get("value") for x in a.get("adTypeFilters") or []}
        yayin = parse_date(f.get("Resmî Gazete Yayım Tarihi", "") or "") or datetime.date.fromisoformat(str(a.get("publishStartDate", ""))[:10]) + datetime.timedelta(days=1)
        url = "https://www.ilan.gov.tr" + str(a.get("urlStr", ""))
        no = str(a.get("adNo", ""))
        tur = "akademik" if no.startswith("YOK") or "akademik-personel-alimlari" in url else "kamu"
        if aid in old:
            it = old[aid]
        else:
            sb = None
            try:
                d = requests.get(API + "AdDetail/GetAdDetail", params={"id": aid}, headers=H, timeout=45, verify=ca)
                if d.ok:
                    sb = son_basvuru(d.json().get("result", {}).get("content", ""), yayin)
                time.sleep(0.7)
            except Exception as e:
                print("detay alınamadı", aid, e)
            it = {"id": aid, "t": t[:160], "k": k[:120], "il": str(a.get("addressCityName") or "")[:30], "d": yayin.isoformat(),
                  "sb": sb.isoformat() if sb else "", "u": url, "c": tur, "p": meslek(t, k), "x": 1 if "iptal" in tr_lower(t) else 0}
            yeni += 1
        items.append(it)
    # Süresi geçenleri at; son başvurusu bilinmeyenleri yayından 30 gün sonra at
    def aktif(x):
        if x.get("sb"):
            return x["sb"] >= TODAY.isoformat()
        return x["d"] >= (TODAY - datetime.timedelta(days=30)).isoformat()
    items = [x for x in items if aktif(x)]
    items.sort(key=lambda x: (x["d"], x["id"]), reverse=True)
    items = items[:300]
    print("Aktif:", len(items), "yeni:", yeni, "son başvurusu bulunan:", sum(1 for x in items if x["sb"]))
    for x in items[:12]:
        print(" ", x["d"], "| sb", x["sb"] or "-", "|", x["c"], x["p"] or "-", "|", x["t"][:80])
    if dene:
        return
    j = {"updated": TODAY.isoformat(), "kaynak": "ilan.gov.tr (Basın İlan Kurumu)", "items": items}
    prev = None
    try:
        prev = json.load(open(OUT, encoding="utf-8"))
    except Exception:
        pass
    if prev and prev.get("items") == items:
        print("Değişiklik yok.")
        return
    json.dump(j, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)

if __name__ == "__main__":
    main()
