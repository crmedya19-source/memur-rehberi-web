#!/data/data/com.termux/files/usr/bin/bash
# Memur Rehberi Telegram botu – Termux kurulumu
set -e
KOK=https://raw.githubusercontent.com/crmedya19-source/memur-rehberi-web/main/telegram
echo "📦 Paketler kuruluyor…"
O="-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"
apt-get update -y || true
apt-get -y $O upgrade || true
apt-get -y $O install python curl
mkdir -p ~/memurbot && cd ~/memurbot
curl -fsSL $KOK/bot.py -o bot.py
curl -fsSL $KOK/calistir.sh -o calistir.sh && chmod +x calistir.sh
curl -fsSL $KOK/guncelle.sh -o guncelle.sh && chmod +x guncelle.sh
# Telefon açılınca otomatik başlat (Termux:Boot uygulaması gerekli)
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/memurbot <<'B'
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
cd ~/memurbot && nohup ./calistir.sh >/dev/null 2>&1 &
B
chmod +x ~/.termux/boot/memurbot
echo "✅ Dosyalar hazır: ~/memurbot"
python bot.py kurulum
echo ""
echo "Botu başlatmak için:  ~/memurbot/calistir.sh &"
echo "Kayıtları izlemek için: tail -f ~/memurbot/bot.log"
