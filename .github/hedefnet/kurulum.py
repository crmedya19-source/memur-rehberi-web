"""Hedef Net Firebase kurulumu: Firestore veritabanı, e-posta girişi, güvenlik kuralları.
Hizmet hesabı anahtarı yalnızca GitHub secret'tan okunur, hiçbir yere yazılmaz."""
import os, json, sys, time, urllib.request, urllib.error
from google.oauth2 import service_account
from google.auth.transport.requests import Request
sa = json.loads(os.environ["FCM_SERVICE_ACCOUNT"]); P = sa["project_id"]
cr = service_account.Credentials.from_service_account_info(sa, scopes=["https://www.googleapis.com/auth/cloud-platform","https://www.googleapis.com/auth/firebase"])
cr.refresh(Request()); TOK = cr.token
def api(method, url, body=None):
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": "Bearer "+TOK, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: j = json.loads(e.read())
        except Exception: j = {}
        return e.code, j
def ozet(j):
    if isinstance(j,dict) and "error" in j: return str(j["error"].get("message",""))[:200]
    return "ok"
print("Proje:", P, "| hizmet hesabı:", sa.get("client_email","").split("@")[0])

# 1) Firestore veritabanı
s, j = api("GET", f"https://firestore.googleapis.com/v1/projects/{P}/databases")
print("Firestore listele:", s, ozet(j))
dbs = [d.get("name","").split("/")[-1] for d in j.get("databases", [])] if s == 200 else []
if s == 200 and "(default)" not in dbs:
    s2, j2 = api("POST", f"https://firestore.googleapis.com/v1/projects/{P}/databases?databaseId=(default)",
                 {"locationId": "eur3", "type": "FIRESTORE_NATIVE"})
    print("Firestore oluştur:", s2, ozet(j2))
    for _ in range(24):
        time.sleep(5); s3, j3 = api("GET", f"https://firestore.googleapis.com/v1/projects/{P}/databases/(default)")
        if s3 == 200: print("Firestore hazır:", j3.get("locationId")); break

# 2) E-posta/şifre girişi
s, j = api("GET", f"https://identitytoolkit.googleapis.com/admin/v2/projects/{P}/config")
print("Auth yapılandırma:", s, "e-posta:", j.get("signIn",{}).get("email",{}).get("enabled") if s==200 else ozet(j))
if s == 404 or (s == 200 and not j.get("signIn")):
    s0, j0 = api("POST", f"https://identitytoolkit.googleapis.com/v2/projects/{P}/identityPlatform:initializeAuth", {})
    print("Auth başlat:", s0)
email_on = s == 200 and j.get("signIn", {}).get("email", {}).get("enabled")
if not email_on:
    s4, j4 = api("PATCH", f"https://identitytoolkit.googleapis.com/admin/v2/projects/{P}/config?updateMask=signIn.email.enabled,signIn.email.passwordRequired",
                 {"signIn": {"email": {"enabled": True, "passwordRequired": True}}})
    print("E-posta girişi aç:", s4, "tamam" if s4==200 else str(j4.get("error",{}).get("message",""))[:200])

# 3) Güvenlik kuralları (yalnızca mevcut kurallar boş/varsayılan ya da zaten Hedef Net'e aitse)
s, j = api("GET", f"https://firebaserules.googleapis.com/v1/projects/{P}/releases/cloud.firestore")
print("Mevcut kural sürümü:", s, ozet(j))
uygula = True
if s == 200:
    rs = j.get("rulesetName"); s5, j5 = api("GET", f"https://firebaserules.googleapis.com/v1/{rs}")
    eski = "".join(f.get("content","") for f in j5.get("source", {}).get("files", []))
    yabanci = [l for l in eski.splitlines() if "match /" in l and "databases" not in l and "/hn_" not in l and "{document=**}" not in l]
    if yabanci: uygula = False; print("DİKKAT: Başka koleksiyon kuralları var, otomatik değiştirilmedi:", yabanci)
if uygula:
    src = open(os.path.join(os.path.dirname(__file__), "firestore.rules")).read()
    s6, j6 = api("POST", f"https://firebaserules.googleapis.com/v1/projects/{P}/rulesets", {"source": {"files": [{"name": "firestore.rules", "content": src}]}})
    print("Kural seti:", s6, ozet(j6) if s6 != 200 else j6.get("name"))
    if s6 == 200:
        rel = {"name": f"projects/{P}/releases/cloud.firestore", "rulesetName": j6["name"]}
        s7, j7 = api("PATCH", f"https://firebaserules.googleapis.com/v1/projects/{P}/releases/cloud.firestore", {"release": rel})
        if s7 == 404: s7, j7 = api("POST", f"https://firebaserules.googleapis.com/v1/projects/{P}/releases", rel)
        print("Kural yayını:", s7, ozet(j7))
print("BITTI")
