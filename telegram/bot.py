#!/usr/bin/env python3
"""Memur Rehberi Telegram botu (telefonda Termux ile çalışır).

- ilanlar.json ve haberler.json'u (memur-rehberi-web) izler, yenileri kanala atar.
- Her mesajın altında "Uygulamayı indir" düğmesi.
- Akşam özeti: bugünkü ilan sayısı + son başvurusu yaklaşanlar.
- Özel sohbet komutları: /start /ilanlar /yaklasan /haberler /uygulama ; sahip için /durum /dur /devam /test
Yalnızca Python standart kütüphanesi kullanılır. Token ayar.json'da durur, hiçbir yere gönderilmez.
"""
import json, os, sys, time, html, signal, traceback, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timedelta, timezone

KLASOR = os.path.dirname(os.path.abspath(__file__))
GH = os.environ.get("TG_GH") == "1"  # GitHub Actions kipi: tek geçiş, token gizli ayardan, durum depoda
AYAR = os.path.join(KLASOR, "ayar-gh.json" if GH else "ayar.json")
DURUM = os.path.join(KLASOR, "durum-gh.json" if GH else "durum.json")
KAYIT = None if GH else os.path.join(KLASOR, "bot.log")
TR = timezone(timedelta(hours=3))
VARSAYILAN = {
    "token": "", "kanal": "", "sahip": 0,
    "uygulama_url": "",          # boş: düğme ve uygulama tanıtımı yok (uygulama yayınlanınca /link ile eklenir)
    "veri_url": "https://crmedya19-source.github.io/memur-rehberi-web/",
    "akademik": "ozet",          # hepsi | ozet | yok
    "haber": True,               # haberleri de at
    "sessiz": [23, 8],           # bu saatler arasında kanala gönderme (kuyrukta bekler)
    "aralik_dk": 4,              # iki kanal mesajı arasındaki en az süre
    "kontrol_dk": 15,            # verinin kaç dakikada bir okunacağı
    "ozet_saat": 20,             # akşam özeti saati (-1: kapalı)
    "gunluk_sinir": 25,          # kanala günde en fazla mesaj
}
API_KOK = os.environ.get("TG_API", "https://api.telegram.org")  # testler için değiştirilebilir
MESLEK = {"z": "Zabıta", "f": "İtfaiye", "s": "Sağlık", "p": "Polis/Bekçi", "j": "Jandarma", "o": "Öğretmen", "i": "İnfaz koruma", "d": "Diyanet", "k": "Adalet", "g": "Belediye/İl idaresi"}
CALISIYOR = True


def simdi():
    return datetime.now(TR)


def log(*a):
    satir = simdi().strftime("%d.%m %H:%M:%S ") + " ".join(str(x) for x in a)
    print(satir, flush=True)
    if not KAYIT:
        return
    try:
        if os.path.exists(KAYIT) and os.path.getsize(KAYIT) > 2_000_000:
            os.replace(KAYIT, KAYIT + ".eski")
        with open(KAYIT, "a", encoding="utf-8") as f:
            f.write(satir + "\n")
    except Exception:
        pass


def oku(yol, vars_):
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return vars_


def yaz(yol, veri):
    gecici = yol + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=1)
    os.replace(gecici, yol)


ESKI_LINK = "https://play.google.com/store/apps/details?id=com.memurmevzuat.rehber"


def ayar_yukle():
    a = dict(VARSAYILAN)
    a.update(oku(AYAR, {}))
    if os.environ.get("TELEGRAM_TOKEN"):
        a["token"] = os.environ["TELEGRAM_TOKEN"].strip()
    if a.get("uygulama_url") == ESKI_LINK:  # uygulama henüz yayında değil
        a["uygulama_url"] = ""
    return a


# ---------------- Telegram ----------------
class TG:
    def __init__(self, token):
        self.k = f"{API_KOK}/bot{token}/"

    def cagir(self, yontem, veri=None, zaman=40):
        govde = json.dumps(veri or {}).encode()
        for deneme in range(4):
            try:
                r = urllib.request.Request(self.k + yontem, data=govde, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(r, timeout=zaman + 10) as x:
                    return json.loads(x.read())["result"]
            except urllib.error.HTTPError as e:
                try:
                    j = json.loads(e.read())
                except Exception:
                    j = {}
                bekle = (j.get("parameters") or {}).get("retry_after")
                if e.code == 429 and bekle:
                    log("Telegram yavaşla dedi, bekleniyor", bekle, "sn")
                    time.sleep(int(bekle) + 1)
                    continue
                raise RuntimeError(f"Telegram {e.code}: {j.get('description', '')}")
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if deneme == 3:
                    raise
                time.sleep(5 * (deneme + 1))
        raise RuntimeError("Telegram'a ulaşılamadı")

    def gonder(self, sohbet, metin, dugme=None, onizleme=False):
        v = {"chat_id": sohbet, "text": metin, "parse_mode": "HTML", "link_preview_options": {"is_disabled": not onizleme}}
        if dugme:
            v["reply_markup"] = {"inline_keyboard": [[{"text": t, "url": u}] for t, u in dugme]}
        return self.cagir("sendMessage", v)


# ---------------- Veri ----------------
def veri_al(url):
    if GH:  # depodaki güncel dosyayı oku
        yerel = os.path.join(KLASOR, "..", url.rstrip("/").split("/")[-1])
        if os.path.exists(yerel):
            with open(yerel, encoding="utf-8") as f:
                return json.load(f)
    r = urllib.request.Request(url + ("&" if "?" in url else "?") + "t=" + str(int(time.time())), headers={"User-Agent": "MemurRehberiBot/1.0"})
    with urllib.request.urlopen(r, timeout=30) as x:
        return json.loads(x.read().decode("utf-8"))


def e(s):
    return html.escape(str(s or ""), quote=False)


def tarih_tr(iso):
    try:
        d = datetime.fromisoformat(iso[:10])
        aylar = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        return f"{d.day} {aylar[d.month - 1]}"
    except Exception:
        return iso


def kalan_gun(iso):
    try:
        return (datetime.fromisoformat(iso[:10]).date() - simdi().date()).days
    except Exception:
        return None


def tr_baslik(s):
    s = str(s or "").replace("I", "ı").replace("İ", "i").lower()
    ust = lambda c: {"i": "İ", "ı": "I"}.get(c, c.upper())
    kucuk = {"ve", "ile", "veya", "de", "da", "ve/veya"}
    kisalt = {"tbmm", "sgk", "tüik", "meb", "afad", "ptt", "trt", "kpss", "ösym", "tcdd", "toki", "msb", "bddk", "spk", "tmo", "dsi", "dsı", "kgm", "mta", "aöf", "ab", "tc", "t.c."}
    def kelime(j, w):
        on = "(" if w.startswith("(") else ""
        g = w[len(on):]
        if not g:
            return w
        if g.strip("),") in kisalt or g.rstrip(",") in ("t.c.", "a.ş.", "a.ş"):
            return on + "".join(ust(c) for c in g)
        if j and not on and g in kucuk:
            return w
        return on + ust(g[0]) + g[1:]
    return " ".join(kelime(j, w) for j, w in enumerate(s.split(" ")))


def ilan_metni(x, baslik=None, reklam=False):
    bas = baslik or ("🎓 <b>Akademik personel alımı</b>" if x.get("c") == "akademik" else "🏛️ <b>Yeni kamu personel alımı</b>")
    m = [bas, "", f"<b>{e(x.get('t'))}</b>"]
    yer = " · ".join(s for s in [e(tr_baslik(x.get("k"))), e(tr_baslik(x.get("il")))] if s)
    if yer:
        m.append("📍 " + yer)
    meslek = ", ".join(MESLEK[c] for c in (x.get("p") or "") if c in MESLEK)
    if meslek:
        m.append("👔 " + meslek)
    if x.get("sb"):
        k = kalan_gun(x["sb"])
        m.append(f"⏳ Son başvuru: <b>{tarih_tr(x['sb'])}</b>" + (f" ({k} gün kaldı)" if k is not None and k >= 0 else ""))
    m.append(f"🗓️ Yayın: {tarih_tr(x.get('d', ''))}")
    m += ["", f'🔗 <a href="{e(x.get("u"))}">İlanın tamamı (ilan.gov.tr)</a>']
    if reklam:
        m += ["", "📲 Başvuru tarihlerini kaçırmamak için hatırlatmalı takip: <b>Memur Rehberi</b> uygulaması"]
    return "\n".join(m)


def haber_metni(x, reklam=False):
    m = [f"📰 <b>{e(x.get('t'))}</b>"]
    if x.get("s"):
        m += ["", e(x["s"])[:900]]
    m += ["", f'🔗 <a href="{e(x.get("u"))}">Haberin devamı</a>' + (f" · {e(x.get('src'))}" if x.get("src") else "")]
    if reklam:
        m += ["", "📲 Memur gündemi, mevzuat ve maaş hesaplama: <b>Memur Rehberi</b>"]
    return "\n".join(m)


# ---------------- Bot ----------------
class Bot:
    def __init__(self):
        self.a = ayar_yukle()
        if not self.a["token"] or not self.a["kanal"]:
            print("Önce kurulum: python bot.py kurulum")
            sys.exit(1)
        self.tg = TG(self.a["token"])
        self.d = oku(DURUM, {})
        self.d.setdefault("gorulen", {"ilan": [], "haber": []})
        self.d.setdefault("kuyruk", [])
        self.d.setdefault("offset", 0)
        self.d.setdefault("gun", {})
        self.d.setdefault("duraklat", False)
        self.d.setdefault("son_kanal", 0)
        self.son_kontrol = 0
        self.son_veri = {"ilan": [], "haber": []}
        self.hata_say = 0

    def kaydet(self):
        self.d["gorulen"]["ilan"] = self.d["gorulen"]["ilan"][-3000:]
        self.d["gorulen"]["haber"] = self.d["gorulen"]["haber"][-1000:]
        yaz(DURUM, self.d)

    def bugun(self):
        g = simdi().date().isoformat()
        if self.d["gun"].get("t") != g:
            self.d["gun"] = {"t": g, "gonderilen": 0, "kamu": 0, "akademik": 0, "haber": 0, "ozet": False}
        return self.d["gun"]

    def reklam(self):
        return bool(self.a.get("uygulama_url"))

    def dugme(self):
        if not self.reklam():
            return None
        return [("📲 Memur Rehberi'ni indir" if "play.google.com" in self.a["uygulama_url"] else "📲 Memur Rehberi", self.a["uygulama_url"])]

    # -- veri kontrolü
    def kontrol(self):
        ilk = not self.d["gorulen"]["ilan"] and not self.d["gorulen"]["haber"]
        ilanlar = veri_al(self.a["veri_url"] + "ilanlar.json").get("items", [])
        haberler = veri_al(self.a["veri_url"] + "haberler.json").get("items", []) if self.a["haber"] else []
        self.son_veri = {"ilan": ilanlar, "haber": haberler}
        gi, gh = set(self.d["gorulen"]["ilan"]), set(self.d["gorulen"]["haber"])
        yeni = 0
        g = self.bugun()
        for x in sorted(ilanlar, key=lambda x: x.get("d", "")):
            i = str(x.get("id"))
            if i in gi:
                continue
            self.d["gorulen"]["ilan"].append(i)
            if ilk or x.get("x"):
                continue  # ilk çalıştırmada eskileri atma; iptal ilanlarını atma
            g["akademik" if x.get("c") == "akademik" else "kamu"] += 1
            if x.get("c") == "akademik" and self.a["akademik"] != "hepsi":
                continue
            self.d["kuyruk"].append({"tur": "ilan", "metin": ilan_metni(x, reklam=self.reklam())})
            yeni += 1
        for x in sorted(haberler, key=lambda x: x.get("d", "")):
            i = x.get("u") or x.get("t")
            if i in gh:
                continue
            self.d["gorulen"]["haber"].append(i)
            if ilk:
                continue
            g["haber"] += 1
            self.d["kuyruk"].append({"tur": "haber", "metin": haber_metni(x, reklam=self.reklam())})
            yeni += 1
        if ilk:
            log(f"İlk çalıştırma: {len(ilanlar)} ilan ve {len(haberler)} haber görüldü olarak işaretlendi (kanala atılmadı).")
        elif yeni:
            log(f"{yeni} yeni gönderi kuyruğa eklendi (kuyruk {len(self.d['kuyruk'])}).")
        self.kaydet()

    def sessiz_mi(self):
        b, s = self.a["sessiz"]
        h = simdi().hour
        return (b <= h or h < s) if b > s else (b <= h < s)

    def kanal_gonder(self):
        if self.d["duraklat"] or not self.d["kuyruk"]:
            return
        g = self.bugun()
        serbest = not self.sessiz_mi() and g["gonderilen"] < self.a["gunluk_sinir"]
        # Sessiz saatte / sınır dolunca yalnızca elle istenen (zorla) gönderiler gider; normal olanlar sırada bekler ama önünü tıkamaz
        sira = 0 if serbest else next((i for i, x in enumerate(self.d["kuyruk"]) if x.get("zorla")), None)
        if sira is None:
            return None
        zorla = self.d["kuyruk"][sira].get("zorla")
        if time.time() - self.d["son_kanal"] < (60 if zorla else self.a["aralik_dk"] * 60):
            return None
        m = self.d["kuyruk"].pop(sira)
        try:
            self.tg.gonder(self.a["kanal"], m["metin"], self.dugme())
            g["gonderilen"] += 1
            self.d["son_kanal"] = time.time()
            log("Kanala gönderildi:", m["tur"], "| kalan kuyruk", len(self.d["kuyruk"]))
            self.kaydet()
            return m
        except RuntimeError as ex:
            log("Gönderilemedi:", ex)
            if "chat not found" in str(ex) or "not enough rights" in str(ex) or "bot is not a member" in str(ex):
                self.d["kuyruk"].insert(sira, m)
                self.d["duraklat"] = True
                self.sahibe(f"⚠️ Kanala yazamıyorum: {e(ex)}\nBotu kanala yönetici olarak ekleyip /devam yaz.")
        self.kaydet()
        return None

    def paylasim_metni(self):
        """WhatsApp/Facebook'a yapıştırmaya hazır düz metin: bugünün ya da yaklaşan ilanlar + kanal linki."""
        il = [x for x in self.son_veri["ilan"] if not x.get("x") and x.get("c") == "kamu"]
        bugun = simdi().date().isoformat()
        yeni = sorted([x for x in il if x.get("d") == bugun], key=lambda x: x.get("sb") or "9999")
        if len(yeni) < 3:
            yeni += sorted([x for x in il if x.get("d", "") >= (simdi().date() - timedelta(days=3)).isoformat() and x not in yeni], key=lambda x: x.get("d", ""), reverse=True)
        yak = sorted([x for x in il if x.get("sb") and 0 <= (kalan_gun(x["sb"]) or -1) <= 5 and x not in yeni[:6]], key=lambda x: x["sb"])
        kanal = str(self.a["kanal"]).lstrip("@")
        sat = [f"🏛️ GÜNCEL KAMU PERSONEL ALIMLARI ({tarih_tr(bugun)})", ""]
        for x in yeni[:6]:
            sat.append("• " + str(x.get("t"))[:100] + (f" – son başvuru {tarih_tr(x['sb'])}" if x.get("sb") else ""))
        if yak[:4]:
            sat += ["", "⏳ Son başvurusu yaklaşanlar:"]
            for x in yak[:4]:
                k = kalan_gun(x["sb"])
                sat.append("• " + str(x.get("t"))[:90] + (" – BUGÜN SON GÜN" if k == 0 else f" – {k} gün kaldı"))
        sat += ["", "Tüm kamu ilanları ve son başvuru tarihleri her gün ücretsiz Telegram kanalımızda 👇", f"t.me/{kanal}", "", "#kpss #memuralımı #kamuilanları"]
        return "\n".join(sat)

    def paylasim_gonder(self):
        if not self.sahip_id():
            return
        try:
            self.tg.cagir("sendMessage", {"chat_id": self.sahip_id(), "text": "📋 Bugünün paylaşım metni hazır. Aşağıdaki mesaja uzun bas → Kopyala, sonra WhatsApp durumuna, gruplara ya da Facebook'a yapıştır."})
            self.tg.cagir("sendMessage", {"chat_id": self.sahip_id(), "text": self.paylasim_metni(), "link_preview_options": {"is_disabled": True}})
        except Exception as ex:
            log("Paylaşım metni gönderilemedi:", ex)

    def ozet(self):
        if self.a["ozet_saat"] < 0 or self.d["duraklat"]:
            return
        g = self.bugun()
        h = simdi().hour
        if g["ozet"] or (not (self.a["ozet_saat"] <= h < 23) if GH else h != self.a["ozet_saat"]):
            return
        g["ozet"] = True
        ilanlar = self.son_veri["ilan"]
        yak = sorted([x for x in ilanlar if x.get("sb") and not x.get("x") and 0 <= (kalan_gun(x["sb"]) or -1) <= 3], key=lambda x: x["sb"])
        if not (g["kamu"] or g["akademik"] or yak):
            self.kaydet()
            return
        m = [f"🌙 <b>{tarih_tr(simdi().date().isoformat())} memur alımları özeti</b>", ""]
        if g["kamu"] or g["akademik"]:
            m.append(f"Bugün <b>{g['kamu']}</b> kamu, <b>{g['akademik']}</b> akademik personel ilanı yayımlandı.")
        if yak:
            m += ["", "⏳ <b>Son başvurusu yaklaşanlar</b>"]
            for x in yak[:8]:
                k = kalan_gun(x["sb"])
                m.append(f'• <a href="{e(x["u"])}">{e(x["t"])[:90]}</a> — ' + ("<b>bugün son gün</b>" if k == 0 else f"{k} gün"))
        if self.reklam():
            m += ["", "📲 Tüm ilanlar, il/meslek filtresi ve son gün hatırlatması: <b>Memur Rehberi</b>"]
        self.d["kuyruk"].insert(0, {"tur": "ozet", "metin": "\n".join(m)})
        self.paylasim_gonder()
        self.d["son_kanal"] = 0
        self.kaydet()

    # -- özel sohbet komutları
    def _anahtar(self):
        import hashlib
        return int(hashlib.sha256(("sahip:" + self.a["token"]).encode()).hexdigest()[:15], 16)

    def sahip_id(self):
        if GH:
            x = self.d.get("sahip_x")
            return (int(x) ^ self._anahtar()) if x else 0
        return self.a.get("sahip") or 0

    def sahip_yaz(self, kim):
        if GH:
            self.d["sahip_x"] = str(int(kim) ^ self._anahtar()); self.kaydet()
        else:
            self.a["sahip"] = kim
            a = oku(AYAR, {}); a["sahip"] = kim; yaz(AYAR, a)

    def sahibe(self, metin):
        if self.sahip_id():
            try:
                self.tg.gonder(self.sahip_id(), metin)
            except Exception as ex:
                log("Sahibe yazılamadı:", ex)

    def komut(self, msj):
        sohbet = msj["chat"]["id"]
        if msj["chat"].get("type") != "private":
            return
        kim = msj.get("from", {}).get("id")
        t = (msj.get("text") or "").strip().split("@")[0].split()[0].lower() if msj.get("text") else ""
        sahip = bool(kim) and kim == self.sahip_id()
        il = [x for x in self.son_veri["ilan"] if not x.get("x")]
        if t == "/sahip" and not self.sahip_id():
            self.sahip_yaz(kim)
            return self.tg.gonder(sohbet, "✅ Artık botun sahibisin. Komutlar: /durum /paylas /test /kanal /link /tanitim /yayinla /dur /devam")
        if t in ("/start", "/yardim", "/help"):
            return self.tg.gonder(sohbet, "👋 Merhaba! Kamu personel alımlarını ve memur gündemini takip ediyorum.\n\n/ilanlar – son kamu ilanları\n/yaklasan – son başvurusu yaklaşanlar\n/haberler – memur gündemi" + ("\n/uygulama – Memur Rehberi uygulaması" if self.reklam() else ""), self.dugme())
        if t == "/ilanlar":
            ls = sorted([x for x in il if x.get("c") == "kamu"], key=lambda x: x.get("d", ""), reverse=True)[:8]
            return self.tg.gonder(sohbet, "🏛️ <b>Son kamu ilanları</b>\n\n" + "\n".join(f'• <a href="{e(x["u"])}">{e(x["t"])[:100]}</a> ({tarih_tr(x["d"])})' for x in ls) if ls else "Şu an ilan yok.", self.dugme())
        if t == "/yaklasan":
            ls = sorted([x for x in il if x.get("sb") and (kalan_gun(x["sb"]) or -1) >= 0], key=lambda x: x["sb"])[:10]
            return self.tg.gonder(sohbet, "⏳ <b>Son başvurusu yaklaşanlar</b>\n\n" + "\n".join(f'• <a href="{e(x["u"])}">{e(x["t"])[:90]}</a> — {tarih_tr(x["sb"])}' for x in ls) if ls else "Yaklaşan son başvuru yok.", self.dugme())
        if t == "/haberler":
            ls = self.son_veri["haber"][:8]
            return self.tg.gonder(sohbet, "📰 <b>Memur gündemi</b>\n\n" + "\n".join(f'• <a href="{e(x["u"])}">{e(x["t"])}</a>' for x in ls) if ls else "Şu an haber yok.", self.dugme())
        if t == "/uygulama" and self.reklam():
            return self.tg.gonder(sohbet, "📲 <b>Memur Rehberi</b>: mevzuat, maaş ve izin hesaplama, kamu ilanları ve son başvuru hatırlatmaları tek uygulamada.", self.dugme())
        if sahip and t == "/durum":
            g = self.bugun()
            return self.tg.gonder(sohbet, f"🤖 Çalışıyor{' (DURAKLATILDI)' if self.d['duraklat'] else ''}\nKanal: {e(self.a['kanal']) if ':' not in str(self.a['kanal']) else '⚠️ hatalı (/kanal @kanaladi ile düzelt)'}\nKuyruk: {len(self.d['kuyruk'])}\nBugün gönderilen: {g['gonderilen']}/{self.a['gunluk_sinir']}\nBugün ilan: {g['kamu']} kamu, {g['akademik']} akademik · haber {g['haber']}\nSessiz saatler: {self.a['sessiz'][0]}:00–{self.a['sessiz'][1]}:00{' (şu an sessiz)' if self.sessiz_mi() else ''}\nSon hata sayısı: {self.hata_say}" + (f"\nÇalışma yeri: GitHub (son çalışma {self.d.get('son_calisma', '–')[11:16]}, 15–60 dk'da bir)" if GH else ""))
        if sahip and t == "/dur":
            self.d["duraklat"] = True; self.kaydet()
            return self.tg.gonder(sohbet, "⏸️ Kanala gönderim durduruldu. /devam ile sürdür.")
        if sahip and t == "/devam":
            self.d["duraklat"] = False; self.kaydet()
            return self.tg.gonder(sohbet, "▶️ Kanala gönderim sürüyor.")
        if sahip and t == "/tanitim":
            m = (("📢 <b>Memur Alımları – Güncel İlanlar</b>\n\n"
                 "Bu kanalda her gün:\n"
                 "🏛️ Yeni kamu personel alım ilanları (ilan.gov.tr)\n"
                 "⏳ Son başvurusu yaklaşan ilanlar\n"
                 "📰 Memur maaş, mevzuat ve gündem haberleri\n"
                 "🌙 Her akşam günün özeti\n\n"
                 "Bildirimleri açmayı unutma 🔔\n\n")
                 + ("📲 Mevzuat, maaş tahmini, izin hesabı, dilekçe taslakları ve son başvuru hatırlatıcıları için <b>Memur Rehberi</b> uygulamasını indir." if self.reklam() else
                    "Kanalı arkadaşlarınla paylaş, kimse ilan kaçırmasın 🤝"))
            self.d["kuyruk"].insert(0, {"tur": "tanitim", "metin": m, "zorla": True}); self.d["son_kanal"] = 0; self.kaydet()
            return self.tg.gonder(sohbet, "Tanıtım mesajı kanala gönderiliyor" + (" (birkaç dakika içinde)" if GH else "") + ". Kanalda mesaja uzun basıp <b>Sabitle</b> de.")
        if sahip and t == "/yayinla":
            try:
                n = max(1, min(40, int((msj.get("text") or "").split()[1])))
            except Exception:
                n = 15
            bugun = simdi().date().isoformat()
            aday = [x for x in il if x.get("c") == "kamu" and ((x.get("sb") or "") >= bugun or (not x.get("sb") and x.get("d", "") >= (simdi().date() - timedelta(days=10)).isoformat()))]
            aday.sort(key=lambda x: (x.get("sb") or "9999", x.get("d", "")))
            for x in aday[:n]:
                self.d["kuyruk"].append({"tur": "ilan", "metin": ilan_metni(x, "📌 <b>Başvurusu devam eden ilan</b>", self.reklam()), "zorla": True})
            self.kaydet()
            return self.tg.gonder(sohbet, f"📤 Başvurusu açık {min(n, len(aday))} kamu ilanı (toplam {len(aday)}) kuyruğa eklendi; " + ("botun bir sonraki çalışmalarında kanala gidecek (her çalışmada 10 ilan)." if GH else "dakikada bir kanala gidecek.") + " Daha fazlası için: /yayinla 30")
        if sahip and t == "/paylas":
            return self.paylasim_gonder()
        if sahip and t == "/kanal":
            parca = (msj.get("text") or "").split()
            if len(parca) < 2:
                return self.tg.gonder(sohbet, "Kullanım: /kanal @kanaladi")
            k = parca[1].strip()
            k = k if k.startswith("@") or k.lstrip("-").isdigit() else "@" + k.replace("https://t.me/", "").replace("t.me/", "")
            if ":" in k or len(k) > 40:
                return self.tg.gonder(sohbet, "Bu bir kanal adına benzemiyor. Örnek: /kanal @MemurRehberi")
            try:
                self.tg.gonder(k, "✅ Bot bu kanala bağlandı.", self.dugme())
            except Exception as ex:
                return self.tg.gonder(sohbet, f"{e(k)} kanalına yazılamadı: {e(ex)}\nKullanıcı adını ve botun yönetici olduğunu kontrol et.")
            self.a["kanal"] = k
            a = oku(AYAR, {}); a["kanal"] = k; yaz(AYAR, a)
            self.d["duraklat"] = False; self.kaydet()
            return self.tg.gonder(sohbet, f"✅ Kanal {e(k)} olarak ayarlandı, gönderim sürüyor.")
        if sahip and t == "/link":
            parca = (msj.get("text") or "").split()
            if len(parca) < 2 or not (parca[1].startswith("https://") or parca[1] == "kapat"):
                return self.tg.gonder(sohbet, f"Şu anki link: {e(self.a['uygulama_url']) or 'yok (düğme kapalı)'}\nEklemek için: /link https://...\nKaldırmak için: /link kapat")
            yeni = "" if parca[1] == "kapat" else parca[1]
            self.a["uygulama_url"] = yeni
            a = oku(AYAR, {}); a["uygulama_url"] = yeni; yaz(AYAR, a)
            return self.tg.gonder(sohbet, "✅ Uygulama düğmesi eklendi." if yeni else "✅ Uygulama düğmesi ve tanıtım satırları kaldırıldı.", self.dugme())
        if sahip and t == "/test":
            try:
                self.tg.gonder(self.a["kanal"], "✅ Test mesajı: bot bu kanala yazabiliyor.", self.dugme())
                return self.tg.gonder(sohbet, "Kanala test mesajı gönderildi.")
            except Exception as ex:
                return self.tg.gonder(sohbet, f"Kanala yazılamadı: {e(ex)}")
        return self.tg.gonder(sohbet, "Komutları görmek için /start yaz.")

    def guncellemeler(self, bekle):
        try:
            gs = self.tg.cagir("getUpdates", {"offset": self.d["offset"], "timeout": bekle, "allowed_updates": ["message"]}, zaman=bekle)
        except Exception as ex:
            log("Güncelleme alınamadı:", ex)
            time.sleep(10)
            return
        for u in gs:
            self.d["offset"] = u["update_id"] + 1
            if "message" in u:
                try:
                    self.komut(u["message"])
                except Exception as ex:
                    log("Komut hatası:", ex)
        if gs:
            self.kaydet()

    def tek(self):
        """GitHub Actions: komutları yanıtla, veriyi kontrol et, kuyruktan sınırlı sayıda gönder, çık."""
        try:
            self.kontrol()
        except Exception as ex:
            log("Veri okunamadı:", ex)
        self.guncellemeler(0)
        self.ozet()
        normal = zorla = 0
        for _ in range(30):
            self.d["son_kanal"] = 0
            m = self.kanal_gonder()
            if not m:
                break
            if m.get("zorla"):
                zorla += 1
            else:
                normal += 1
            if zorla >= 10 or normal >= 4:
                break
            time.sleep(20 if not m.get("zorla") else 4)
        self.guncellemeler(0)
        self.d["son_calisma"] = simdi().isoformat(timespec="minutes")
        self.kaydet()
        log(f"Bitti: {normal} yeni + {zorla} elle gönderim, kuyrukta {len(self.d['kuyruk'])}")

    def calis(self):
        me = self.tg.cagir("getMe")
        log(f"Bot başladı: @{me.get('username')} → {self.a['kanal']}")
        self.sahibe("🟢 Bot başladı.")
        while CALISIYOR:
            try:
                if time.time() - self.son_kontrol > self.a["kontrol_dk"] * 60:
                    self.son_kontrol = time.time()
                    self.kontrol()
                self.ozet()
                self.kanal_gonder()
                self.hata_say = 0
            except Exception as ex:
                self.hata_say += 1
                log("Hata:", ex)
                if self.hata_say in (5, 50):
                    self.sahibe(f"⚠️ Üst üste {self.hata_say} hata: {e(ex)}")
                time.sleep(min(300, 10 * self.hata_say))
            self.guncellemeler(25)
        self.kaydet()
        log("Bot durdu.")


def kurulum():
    a = oku(AYAR, {})
    print("Memur Rehberi Telegram botu kurulumu\n")
    import getpass
    tok = getpass.getpass(f"BotFather'dan aldığın token (yazarken görünmez){' — boş bırak: değişmesin' if a.get('token') else ''}: ").strip()
    import re
    bul = re.search(r"\d{6,12}:[A-Za-z0-9_-]{30,}", tok or "")
    if tok and not bul:
        print("⚠️ Bunda token bulamadım. BotFather'daki token'ın üstüne dokunup sadece onu kopyala ve tekrar dene.")
        return
    if bul:
        a["token"] = bul.group(0)
    kan = input(f"Kanal kullanıcı adı, ör. @memuralimlari{' [' + a['kanal'] + ']' if a.get('kanal') else ''}: ").strip()
    if kan and (":" in kan or len(kan) > 40):
        print("⚠️ Bu kanal adına benzemiyor, kanal değiştirilmedi.")
        kan = ""
    if kan:
        a["kanal"] = kan if kan.startswith("@") or kan.lstrip("-").isdigit() else "@" + kan
    url = input("Uygulama linki (yoksa boş bırak): ").strip()
    if url:
        a["uygulama_url"] = url
    yaz(AYAR, {**VARSAYILAN, **a})
    try:
        os.chmod(AYAR, 0o600)
    except Exception:
        pass
    try:
        me = TG(a["token"]).cagir("getMe")
        print(f"\n✅ Token doğru: @{me['username']}")
        print(f"Şimdi Telegram'da @{me['username']} botuna özelden /sahip yaz (botun sahibi sen olursun).")
        print(f"Sonra botu {a['kanal']} kanalına YÖNETİCİ olarak ekle ve bota /test yaz.")
    except Exception as ex:
        print("\n⚠️ Token denenemedi:", ex)


def durdur(*_):
    global CALISIYOR
    CALISIYOR = False


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "tek":
        if not ayar_yukle().get("token"):
            print("TELEGRAM_TOKEN gizli ayarı yok; atlanıyor.")
            sys.exit(0)
        Bot().tek()
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "kurulum":
        kurulum()
        sys.exit(0)
    signal.signal(signal.SIGTERM, durdur)
    signal.signal(signal.SIGINT, durdur)
    try:
        Bot().calis()
    except SystemExit:
        raise
    except Exception:
        log("Ölümcül hata:\n" + traceback.format_exc())
        sys.exit(1)
