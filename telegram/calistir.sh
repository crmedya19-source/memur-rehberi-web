#!/data/data/com.termux/files/usr/bin/bash
# Botu çalıştırır, çökerse 15 sn sonra yeniden başlatır. Aynı anda iki kopya çalışmaz.
cd "$(dirname "$0")"
PID=bot.pid
# Kayıtlı pid gerçekten bu betiğe aitse çık (yeniden başlatmadan sonra pid başka bir sürece verilmiş olabilir)
if [ -f $PID ] && grep -q calistir "/proc/$(cat $PID)/cmdline" 2>/dev/null; then echo "Bot zaten çalışıyor (pid $(cat $PID))."; exit 0; fi
echo $$ > $PID
command -v termux-wake-lock >/dev/null && termux-wake-lock
trap 'rm -f $PID; kill $C 2>/dev/null; exit 0' INT TERM
while true; do
  python bot.py & C=$!; wait $C
  echo "$(date '+%d.%m %H:%M:%S') bot kapandı, 15 sn sonra yeniden başlıyor" >> bot.log
  sleep 15
done
