"""Hedef Net: yeni sınıf duyurularını FCM ile o sınıfın konusuna (hn_s_<sınıfId>) bildirim olarak gönderir.
Herkese açık depo: kayıtlara sınıf adı, duyuru metni ya da kimlik YAZILMAZ, yalnızca sayılar."""
import os, json, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from google.oauth2 import service_account
from google.auth.transport.requests import Request
sa=json.loads(os.environ["FCM_SERVICE_ACCOUNT"]); P=sa["project_id"]
cr=service_account.Credentials.from_service_account_info(sa, scopes=["https://www.googleapis.com/auth/datastore","https://www.googleapis.com/auth/firebase.messaging"]); cr.refresh(Request())
def api(m,u,b=None):
    r=urllib.request.Request(u,method=m,data=None if b is None else json.dumps(b).encode(),headers={"Authorization":"Bearer "+cr.token,"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(r, timeout=30) as x: return x.status, json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except Exception: return e.code, {}
DB=f"https://firestore.googleapis.com/v1/projects/{P}/databases/(default)/documents"
def sv(v): return v.get("stringValue") or v.get("timestampValue") or ""
sinif=gonder=hata=0; tok=None; esik=datetime.now(timezone.utc)-timedelta(hours=6)
while True:
    u=DB+"/hn_sinif?pageSize=300&mask.fieldPaths=duyurular&mask.fieldPaths=pushSon&mask.fieldPaths=ad"+(f"&pageToken={tok}" if tok else "")
    s,j=api("GET",u)
    if s!=200: print("liste hatası", s); break
    for d in j.get("documents",[]):
        sinif+=1; f=d.get("fields",{}); sid=d["name"].split("/")[-1]
        du=[x.get("mapValue",{}).get("fields",{}) for x in f.get("duyurular",{}).get("arrayValue",{}).get("values",[])]
        if not du: continue
        son=sv(f.get("pushSon",{}))
        # pushSon'dan sonra gelenler; ilk çalışmada yalnızca son 6 saattekiler (eski duyurular için bildirim yağmasın)
        ids=[sv(x.get("id",{})) for x in du]
        yeni=du[ids.index(son)+1:] if son in ids else [x for x in du if sv(x.get("tarih",{})) and datetime.fromisoformat(sv(x["tarih"]).replace("Z","+00:00"))>esik]
        ad=sv(f.get("ad",{}))[:40] or "Sınıf"
        for x in [y for y in yeni if not y.get("bildir",{}).get("booleanValue",True)==False][-3:]:
            msg={"message":{"topic":"hn_s_"+sid,"notification":{"title":"📢 "+ad,"body":sv(x.get("metin",{}))[:240]},
                 "android":{"priority":"high","notification":{"channel_id":"duyuru","icon":"ic_stat_icon","color":"#6C4CF5"}},"data":{"tip":"duyuru","sid":sid}}}
            s2,j2=api("POST",f"https://fcm.googleapis.com/v1/projects/{P}/messages:send",msg)
            if s2==200: gonder+=1
            else: hata+=1; print("gönderim hatası", s2, (j2.get("error") or {}).get("status",""))
        if ids[-1]!=son:
            s3,_=api("PATCH",f"{DB}/hn_sinif/{sid}?updateMask.fieldPaths=pushSon",{"fields":{"pushSon":{"stringValue":ids[-1]}}})
            if s3!=200: hata+=1; print("işaret hatası", s3)
    tok=j.get("nextPageToken")
    if not tok: break
print(f"sınıf {sinif} · bildirim {gonder} · hata {hata}")
