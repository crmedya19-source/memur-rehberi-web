"""Hedef Net Android uygulamasını Firebase'e kaydeder, SHA parmak izlerini ekler, yapılandırmayı base64 yazar."""
import os, json, time, base64, urllib.request, urllib.error
from google.oauth2 import service_account
from google.auth.transport.requests import Request
sa=json.loads(os.environ["FCM_SERVICE_ACCOUNT"]); P=sa["project_id"]
cr=service_account.Credentials.from_service_account_info(sa, scopes=["https://www.googleapis.com/auth/cloud-platform","https://www.googleapis.com/auth/firebase"]); cr.refresh(Request())
def api(m,u,b=None):
    r=urllib.request.Request(u,method=m,data=None if b is None else json.dumps(b).encode(),headers={"Authorization":"Bearer "+cr.token,"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(r) as x: return x.status, json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except Exception: return e.code, {}
B=f"https://firebase.googleapis.com/v1beta1/projects/{P}"
PKG="com.hedefnet.yks"
s,j=api("GET",B+"/androidApps"); print("liste",s, (j.get("error") or {}).get("message",""))
app=next((a for a in j.get("apps",[]) if a.get("packageName")==PKG), None)
if not app and s==200:
    s,j=api("POST",B+"/androidApps",{"packageName":PKG,"displayName":"Hedef Net"}); print("oluştur",s,(j.get("error") or {}).get("message",""))
    if s==200 and j.get("name","").startswith("operations/"):
        for _ in range(20):
            time.sleep(3); s2,j2=api("GET","https://firebase.googleapis.com/v1beta1/"+j["name"])
            if j2.get("done"): app=j2.get("response"); break
if app:
    aid=app["appId"]; print("appId",aid)
    s,j=api("GET",f"{B}/androidApps/{aid}/sha"); var={c["shaHash"].lower() for c in j.get("certificates",[])}
    for h,t in [(os.environ["SHA1"],"SHA_1"),(os.environ["SHA256"],"SHA_256")]:
        hh=h.replace(":","").lower()
        if hh not in var: s,j=api("POST",f"{B}/androidApps/{aid}/sha",{"shaHash":hh,"certType":t}); print("sha",t,s,(j.get("error") or {}).get("message",""))
        else: print("sha",t,"zaten var")
    s,j=api("GET",f"{B}/androidApps/{aid}/config")
    if s==200: print("CONFIG_B64", j["configFileContents"])
    else: print("config",s)
print("BITTI")
