import json, requests, ssl, certifi, os
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import ExtensionOID, AuthorityInformationAccessOID
def bundle(host):
    # Sunucu ara sertifikayı göndermiyor: AIA adresinden indirip güven zincirine ekle (doğrulama açık kalır)
    pem=ssl.get_server_certificate((host,443));leaf=x509.load_pem_x509_certificate(pem.encode())
    extra=b""
    cur=leaf
    for _ in range(3):
        try: aia=cur.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
        except Exception: break
        urls=[d.access_location.value for d in aia if d.access_method==AuthorityInformationAccessOID.CA_ISSUERS]
        if not urls: break
        raw=requests.get(urls[0],timeout=30).content
        try: c=x509.load_der_x509_certificate(raw)
        except Exception: c=x509.load_pem_x509_certificate(raw)
        print("ARA SERTIFIKA",c.subject.rfc4514_string()[:120])
        extra+=c.public_bytes(Encoding.PEM)
        if c.issuer==c.subject: break
        cur=c
    p="/tmp/ilan_ca.pem";open(p,"wb").write(open(certifi.where(),"rb").read()+b"\n"+extra);return p
CA=bundle("www.ilan.gov.tr")
H={'accept':'text/plain','content-type':'application/json-patch+json','origin':'https://www.ilan.gov.tr','referer':'https://www.ilan.gov.tr/ilan/tum-ilanlar','user-agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36','x-request-origin':'IGT-UI','x-requested-with':'XMLHttpRequest'}
U="https://www.ilan.gov.tr/api/api/services/app/"
r=requests.post(U+"Ad/AdsByFilter",json={"keys":{"ats":[5]},"skipCount":0,"maxResultCount":30},headers=H,timeout=40,verify=CA)
print("STATUS",r.status_code)
j=r.json()["result"];print("NUMFOUND",j.get("numFound"))
print("CATS",json.dumps([(c.get("taxId"),c.get("name"),c.get("count")) for c in j.get("categories",[])],ensure_ascii=False)[:1500])
for a in j["ads"][:30]:
  print("AD",json.dumps({k:a.get(k) for k in ("id","adNo","title","advertiserName","addressCityName","publishStartDate","urlStr","isArchived")},ensure_ascii=False),json.dumps(a.get("adTypeFilters"),ensure_ascii=False)[:400])
print("KEYS",list(j["ads"][0].keys()))
for aid in [a["id"] for a in j["ads"] if a["adNo"].startswith("DPB")][:3]:
  d=requests.get(U+"AdDetail/GetAdDetail",params={"id":aid},headers=H,timeout=40,verify=CA)
  print("DSTATUS",d.status_code)
  dr=d.json().get("result",{});print("DKEYS",list(dr.keys()));print("DFILT",json.dumps(dr.get("adTypeFilters"),ensure_ascii=False)[:800]);print("DVAL",json.dumps(dr.get("values"),ensure_ascii=False)[:500])
  import re;txt=re.sub(r"<[^>]+>"," ",dr.get("content") or "");txt=re.sub(r"\s+"," ",txt);print("DLEN",len(txt));
  for m in re.finditer(r"[Bb]aşvuru",txt): print("DCTX",txt[max(0,m.start()-150):m.start()+200])
print("ALLDPB",len([a for a in j["ads"] if a["adNo"].startswith("DPB")]))
r2=requests.post(U+"Ad/AdsByFilter",json={"keys":{"ats":[5]},"skipCount":30,"maxResultCount":80},headers=H,timeout=40,verify=CA).json()["result"]
for a in r2["ads"]:
  if not a["adNo"].startswith("YOK"): print("NONYOK",a["adNo"],a["title"][:90],a["publishStartDate"][:10])
print("PREFIX",sorted({a["adNo"][:3] for a in j["ads"]+r2["ads"]}))
