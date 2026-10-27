#!/usr/bin/env bash
# Footage Logging — cài phụ thuộc cho phần "máy đo" (macOS hoặc Linux). Chạy lại nhiều lần không sao.
#   bash setup.sh             # ffmpeg + Python: opencv, numpy, pillow, mediapipe
#   bash setup.sh --whisper   # thêm Whisper small offline (Node 18+) cho máy không có Mac Apple Silicon
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ok(){ printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn(){ printf '  \033[33m!\033[0m %s\n' "$1"; }

echo "Footage Logging — kiểm tra môi trường"
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  warn "Chưa có ffmpeg. Cài: macOS 'brew install ffmpeg' · Ubuntu/Debian 'sudo apt install ffmpeg'"; exit 1
fi
ok "ffmpeg $(ffmpeg -version | head -1 | awk '{print $3}')"

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null || { warn "Chưa có Python 3.9+"; exit 1; }
ok "$($PY --version)"
pipi(){ "$PY" -m pip install -q "$@" 2>/dev/null || "$PY" -m pip install -q --user "$@" 2>/dev/null \
        || "$PY" -m pip install -q --break-system-packages "$@"; }

"$PY" -c "import cv2, numpy, PIL" 2>/dev/null || { echo "  → cài opencv-python-headless numpy pillow"; pipi opencv-python-headless numpy pillow; }
ok "opencv $("$PY" -c 'import cv2;print(cv2.__version__)')"

# mediapipe 0.10.14 (có mp.solutions, model nằm sẵn trong gói) cần Python ≤ 3.12.
if "$PY" -c "import mediapipe as m; m.solutions.face_detection" 2>/dev/null; then
  ok "mediapipe (nhận diện mặt + dáng người)"
elif "$PY" -c 'import sys; exit(0 if sys.version_info < (3,13) else 1)'; then
  echo "  → cài mediapipe==0.10.14"; pipi "mediapipe==0.10.14" && ok "mediapipe 0.10.14" || warn "Không cài được mediapipe → shots.py dùng OpenCV (cỡ cảnh kém chính xác hơn)"
else
  warn "Python $("$PY" -c 'import sys;print(*sys.version_info[:2],sep=".")') chưa có mediapipe bản cũ → shots.py dùng OpenCV. Muốn chính xác hơn: PYTHON=python3.12 bash setup.sh"
fi
mkdir -p "$HOME/.tls_cache/shots"

if [ "$1" = "--whisper" ]; then
  command -v node >/dev/null || { warn "Cần Node 18+ cho Whisper small"; exit 1; }
  W="$HOME/.footage-logging/whisper"; mkdir -p "$W"; cd "$W"
  [ -f package.json ] || npm init -y >/dev/null
  [ -d node_modules/sts-whisper-small ] && [ -d node_modules/@huggingface/transformers ] \
    || { echo "  → cài @huggingface/transformers + sts-whisper-small (~250MB)"
         npm i -s @huggingface/transformers sts-whisper-small >"$W/npm.log" 2>&1 || { warn "npm lỗi, xem $W/npm.log"; tail -5 "$W/npm.log"; exit 1; }; }
  cp "$HERE/transcribe.mjs" "$W/transcribe.mjs"
  ok "Whisper small: node \"$W/transcribe.mjs\" <dự án>"
fi
echo "Sẵn sàng. Bộ công cụ: $HERE"
