#!/usr/bin/env bash
# Footage Logging — phần chạy trên Mac Apple Silicon (AI local, không tốn lượt Claude).
#   bash mac_local.sh install                       # cài mlx-whisper + mlx-vlm vào ~/.tls_mlx (một lần)
#   bash mac_local.sh whisper  "<dự án>" [--only POV]   # bóc băng large-v3-turbo (thay Whisper small)
#   bash mac_local.sh describe "<dự án>" [--only POV] [--min-interest 4]   # AI nhìn ảnh mô tả từng cảnh
#   bash mac_local.sh all      "<dự án>"            # whisper rồi describe
# Chạy SAU khi Claude đã chạy analyze.py + shots.py trong máy ảo (cần _SOCIAL/analysis/shots/).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="$HOME/.tls_mlx"
cmd="$1"; shift || true

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "Script này cần Mac chip Apple (M1–M4)."; exit 1
fi

install() {
  bash "$HERE/mac_whisper.sh" --install
  if ! "$VENV/bin/python" -c "import mlx_vlm" 2>/dev/null; then
    echo "→ Cài mlx-vlm…"
    "$VENV/bin/pip" install -q --upgrade mlx-vlm torch torchvision 2>/dev/null || "$VENV/bin/pip" install -q --upgrade mlx-vlm
  fi
  echo "OK: $(sysctl -n hw.memsize | awk '{printf "%.0f", $1/1073741824}') GB RAM — $( "$VENV/bin/python" -c 'import mlx_vlm;print("mlx-vlm", getattr(mlx_vlm, "__version__", "?"))')"
}

case "$cmd" in
  install) install ;;
  whisper) bash "$HERE/mac_whisper.sh" "$@" ;;
  describe) install >/dev/null; "$VENV/bin/python" "$HERE/mac_describe.py" "$@" ;;
  all) P="$1"; shift || true; bash "$HERE/mac_whisper.sh" "$P" "$@"; install >/dev/null; "$VENV/bin/python" "$HERE/mac_describe.py" "$P" "$@" ;;
  *) sed -n 2,7p "$0" ;;
esac
