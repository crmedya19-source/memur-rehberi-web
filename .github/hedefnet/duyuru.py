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
sinif=gonder=hata=dsinif=yeniS=0; tok=None; esik=datetime.now(timezone.utc)-timedelta(hours=6)
while True:
    u=DB+"/hn_sinif?pageSize=300&mask.fieldPaths=duyurular&mask.fieldPaths=pushSon&mask.fieldPaths=ad"+(f"&pageToken={tok}" if tok else "")
    s,j=api("GET",u)
    if s!=200: print("liste hatası", s); break
    for d in j.get("documents",[]):
        sinif+=1; f=d.get("fields",{}); sid=d["name"].split("/")[-1]
        du=[x.get("mapValue",{}).get("fields",{}) for x in f.get("duyurular",{}).get("arrayValue",{}).get("values",[])]
        if not du: continue
        dsinif+=1
        son=sv(f.get("pushSon",{}))
        # pushSon'dan sonra gelenler; ilk çalışmada yalnızca son 6 saattekiler (eski duyurular için bildirim yağmasın)
        ids=[sv(x.get("id",{})) for x in du]
        yeni=du[ids.index(son)+1:] if son in ids else [x for x in du if sv(x.get("tarih",{})) and datetime.fromisoformat(sv(x["tarih"]).replace("Z","+00:00"))>esik]
        ad=sv(f.get("ad",{}))[:40] or "Sınıf"
        yeniS+=len(yeni)
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
print(f"sınıf {sinif} · duyurulu {dsinif} · yeni duyuru {yeniS} · bildirim {gonder} · hata {hata}")

# ---------------- Haftalık veli özeti (pazar 19:00 sonrası, haftada bir) ----------------
TR=timezone(timedelta(hours=3))
simdi=datetime.now(TR)
DENEME = os.environ.get("VELI_DENEME") == "1"   # elle deneme: gönderme, yalnızca say
if (simdi.weekday()==6 and simdi.hour>=19) or DENEME:
    pazartesi=(simdi.date()-timedelta(days=simdi.weekday())).isoformat()
    def num(v): return v.get("integerValue") or v.get("doubleValue") or 0
    def mp(v): return (v or {}).get("mapValue",{}).get("fields",{})
    def arr(v): return (v or {}).get("arrayValue",{}).get("values",[])
    def dkyaz(dk):
        dk=int(round(float(dk or 0))); return f"{dk//60} sa {dk%60} dk" if dk>=60 else f"{dk} dk"
    def netfmt(x): return (f"{x:.2f}".rstrip("0").rstrip(".")).replace(".",",")
    ogr=gonderV=atla=hataV=0; tok=None
    alan="&".join("mask.fieldPaths="+f for f in ["ad","ozet","denemeler","veliler","konuOz","gorevOz","veliRaporHafta"])
    while True:
        s,j=api("GET",DB+"/hn_ogrenci?pageSize=200&"+alan+(f"&pageToken={tok}" if tok else ""))
        if s!=200: print("öğrenci listesi hatası", s); break
        for d in j.get("documents",[]):
            f=d.get("fields",{}); uid=d["name"].split("/")[-1]
            if not arr(f.get("veliler")): continue
            ogr+=1
            if sv(f.get("veliRaporHafta",{}))==pazartesi and not DENEME: atla+=1; continue
            ad=(sv(f.get("ad",{})) or "Öğrenciniz").split(" ")[0][:20]
            oz=mp(f.get("ozet")); hf=mp(oz.get("hf"))
            bu = sv(hf.get("h",{}))==pazartesi
            dk=float(num(hf.get("dk",{}))) if bu else 0; soru=int(float(num(hf.get("soru",{})))) if bu else 0
            dn=[mp(x) for x in arr(f.get("denemeler"))]
            def toplam(x): return sum(float(num(v)) for v in mp(x.get("n")).values())
            bu_dn=[x for x in dn if sv(x.get("d",{}))>=pazartesi]
            parca=[]
            if dk or soru: parca.append(f"{dkyaz(dk)} odak, {soru} soru")
            if bu_dn:
                x=bu_dn[0]; tur=sv(x.get("t",{})) or "TYT"; t=toplam(x)
                onceki=[y for y in dn if sv(y.get("t",{}))==tur and sv(y.get("d",{}))<sv(x.get("d",{}))]
                fark=f" ({'+' if t-toplam(onceki[0])>=0 else ''}{netfmt(t-toplam(onceki[0]))})" if onceki else ""
                parca.append(f"{len(bu_dn)} deneme, son {tur} {netfmt(t)} net{fark}")
            gr=[mp(x) for x in arr(f.get("gorevOz"))]
            if gr: parca.append(f"görev {sum(1 for g in gr if int(float(num(g.get('t',{})) or 0)))}/{len(gr)}")
            kron=""
            for k in arr(f.get("konuOz")):
                p=sv(k).split("\t")
                if len(p)>=8:
                    N,D,gor,kay=float(p[3] or 0),float(p[4] or 0),int(float(p[6] or 0)),int(float(p[7] or 0))
                    if N and gor>=3 and kay>=-(-gor*2//3) and D/N<0.7 and not (D==0 and float(p[5] or 0)==0): kron=p[1][:40]; break
            govde=("Bu hafta: "+", ".join(parca)+"." if parca else "Bu hafta Hedef Net'te çalışma kaydı görünmüyor.")+(f" Takıldığı konu: {kron}." if kron else "")+" Ayrıntılar için dokunun."
            if DENEME: gonderV+=1; continue
            msg={"message":{"topic":"hn_v_"+uid,"notification":{"title":f"📊 {ad} – haftalık özet","body":govde[:240]},
                 "android":{"notification":{"channel_id":"veli","icon":"ic_stat_icon","color":"#6C4CF5"}},"data":{"tip":"veli"}}}
            s2,j2=api("POST",f"https://fcm.googleapis.com/v1/projects/{P}/messages:send",msg)
            if s2==200:
                gonderV+=1
                api("PATCH",f"{DB}/hn_ogrenci/{uid}?updateMask.fieldPaths=veliRaporHafta",{"fields":{"veliRaporHafta":{"stringValue":pazartesi}}})
            else: hataV+=1; print("veli bildirimi hatası", s2, (j2.get("error") or {}).get("status",""))
        tok=j.get("nextPageToken")
        if not tok: break
    print(f"veli özeti{' (DENEME, gönderilmedi)' if DENEME else ''}: velili öğrenci {ogr} · gönderilen {gonderV} · bu hafta zaten {atla} · hata {hataV}")
