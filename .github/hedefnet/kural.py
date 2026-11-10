"""firestore.rules sözdizimini Firebase Rules API ile denetler: yayınlanmamış bir kural seti oluşturur (yayınlamaz). Yalnızca hata satırları yazılır."""
import os, json, sys, urllib.request, urllib.error
from google.oauth2 import service_account
from google.auth.transport.requests import Request
sa=json.loads(os.environ["FCM_SERVICE_ACCOUNT"]); P=sa["project_id"]
cr=service_account.Credentials.from_service_account_info(sa, scopes=["https://www.googleapis.com/auth/cloud-platform"]); cr.refresh(Request())
src=open(os.path.join(os.path.dirname(__file__),"firestore.rules")).read()
r=urllib.request.Request(f"https://firebaserules.googleapis.com/v1/projects/{P}/rulesets",method="POST",
  data=json.dumps({"source":{"files":[{"name":"firestore.rules","content":src}]}}).encode(),headers={"Authorization":"Bearer "+cr.token,"Content-Type":"application/json"})
try:
    with urllib.request.urlopen(r) as x: j=json.loads(x.read() or b"{}"); s=x.status
except urllib.error.HTTPError as e:
    s=e.code; j=json.loads(e.read() or b"{}")
iss=j.get("issues",[]) or ((j.get("error") or {}).get("details") or [])
print("durum", s)
if s==400:
    import re; m=(j.get("error") or {}).get("message",""); print(m[:2000]); sys.exit(1)
for i in j.get("issues",[]): p=i.get("sourcePosition",{}); print("SORUN", i.get("severity"), f"satır {p.get('line')}:{p.get('column')}", i.get("description"))
if s!=200: print((j.get("error") or {}).get("message","")); sys.exit(1)
if any(i.get("severity")=="ERROR" for i in j.get("issues",[])): sys.exit(1)
print("KURALLAR GEÇERLİ")
