#!/usr/bin/env bash
# Nhấp đúp để chạy phần AI local trên Mac cho dự án Tea and Tales:
#   1) cài mlx-whisper + mlx-vlm (lần đầu), 2) bóc băng large-v3-turbo, 3) AI nhìn ảnh mô tả từng cảnh.
# Có thể đóng cửa sổ giữa chừng, nhấp đúp lại sẽ làm tiếp chỗ dở.
T="/Volumes/NEX4/Tai Nguyen/TroLySocial/tools"
P="${1:-/Volumes/NEX4/NEX 2026/26 T8/Tea and Tales}"   # đổi sang folder dự án cần log
cd "$T" || exit 1
echo "== 1/3 Cài đặt"; bash mac_local.sh install || { echo "Cài lỗi — chụp màn hình gửi Claude"; read -n1; exit 1; }
echo "== 2/3 Bóc băng (mlx-whisper large-v3-turbo)"; bash mac_local.sh whisper "$P"
echo "== 3/3 AI mô tả từng cảnh"
for i in $(seq 1 180); do
  [ -f "$P/_SOCIAL/analysis/shots/_DONE" ] && break
  [ $i = 1 ] && echo "   chờ Claude đo xong các cảnh trong máy ảo…"
  bash mac_local.sh describe "$P" --only POV >/dev/null 2>&1 || true
  sleep 60
done
bash mac_local.sh describe "$P"
echo; echo "XONG. Báo Claude là đã chạy xong."; read -n1
