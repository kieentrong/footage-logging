#!/usr/bin/env bash
# Footage Logging — cài & chạy mlx-whisper (large-v3-turbo) trên Mac Apple Silicon.
# Lần đầu: tự cài vào ~/.tls_mlx (không đụng Python hệ thống), tải model ~1.6GB.
# Dùng:  bash tools/mac_whisper.sh "<folder dự án>" [--only POV] [--force]
# Chỉ cài, không chạy:  bash ".../mac_whisper.sh" --install
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="$HOME/.tls_mlx"

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "Script này cần Mac chip Apple (M1/M2/M3/M4)."; exit 1
fi

PY=""
for c in python3.12 python3.11 python3.10 python3; do
  if command -v $c >/dev/null 2>&1 && $c -c 'import sys; exit(0 if sys.version_info >= (3,9) else 1)' 2>/dev/null; then PY=$(command -v $c); break; fi
done
if [ -z "$PY" ]; then
  echo "Chưa có Python 3.9+. Chạy:  xcode-select --install   (hoặc: brew install python) rồi chạy lại."; exit 1
fi

if [ ! -x "$VENV/bin/python" ]; then
  echo "→ Tạo môi trường $VENV ($($PY --version))"
  "$PY" -m venv "$VENV"
fi
if ! "$VENV/bin/python" -c "import mlx_whisper, imageio_ffmpeg" 2>/dev/null; then
  echo "→ Cài mlx-whisper (vài phút lần đầu)…"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q mlx-whisper imageio-ffmpeg
fi
# mlx-whisper gọi lệnh `ffmpeg` để đọc audio — nếu máy chưa có, dùng bản ffmpeg đóng gói sẵn
if ! command -v ffmpeg >/dev/null 2>&1; then
  FF=$("$VENV/bin/python" -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())")
  ln -sf "$FF" "$VENV/bin/ffmpeg"
fi
export PATH="$VENV/bin:$PATH"
echo "✓ mlx-whisper sẵn sàng: $("$VENV/bin/python" -c 'import importlib.metadata as m; print(m.version("mlx-whisper"))')"

[ "$1" = "--install" ] && exit 0
if [ -z "$1" ]; then echo "Thiếu đường dẫn folder dự án."; exit 1; fi
"$VENV/bin/python" "$HERE/mac_transcribe.py" "$@"
