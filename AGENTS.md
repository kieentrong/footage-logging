# AGENTS.md — footage-logging

## Dự án
Skill Claude "Footage Logging" (log & lọc source quay) của NEX Picture, kèm các script nó dùng. Tách ra từ skill `tro-ly-social` ngày 27/10/2026.

## Quy ước
- `SKILL.md` frontmatter `name: footage-logging`, phải khớp tên skill trên tài khoản Claude.
- Script gốc đang chạy thật nằm ở `/Volumes/NEX4/Tai Nguyen/TroLySocial/tools`; sửa ở đâu thì đồng bộ sang nơi kia và ghi nhật ký ở cả hai AGENTS.md.
- Không commit footage, transcript, notes của dự án khách, `node_modules`, model Whisper, API key.

## Việc còn mở
- Chờ anh chấm 40 cảnh trên trang hiệu chỉnh → chạy `calibrate.py fit` → `shots.py --force`.
- Qwen-VL mô tả hết máy chính (chạy qua đêm trên Mac).

## Nhật ký thay đổi
### 2026-10-27 — Khởi tạo repo
- SKILL.md từ tài khoản Claude; tools: analyze.py, transcribe.mjs, review.py, setup_vm.sh, mac_whisper.sh, mac_transcribe.py; docs/pipeline.md (sao từ TroLySocial).
- Thêm README.md, AGENTS.md, .gitignore.

### 2026-10-27 — v2: log theo từng cảnh, 3 tầng máy đo → AI local → Claude 2 lượt
- Thêm `tools/shots.py`: chia cảnh; optical flow Farneback + mô hình tương tự (tịnh tiến, tỉ lệ, xoay, thị sai) → cách đặt máy & chuyển động; mediapipe face/pose → cỡ cảnh, số người, bố cục, headroom, crop 9:16; nét, ổn định, phơi sáng, flicker, nhiễu, ám màu, vật cản, profile màu (Sony XML tìm cả trong PRIVATE/M4ROOT, đoán S-Log3 khi thiếu XML), slow-mo, âm thanh; `--mics`, `--takes`. Chạy theo khúc 45s song song, cache nén, tự khởi động lại khi tiến trình sập.
- `tools/review.py` viết lại: `pages`, `candidates`, `strip` (một lần giải mã), `log` theo cảnh ~47 cột, gộp Claude > AI local > máy.
- Thêm `mac_describe.py`, `mac_local.sh`, `chay_ai_local.command`, `calibrate.py`, `calib/trang_cham.html`.
- Chạy thử Tea and Tales: 842 clip → 2.139 cảnh (6,8 giờ); bóc băng mlx 727 clip; mic rời khớp 591 clip; Claude ghi notes 53 cảnh POV + 34 cảnh máy chính.
- Lỗi đã sửa khi chạy: đầy ổ máy ảo do file tạm, rò bộ nhớ mediapipe, POV bị gán DOF nông/crane, cảnh báo lệch nét quá nhạy.
- Giới hạn: vật lớn chạy qua khung làm máy tưởng máy quay chuyển động; zoom vs dolly chỉ là đoán; điểm "đáng chú ý" của máy bão hoà ở cảnh phỏng vấn.
