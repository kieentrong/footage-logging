# Pipeline kỹ thuật — Trợ lý social

Đọc file này trước khi chạy lệnh. Mọi thứ chạy trong **máy ảo Linux trên Mac của anh Kiên** qua `device_bash`
(4 nhân, ~3–4GB RAM, không GPU, mỗi lệnh tối đa ~180 giây, tiến trình nền bị dừng khi lệnh kết thúc).

## Đường dẫn
| Thứ | Trong máy ảo | Trên Mac |
|---|---|---|
| Bộ công cụ | `~/mnt/Tai Nguyen/TroLySocial/tools` | `/Volumes/NEX4/Tai Nguyen/TroLySocial/tools` |
| Thư viện SFX | `~/mnt/Tai Nguyen/SFX` | `/Volumes/NEX4/Tai Nguyen/SFX` |
| Nhạc | `~/mnt/Tai Nguyen/Livestreaming Soundtrack` (+ thư mục anh chỉ thêm) | |
| LUT | `~/mnt/Tai Nguyen/LUTS/A7S3 Kien.cube` (Sony A7S3 log → đẹp nhất khi test) | |
| Dự án | `~/mnt/<tên folder dự án>` | folder anh chọn |
| Kết quả | `<dự án>/_SOCIAL/` | |

Folder phải được anh cấp quyền trong phiên (device_request_folder_access) — cần cả folder dự án và `/Volumes/NEX4/Tai Nguyen`.

## 0. Chuẩn bị (mỗi phiên)
```bash
bash "$HOME/mnt/Tai Nguyen/TroLySocial/tools/setup_vm.sh"
```

## 1. Quét + QC kỹ thuật (analyze.py)
```bash
T="$HOME/mnt/Tai Nguyen/TroLySocial/tools"; cd "$HOME/mnt/<dự án>"
timeout 175 python3 "$T/analyze.py" . --only POV "01_SOURCE/Day 2" --budget 135 --cost 0.03
```
- Chạy lặp lại cho tới khi in `còn lại 0` (có cache từng clip). POV HEVC nặng: dùng `--cost 0.3`; proxy ProRes nhẹ: `--cost 0.03`.
- Tự nhận thiết bị: Ray-Ban Meta (tag `Ray-Ban Meta Smart Glasses`) → POV; iPhone → PHONE; GoPro/DJI → ACTION; Sony → CAM (tự dùng proxy trong `.../Proxy/<tên>_Proxy.mov` nếu có).
- Mỗi giây gắn cờ: `dark` (tối), `blown` (cháy), `blur` (mờ/out nét), `shaky` (rung — ngưỡng nới cho POV/action), `whip` (lia gắt). Đoạn sạch ≥1.5s = `usable`. Điểm `quality` 0–10.
- File hỏng (thiếu moov atom…) → ghi `error: corrupt` để báo anh.
- Output: `_SOCIAL/analysis/clips/<id>.json` + `sheets/<id>.jpg` (6 khung).

## 2. Nghe lời thoại (transcribe.mjs, Whisper small offline)
```bash
cd "$HOME/mnt/<dự án>"; timeout 172 node ~/tls/transcribe.mjs . --only POV --budget 150
```
- Lặp tới khi in `DONE`. Tự nhận vi/en theo từng cửa sổ 30s, bỏ đoạn im lặng & ảo giác (lặp từ, "subscribe"…).
- Whisper small nghe **tiếng Anh khá, tiếng Việt kém** → transcript chỉ để hiểu nội dung/định vị đoạn; câu phụ đề cuối cùng phải tự viết lại cho đúng ngữ cảnh (đọc thêm sub đã burn sẵn, hình ảnh, ngữ cảnh). Không bịa lời người khác nói; đoạn nghe không rõ thì dùng text kể chuyện thay vì sub.
- **Ưu tiên bản Mac (mlx-whisper large-v3-turbo, tiếng Việt tốt hơn hẳn)**: sau khi analyze xong, nhờ anh dán 1 lệnh vào Terminal trên Mac
  (Claude không gõ được vào Terminal — quyền chỉ cho bấm):
  `bash "/Volumes/NEX4/Tai Nguyen/TroLySocial/tools/mac_whisper.sh" "<đường dẫn Mac của folder dự án>"`
  Script tự cài vào `~/.tls_mlx` (lần đầu), ghi `transcripts/<id>.json` với `model: mlx-whisper-large-v3-turbo` + mốc từng từ (`words`).
  transcribe.mjs không ghi đè file đã có → chạy bản Mac trước thì máy ảo chỉ bổ sung clip còn thiếu.
  Kiểm tra đã có bản mlx: `grep -l '"model": "mlx' transcripts/*.json | wc -l`.
  Giới hạn: mỗi clip nhận 1 ngôn ngữ (theo 30s đầu) — clip trộn Việt/Anh nhiều thì đoạn tiếng còn lại có thể bị dịch; kiểm khi viết phụ đề.
- Song song được: tách wav 16k → tar → stage sang container → `node transcribe.mjs <dir> --audio-dir wav` (container chậm hơn ~2×, chỉ dùng khi cần).

## 3. Xem (AI viết mô tả)
```bash
python3 "$T/review.py" pages . --only POV --per 4            # POV: xem kỹ
python3 "$T/review.py" pages . --only "01_SOURCE/Day 3" --per 8 --minq 8 --tag _d3   # CAM: lọc Q≥8
cd _SOCIAL/analysis && tar cf pages_x.tar pages/page_d3_*   # gom 1 file rồi device_stage_files
```
Xem từng trang ảnh (Read) + đọc `.txt` cùng tên (cờ kỹ thuật + lời thoại) rồi ghi `_SOCIAL/analysis/notes/notes_<nhóm>.json`:
`{clip_id: {desc, scene, people, tags, highlights:[{start,end,why,score}], usable, reject_reason, rating 1–5}}`.
Ghi rõ lý do loại (rung, tối, hút thuốc, lộ thông tin riêng, file hỏng…). Sau đó `review.py log .` → `clip_log.csv/json/html` (bảng log có ảnh cho anh xem).

Khi cần xem chính xác thời điểm (vd. tàu chạy qua lúc nào), làm "dải khung" 0.5s/khung bằng ffmpeg+cv2 rồi xem.

## 4. Dựng (render.py) — xem edit_guide.md
```bash
RENDER_BUDGET=140 timeout 175 python3 "$T/render.py" _SOCIAL/edits/<id>/edit.json --stage segs     # lặp tới khi xong
RENDER_BUDGET=150 timeout 175 python3 "$T/render.py" _SOCIAL/edits/<id>/edit.json --stage graphics
timeout 172 python3 "$T/render.py" _SOCIAL/edits/<id>/edit.json --stage final --preview   # ~50s, duyệt nhanh
timeout 175 python3 "$T/render.py" _SOCIAL/edits/<id>/edit.json --stage final             # ~2 phút cho 68s
```
Output: `final.mp4` (1080×1920, 30fps, H.264, AAC, -14 LUFS — đăng thẳng), `premiere.xml` (V1 A-roll, V2 B-roll, V3 graphic ProRes 4444 alpha, A1 thoại, A2 nhạc, A3 SFX, A4 VO; marker ghi clip gốc + timecode), `captions.srt`, `parts/`.

Kiểm tra: dựng contact sheet từ final (8–24 khung) và xem; đo loudness `ebur128` (mục tiêu -14 LUFS ±1).

## Bẫy đã gặp (đọc kỹ)
- **Commit file từ container lên ổ có độ trễ**: file trong `/mnt/user-data/outputs` vừa sửa có thể chưa đồng bộ khi `device_commit_files` đọc → ghi bản cũ. Luôn `wc -c` so kích thước 2 bên sau khi commit; lệch thì commit lại.
- **Ổ gắn trong máy ảo có độ trễ đọc-sau-ghi**: file Python vừa tạo trên ổ đôi khi process khác chưa thấy → file nháp đặt trong `~/.tls_cache` (render.py đã làm), chỉ copy kết quả cuối ra ổ.
- Đường dẫn có dấu cách làm hỏng filter `lut3d` → LUT được chép ra `~/.tls_cache` trước.
- Không `rm` được trong folder kết nối (cần xin quyền xoá) — đừng thiết kế quy trình dựa vào xoá file.
- Model ONNX: phải tắt memory arena (`enableCpuMemArena:false, enableMemPattern:false`) nếu không RAM vọt 2.5GB và bị kill.
- Gom nhiều file nhỏ thành 1 `.tar` trước khi stage/commit (giới hạn 50 file/lệnh, 30MB/file khi commit).
- Video final > 30MB: không commit từ container được → render final luôn trong máy ảo (đã ở đúng chỗ trên ổ).

- Commit **ghi đè** file đã có đôi khi không hiện trong máy ảo (wc -c vẫn số cũ dù chờ lâu). Cách chắc: commit ra tên mới **chưa từng dùng** (`x.md.<giờ>`; dùng lại cùng tên tạm cũng bị lỗi y vậy) rồi `mv -f x.v2.md x.md` trong máy ảo, kiểm lại `wc -c`.
- edit.json vừa ghi đè trên ổ có thể 'No such file' với process khác vài giây → sinh edit vào `~/.tls_cache/editX.json` và chạy render.py với file đó (render vẫn ghi kết quả vào `out` trên ổ), rồi copy edit.json ra ổ để lưu.

## Footage Logging v2 — log theo từng cảnh (27/10/2026)
Thứ tự: `analyze.py` → `shots.py` → (Mac) `mac_local.sh all` → `review.py pages` → Claude lượt 1 → `review.py candidates/strip` → Claude lượt 2 (notes) → `review.py log`.
- `shots.py`: chia clip thành khúc 45s (`~/.tls_cache/shots/*.pkl`, ảnh nén JPEG, tự xoá sau khi ghép), 4 tiến trình, mỗi tiến trình giữ một bộ mediapipe (tạo lại mỗi khúc làm rò bộ nhớ → sập). Tiến trình sập thì tự khởi động lại; khúc làm sập 2 lần bị bỏ qua. Lặp lệnh tới "còn 0 clip". Tốc độ thực tế: POV HEVC ~0.7s xử lý/giây video/tiến trình, proxy ProRes ~0.25.
- Ngưỡng nằm trong `TH` đầu file, ghi đè bằng `tools/thresholds.json` (calibrate.py tạo). Đổi thuật toán thì tăng `VERSION` để đo lại.
- Xong máy chính thì `touch _SOCIAL/analysis/shots/_DONE` → `chay_ai_local.command` chuyển sang mô tả cả máy chính.
- Bẫy: (1) máy ảo chỉ ~10GB — đầy ổ làm tiến trình sập, xem `df -h $HOME`; (2) `device_commit_files` có thể giao bản cũ nếu dùng lại cùng đường dẫn nguồn → mỗi lần commit dùng tên file nguồn mới, kiểm `md5sum`; (3) đừng `cd` vào thư mục khác trong cùng lệnh trước khi gọi tool với `.` là dự án; (4) vật lớn chạy qua (tàu, xe) làm máy đo nhầm thành chuyển động máy — lượt 2 của Claude sửa.
- Mac: Terminal chỉ cho Claude bấm, không gõ → dùng file `.command` để anh nhấp đúp.
