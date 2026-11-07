import json, requests
H={'accept':'text/plain','content-type':'application/json-patch+json','origin':'https://www.ilan.gov.tr','referer':'https://www.ilan.gov.tr/ilan/tum-ilanlar','user-agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36','x-request-origin':'IGT-UI','x-requested-with':'XMLHttpRequest'}
U="https://www.ilan.gov.tr/api/api/services/app/"
r=requests.post(U+"Ad/AdsByFilter",json={"keys":{"ats":[5]},"skipCount":0,"maxResultCount":30},headers=H,timeout=40)
print("STATUS",r.status_code)
j=r.json()["result"];print("NUMFOUND",j.get("numFound"))
print("CATS",json.dumps([(c.get("taxId"),c.get("name"),c.get("count")) for c in j.get("categories",[])],ensure_ascii=False)[:1500])
for a in j["ads"][:30]:
  print("AD",json.dumps({k:a.get(k) for k in ("id","adNo","title","advertiserName","addressCityName","publishStartDate","urlStr","isArchived")},ensure_ascii=False),json.dumps(a.get("adTypeFilters"),ensure_ascii=False)[:400])
print("KEYS",list(j["ads"][0].keys()))
d=requests.post(U+"AdDetail/GetAdDetail",json={"id":j["ads"][0]["id"]},headers=H,timeout=40)
print("DSTATUS",d.status_code)
dr=d.json().get("result",{});print("DKEYS",list(dr.keys()));print("DFILT",json.dumps(dr.get("adTypeFilters"),ensure_ascii=False)[:800]);print("DCAT",json.dumps(dr.get("categories"),ensure_ascii=False)[:500]);print("DCONTENT",(dr.get("content") or "")[:1500])
