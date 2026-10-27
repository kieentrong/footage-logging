#!/usr/bin/env bash
# Footage Logging — nhấp đúp trên Mac (Apple Silicon) để chạy phần AI local cho một dự án:
#   1) cài mlx-whisper + mlx-vlm (lần đầu, ~6–7GB model), 2) bóc băng large-v3-turbo, 3) AI nhìn ảnh mô tả từng cảnh.
# Đóng cửa sổ giữa chừng cũng được — nhấp đúp lại sẽ làm tiếp chỗ dở.
T="$(cd "$(dirname "$0")" && pwd)"
OUT="${FL_OUT:-_SOCIAL}"
MEM="$HOME/.footage-logging/last_project"; mkdir -p "$(dirname "$MEM")"
P="$1"
if [ -z "$P" ]; then
  LAST="$(cat "$MEM" 2>/dev/null)"
  P="$(osascript -e "POSIX path of (choose folder with prompt \"Chọn folder dự án cần log\"${LAST:+ default location POSIX file \"$LAST\"})" 2>/dev/null)"
fi
P="${P%/}"; [ -d "$P" ] || { echo "Chưa chọn folder dự án."; read -n1; exit 1; }
echo "$P" > "$MEM"
cd "$T" || exit 1
echo "Dự án: $P"
echo "== 1/3 Cài đặt"; bash mac_local.sh install || { echo "Cài lỗi — chụp màn hình gửi Claude"; read -n1; exit 1; }
echo "== 2/3 Bóc băng (mlx-whisper large-v3-turbo)"; bash mac_local.sh whisper "$P"
echo "== 3/3 AI mô tả từng cảnh"
for i in $(seq 1 180); do
  [ -f "$P/$OUT/analysis/shots/_DONE" ] && break
  [ $i = 1 ] && echo "   chờ Claude đo xong các cảnh (shots.py)… mô tả trước những cảnh đã đo"
  bash mac_local.sh describe "$P" >/dev/null 2>&1 || true
  sleep 60
done
bash mac_local.sh describe "$P"
echo; echo "XONG. Báo Claude là đã chạy xong."; read -n1
