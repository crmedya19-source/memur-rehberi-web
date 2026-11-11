#!/data/data/com.termux/files/usr/bin/bash
# bot.py'nin en yeni sürümünü indirir, hatasızsa değiştirir ve botu yeniden başlatır.
cd "$(dirname "$0")"
curl -fsSL https://raw.githubusercontent.com/crmedya19-source/memur-rehberi-web/main/telegram/bot.py -o bot.py.yeni || { echo "İndirilemedi"; exit 1; }
curl -fsSL https://raw.githubusercontent.com/crmedya19-source/memur-rehberi-web/main/telegram/calistir.sh -o calistir.sh.yeni && bash -n calistir.sh.yeni && mv calistir.sh.yeni calistir.sh && chmod +x calistir.sh
python -m py_compile bot.py.yeni && mv bot.py.yeni bot.py && echo "✅ Güncellendi" || { echo "Yeni sürümde hata var, eski sürüm kaldı"; rm -f bot.py.yeni; exit 1; }
pkill -f "python bot.py" && echo "Bot yeniden başlatılıyor…"
