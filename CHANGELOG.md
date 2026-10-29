# Changelog

## 2.2.1 — 2026-10-29 · Vá hiện trường: thư mục "Proxies", nhận diện máy qua XML, layout HTML
- `analyze.py`: nhận diện cả thư mục **`Proxies`** (kiểu Premiere) bên cạnh `Proxy` — trước đây file proxy bị đếm như clip riêng, nhân đôi dự án.
- `analyze.py`: nhận diện thiết bị qua **XML sidecar** của Sony (`<Device manufacturer modelName>`, vd. `KEN9316.MP4` → `KEN9316M01.XML`). File XAVC gần như không ghi tag model trong MP4, và quy tắc tên file chỉ khớp tiền tố NEX/C#### trong M4ROOT — file tiền tố khác nằm ở gốc thẻ từng rơi xuống `unknown` dù quay bằng FX3. Thứ tự ưu tiên không đổi: tag trong file trước, sidecar là fallback cuối.
- `review.py` (HTML): khoá layout bảng (cột cố định, cột mô tả ưu tiên, bỏ `nowrap` ở cột điểm) — bản cũ bóp nghẹt cột mô tả khi mở ở cửa sổ hẹp/xem trước trong app.
- Bài học từ một lần chạy thật trên dự án 3 thẻ nhớ (490 clip): cả ba lỗi trên chỉ lộ khi chạy đủ nhiều định dạng thẻ khác nhau — mỗi thẻ một kiểu đặt proxy, một tiền tố tên file, một thân máy.


## 2.2.0 — 2026-10-29 · Hỗ trợ Muse + khoá quy trình
- `SKILL.md`: thêm mục **Khoá quy trình — không giao lưng chừng**: thứ tự tầng bắt buộc (máy đo → bóc băng → mô tả thô → agent xem 2 lượt → log) và cổng hoàn thành — bảng log chỉ là thành phẩm khi gộp đủ 4 nguồn (số đo + transcript + mô tả thô + notes của agent); giao thiếu tầng phải ghi rõ là BẢN TRUNG GIAN. Bóc băng khoá trước mô tả vì mô tả dùng lời thoại làm ngữ cảnh.
- Hỗ trợ **Muse** chính thức: ghi chú môi trường VM/sandbox (venv riêng + ghim `numpy<2` cho mediapipe 0.10.14); agent có SSH tới Mac (Muse) tự chạy tầng Mac qua SSH và chạy cả tầng đo ngay trên Mac — không chép footage nặng về VM, không cần người dùng bấm `.command`.
- `tools/setup.sh`: ghim `numpy<2` khi cài mediapipe, tránh pip resolve numpy 2 làm vỡ môi trường.
- Thuật ngữ trung tính: "Claude xem 2 lượt" → "agent xem 2 lượt" (Claude hoặc Muse); ưu tiên gộp: agent > AI local > máy. README thêm Cách 4 — Muse.
- Bài học từ một lần chạy thật: agent giao bảng log mới có tầng đo như thành phẩm, người dùng phải nhắc hai lần mới bổ sung đủ tầng — mục Khoá quy trình ở bản này nhằm chặn đúng lỗi đó.

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
