# Changelog

## 2.1.0 — 2026-10-27 · Bản cộng đồng
- Bỏ mọi đường dẫn và tên dự án nội bộ; `SKILL.md` viết lại cho mọi người dùng, công cụ nằm ngay trong thư mục skill.
- Biến môi trường `FL_OUT` (thư mục kết quả, mặc định `_SOCIAL`) và `FL_TZ` (múi giờ nơi quay, mặc định 7).
- `tools/setup.sh` thay `setup_vm.sh`: kiểm tra/cài phụ thuộc trên macOS/Linux, `--whisper` cài Whisper small vào `~/.footage-logging/whisper`.
- `shots.py`: tự chuyển sang OpenCV khi không có mediapipe bản có `mp.solutions` (Python 3.13+), có cảnh báo.
- `calibrate.py page`: tạo trang chấm tự chứa (ảnh nhúng), lưu trong trình duyệt + nút "Tải answers.json"; vẫn dùng được db khi đăng thành Artifact.
- `chay_ai_local.command`: hỏi chọn folder dự án, nhớ folder lần trước.
- `scripts/build-skill-zip.sh`: đóng gói zip để tải lên Claude.
- Thêm README đầy đủ, LICENSE (MIT), tài liệu `docs/pipeline.md` viết lại.

## 2.0.0 — 2026-10-27 · Log theo từng cảnh
- `shots.py`: chia cảnh; optical flow Farneback + mô hình tương tự (tịnh tiến, tỉ lệ, xoay, thị sai) → cách đặt máy & chuyển động;
  mediapipe face/pose → cỡ cảnh, số người, bố cục, headroom, crop 9:16; nét, ổn định, phơi sáng, flicker, nhiễu, ám màu, vật cản,
  profile màu, slow-mo, âm thanh; `--mics`, `--takes`. Chạy theo khúc 45s song song, cache nén, tự khởi động lại khi tiến trình sập.
- `review.py` viết lại: `pages`, `candidates`, `strip`, `log` theo cảnh (49 cột), gộp Claude > AI local > máy.
- AI local trên Mac: `mac_describe.py` (Qwen2.5-VL), `mac_local.sh`, `chay_ai_local.command`. Hiệu chỉnh: `calibrate.py`.
- Chạy thật trên một dự án 5 ngày quay: 842 clip → 2.139 cảnh (6,8 giờ); bóc băng mlx 727 clip; mic rời khớp 591 clip.
- Lỗi đã sửa khi chạy thật: đầy ổ do file tạm, rò bộ nhớ mediapipe, POV bị gán DOF nông/crane, cảnh báo lệch nét quá nhạy.

## 1.0.0 — 2026-10-27 · Khởi tạo
- `analyze.py` (QC thô từng giây, contact sheet), `transcribe.mjs` (Whisper small offline), `review.py` (trang ảnh + bảng log theo clip), mlx-whisper cho Mac.
