#!/usr/bin/env bash
# Trợ lý social — chuẩn bị máy ảo (chạy đầu mỗi phiên, ~1 phút, chạy lại nhiều lần không sao)
# Dùng: bash "$HOME/mnt/Tai Nguyen/TroLySocial/tools/setup_vm.sh"
set -e
# folder bộ công cụ có thể được cấp dưới tên "Tai Nguyen" hoặc "TroLySocial"
TLS="$HOME/mnt/Tai Nguyen/TroLySocial"; [ -d "$TLS" ] || TLS="$HOME/mnt/TroLySocial"
python3 -c "import cv2, numpy, PIL" 2>/dev/null || pip3 install --user -q opencv-python-headless numpy pillow
# Footage Logging: nhận diện mặt + dáng người (bản 0.10.14 có sẵn model trong gói, không cần tải mạng)
python3 -c "import mediapipe" 2>/dev/null || pip3 install --user -q "mediapipe==0.10.14"
mkdir -p "$HOME/.tls_cache/shots"
mkdir -p "$HOME/tls" "$HOME/.tls_cache"
cd "$HOME/tls"
if [ ! -d node_modules/sts-whisper-small ] || [ ! -d node_modules/@huggingface/transformers ]; then
  [ -f package.json ] || npm init -y >/dev/null
  # Whisper small (ONNX, offline) lấy qua npm vì máy ảo không vào được huggingface.co
  npm i -s @huggingface/transformers sts-whisper-small >/dev/null 2>&1
fi
# luôn lấy bản script mới nhất từ ổ NEX4 về chạy cục bộ (node cần node_modules cạnh script)
[ -d node_modules/sts-rmbg-modnet ] || npm i -s sts-rmbg-modnet >/dev/null 2>&1   # MODNet cắt nền cho thumbnail
python3 -c "import onnxruntime" 2>/dev/null || pip3 install --user -q onnxruntime
cp "$TLS/tools/transcribe.mjs" "$HOME/tls/transcribe.mjs"
cp "$TLS/tools/asr.mjs" "$HOME/tls/ref.mjs"   # Whisper nhanh 1 file (qc.py --asr)
which ffmpeg ffprobe >/dev/null
echo "OK — máy ảo sẵn sàng. Tools: $TLS/tools"
