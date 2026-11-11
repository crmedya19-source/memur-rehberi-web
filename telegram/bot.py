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
AYAR = os.path.join(KLASOR, "ayar.json")
DURUM = os.path.join(KLASOR, "durum.json")
KAYIT = os.path.join(KLASOR, "bot.log")
TR = timezone(timedelta(hours=3))
VARSAYILAN = {
    "token": "", "kanal": "", "sahip": 0,
    "uygulama_url": "https://play.google.com/store/apps/details?id=com.memurmevzuat.rehber",
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


def ayar_yukle():
    a = dict(VARSAYILAN)
    a.update(oku(AYAR, {}))
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
        if g.strip("),") in kisalt or g.rstrip(",") == "t.c.":
            return on + "".join(ust(c) for c in g)
        if j and not on and g in kucuk:
            return w
        return on + ust(g[0]) + g[1:]
    return " ".join(kelime(j, w) for j, w in enumerate(s.split(" ")))


def ilan_metni(x):
    bas = "🎓 <b>Akademik personel alımı</b>" if x.get("c") == "akademik" else "🏛️ <b>Yeni kamu personel alımı</b>"
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
    m += ["", f'🔗 <a href="{e(x.get("u"))}">İlanın tamamı (ilan.gov.tr)</a>', "", "📲 Başvuru tarihlerini kaçırmamak için hatırlatmalı takip: <b>Memur Rehberi</b> uygulaması"]
    return "\n".join(m)


def haber_metni(x):
    m = [f"📰 <b>{e(x.get('t'))}</b>"]
    if x.get("s"):
        m += ["", e(x["s"])[:900]]
    m += ["", f'🔗 <a href="{e(x.get("u"))}">Haberin devamı</a>' + (f" · {e(x.get('src'))}" if x.get("src") else ""), "", "📲 Memur gündemi, mevzuat ve maaş hesaplama: <b>Memur Rehberi</b>"]
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

    def dugme(self):
        return [("📲 Memur Rehberi'ni indir", self.a["uygulama_url"])]

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
            self.d["kuyruk"].append({"tur": "ilan", "metin": ilan_metni(x)})
            yeni += 1
        for x in sorted(haberler, key=lambda x: x.get("d", "")):
            i = x.get("u") or x.get("t")
            if i in gh:
                continue
            self.d["gorulen"]["haber"].append(i)
            if ilk:
                continue
            g["haber"] += 1
            self.d["kuyruk"].append({"tur": "haber", "metin": haber_metni(x)})
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
        if self.d["duraklat"] or not self.d["kuyruk"] or self.sessiz_mi():
            return
        g = self.bugun()
        if g["gonderilen"] >= self.a["gunluk_sinir"]:
            return
        if time.time() - self.d["son_kanal"] < self.a["aralik_dk"] * 60:
            return
        m = self.d["kuyruk"].pop(0)
        try:
            self.tg.gonder(self.a["kanal"], m["metin"], self.dugme())
            g["gonderilen"] += 1
            self.d["son_kanal"] = time.time()
            log("Kanala gönderildi:", m["tur"], "| kalan kuyruk", len(self.d["kuyruk"]))
        except RuntimeError as ex:
            log("Gönderilemedi:", ex)
            if "chat not found" in str(ex) or "not enough rights" in str(ex) or "bot is not a member" in str(ex):
                self.d["kuyruk"].insert(0, m)
                self.d["duraklat"] = True
                self.sahibe(f"⚠️ Kanala yazamıyorum: {e(ex)}\nBotu kanala yönetici olarak ekleyip /devam yaz.")
        self.kaydet()

    def ozet(self):
        if self.a["ozet_saat"] < 0 or self.d["duraklat"]:
            return
        g = self.bugun()
        if g["ozet"] or simdi().hour != self.a["ozet_saat"]:
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
        m += ["", "📲 Tüm ilanlar, il/meslek filtresi ve son gün hatırlatması: <b>Memur Rehberi</b>"]
        self.d["kuyruk"].insert(0, {"tur": "ozet", "metin": "\n".join(m)})
        self.d["son_kanal"] = 0
        self.kaydet()

    # -- özel sohbet komutları
    def sahibe(self, metin):
        if self.a["sahip"]:
            try:
                self.tg.gonder(self.a["sahip"], metin)
            except Exception as ex:
                log("Sahibe yazılamadı:", ex)

    def komut(self, msj):
        sohbet = msj["chat"]["id"]
        if msj["chat"].get("type") != "private":
            return
        kim = msj.get("from", {}).get("id")
        t = (msj.get("text") or "").strip().split("@")[0].split()[0].lower() if msj.get("text") else ""
        sahip = kim == self.a["sahip"]
        il = [x for x in self.son_veri["ilan"] if not x.get("x")]
        if t == "/sahip" and not self.a["sahip"]:
            self.a["sahip"] = kim
            a = oku(AYAR, {}); a["sahip"] = kim; yaz(AYAR, a)
            return self.tg.gonder(sohbet, "✅ Artık botun sahibisin. Komutlar: /durum /test /dur /devam")
        if t in ("/start", "/yardim", "/help"):
            return self.tg.gonder(sohbet, "👋 Merhaba! Kamu personel alımlarını ve memur gündemini takip ediyorum.\n\n/ilanlar – son kamu ilanları\n/yaklasan – son başvurusu yaklaşanlar\n/haberler – memur gündemi\n/uygulama – Memur Rehberi uygulaması", self.dugme())
        if t == "/ilanlar":
            ls = sorted([x for x in il if x.get("c") == "kamu"], key=lambda x: x.get("d", ""), reverse=True)[:8]
            return self.tg.gonder(sohbet, "🏛️ <b>Son kamu ilanları</b>\n\n" + "\n".join(f'• <a href="{e(x["u"])}">{e(x["t"])[:100]}</a> ({tarih_tr(x["d"])})' for x in ls) if ls else "Şu an ilan yok.", self.dugme())
        if t == "/yaklasan":
            ls = sorted([x for x in il if x.get("sb") and (kalan_gun(x["sb"]) or -1) >= 0], key=lambda x: x["sb"])[:10]
            return self.tg.gonder(sohbet, "⏳ <b>Son başvurusu yaklaşanlar</b>\n\n" + "\n".join(f'• <a href="{e(x["u"])}">{e(x["t"])[:90]}</a> — {tarih_tr(x["sb"])}' for x in ls) if ls else "Yaklaşan son başvuru yok.", self.dugme())
        if t == "/haberler":
            ls = self.son_veri["haber"][:8]
            return self.tg.gonder(sohbet, "📰 <b>Memur gündemi</b>\n\n" + "\n".join(f'• <a href="{e(x["u"])}">{e(x["t"])}</a>' for x in ls) if ls else "Şu an haber yok.", self.dugme())
        if t == "/uygulama":
            return self.tg.gonder(sohbet, "📲 <b>Memur Rehberi</b>: mevzuat, maaş ve izin hesaplama, kamu ilanları ve son başvuru hatırlatmaları tek uygulamada.", self.dugme())
        if sahip and t == "/durum":
            g = self.bugun()
            return self.tg.gonder(sohbet, f"🤖 Çalışıyor{' (DURAKLATILDI)' if self.d['duraklat'] else ''}\nKanal: {e(self.a['kanal'])}\nKuyruk: {len(self.d['kuyruk'])}\nBugün gönderilen: {g['gonderilen']}/{self.a['gunluk_sinir']}\nBugün ilan: {g['kamu']} kamu, {g['akademik']} akademik · haber {g['haber']}\nSessiz saatler: {self.a['sessiz'][0]}:00–{self.a['sessiz'][1]}:00{' (şu an sessiz)' if self.sessiz_mi() else ''}\nSon hata sayısı: {self.hata_say}")
        if sahip and t == "/dur":
            self.d["duraklat"] = True; self.kaydet()
            return self.tg.gonder(sohbet, "⏸️ Kanala gönderim durduruldu. /devam ile sürdür.")
        if sahip and t == "/devam":
            self.d["duraklat"] = False; self.kaydet()
            return self.tg.gonder(sohbet, "▶️ Kanala gönderim sürüyor.")
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
    if tok:
        a["token"] = tok
    kan = input(f"Kanal kullanıcı adı, ör. @memuralimlari{' [' + a['kanal'] + ']' if a.get('kanal') else ''}: ").strip()
    if kan:
        a["kanal"] = kan if kan.startswith("@") or kan.lstrip("-").isdigit() else "@" + kan
    url = input("Uygulama linki (boş bırak: Play Store linki): ").strip()
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
