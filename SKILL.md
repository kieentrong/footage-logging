---
name: footage-logging
description: Log & lọc source quay (footage logging) cho dự án NEX: QC kỹ thuật, bóc băng, mô tả từng clip, đánh dấu đoạn hay/loại, xuất bảng log như editor. Dùng khi nhắc lọc source, log source, bóc băng, xem footage.
---

# Footage Logging — log & lọc source theo từng cảnh

Anh Kiên đưa một folder dự án đã quay → mình làm đúng việc của assistant editor ngồi log source, nhưng chia
3 tầng để xem kỹ mà không tốn sức: **máy đo** (máy ảo) → **AI local** (Mac, miễn phí) → **Claude xem 2 lượt**.
Kết quả là bảng log mỗi dòng một CẢNH (không phải một clip) với đủ tiêu chí ngôn ngữ máy, kỹ thuật, nội dung,
âm thanh, biên tập. Skill `tro-ly-social` đọc lại bảng này để dựng video.

Dùng khi anh nói: "lọc source", "log source", "bóc băng", "xem footage giúp", "clip nào dùng được", "tìm đoạn hay",
"đánh dấu source", hoặc chỉ đưa folder dự án và bảo xem qua.

## Bộ công cụ
Nằm trên ổ anh: `/Volumes/NEX4/Tai Nguyen/TroLySocial/tools` (trong máy ảo: `~/mnt/TroLySocial/tools` hoặc
`~/mnt/Tai Nguyen/TroLySocial/tools` tuỳ folder được cấp). Đọc `TroLySocial/AGENTS.md` và `docs/pipeline.md` trước.

| Tool | Chạy ở | Việc |
|---|---|---|
| `analyze.py` | máy ảo | quét metadata, thiết bị, proxy, QC thô từng giây |
| `shots.py` | máy ảo | **chia cảnh** + đo từng cảnh (chi tiết bên dưới), vẽ contact sheet có chú thích, lưới 2×2 cho AI |
| `transcribe.mjs` | máy ảo | Whisper small — chỉ dùng khi chưa chạy được bản Mac |
| `mac_local.sh` / `mac_whisper.sh` / `mac_describe.py` | Mac | mlx-whisper large-v3-turbo (bóc băng chuẩn tiếng Việt) + Qwen2.5-VL (mô tả thô từng cảnh) |
| `review.py` | máy ảo | `pages` (lượt 1), `candidates` + `strip` (lượt 2), `log` (gộp bảng) |
| `calibrate.py` | máy ảo | lấy mẫu cảnh cho anh chấm tay → dò lại ngưỡng → `tools/thresholds.json` |

## 0. Bắt đầu
- Cần quyền 2 folder: folder dự án và `TroLySocial` (hoặc cả `Tai Nguyen`). Thiếu thì `device_request_folder_access` một lần.
- `bash .../tools/setup_vm.sh` (cài opencv, mediapipe, Whisper small).
- Dự án đã có `_SOCIAL/analysis/` thì đọc `_SOCIAL/AGENTS.md` trước — mọi tool có cache, không làm lại phần đã xong.
- Khảo sát nhanh: số clip, thời lượng theo nhóm thiết bị, có proxy/mic rời không → báo anh 3–4 dòng + ước lượng thời gian.

## 1. Máy đo (máy ảo)
```bash
T=~/mnt/TroLySocial/tools; cd ~/mnt/<dự án>
timeout 175 python3 $T/analyze.py . --budget 135 --cost 0.03          # lặp tới "còn lại 0"
timeout 172 python3 $T/shots.py . --only POV --budget 140             # POV HEVC: --cost 0.9 (mặc định)
timeout 172 python3 $T/shots.py . --only 01_SOURCE --budget 140 --cost 0.3   # máy chính qua proxy
python3 $T/shots.py . --mics ; python3 $T/shots.py . --takes          # mic rời khớp giờ, nhóm take giống nhau
```
- shots.py chia clip dài thành khúc 45s chạy song song rồi ghép; lặp lệnh tới "còn 0 clip". Xong thì tạo file
  `_SOCIAL/analysis/shots/_DONE` để phần Mac chuyển sang mô tả máy chính.
- Mỗi cảnh có: cách đặt máy (chân máy / gimbal / slider / cầm tay / POV), chuyển động (pan, tilt, push/pull, zoom,
  truck, pedestal, follow, roll; hướng + tốc độ), cỡ cảnh (ECU→EWS, từ mặt + dáng người), số người, bố cục 1/3,
  headroom, DOF, crop 9:16 (focus_x), ổn định (rung, lia gắt, jello), nét (out nét, lệch nét, hunting, nhoè),
  phơi sáng (cháy/sập), flicker, nhiễu, ám màu, vật cản rìa khung, profile màu (S-Log3/HLG/Rec709), slow-mo,
  âm thanh (thoại, nhạc nền, gió, clip đỉnh, đỉnh âm thanh), in/out đề xuất, điểm KT 0–10, điểm "đáng chú ý".
- Mọi số đo là MÁY ĐOÁN. Bẫy đã biết: vật lớn chạy qua khung (tàu, xe) làm máy tưởng máy quay chuyển động;
  POV luôn "đi tới/quay đầu"; DOF chỉ có nghĩa với máy chính.

## 2. AI local trên Mac
Terminal trên Mac chỉ cho Claude bấm, không gõ được → nhờ anh nhấp đúp `TroLySocial/chay_ai_local.command`
(sửa đường dẫn dự án trong file nếu là dự án khác), hoặc anh chạy `bash .../tools/mac_local.sh all "<dự án>"`.
- mlx-whisper large-v3-turbo ghi đè transcript Whisper small (tiếng Việt chuẩn hơn hẳn).
- Qwen2.5-VL viết `vlm/<clip>__sNN.json`: mô tả, loại cảnh, góc máy, cỡ cảnh, thời điểm, rủi ro, điểm nội dung, vai trò.
  Mô tả thô, hay chung chung và gán "hook" quá tay → chỉ dùng để lọc, Claude chốt.

## 3. Claude xem 2 lượt (phần quan trọng nhất)
**Lượt 1 — toàn cảnh:** `review.py pages . --only POV --per 3 --tag _pov` → gom `.tar` → stage → đọc `.txt`
(số đo + lời thoại mới nhất + AI local) và xem ảnh (contact sheet có mũi tên hướng máy, khung mặt xanh, thanh
màu xanh/vàng/đỏ theo giây). Ảnh cao quá thì ghép 2 cột trong container cho dễ xem. POV/điện thoại xem hết;
máy chính dựa vào AI local + `--minq`, chỉ xem ảnh những cảnh nổi bật.
**Lượt 2 — chi tiết:** `review.py candidates . --top 40` rồi `review.py strip . <clip_id> <từ> <đến> --step 0.4`
cho các đoạn ứng viên → xem dải khung để chốt in/out chính xác, sửa chuyển động/cỡ cảnh máy đoán sai, bắt rủi ro
(hút thuốc, người lạ, màn hình, nhắc tên nền tảng thuê freelancer).

Ghi `_SOCIAL/analysis/notes/notes_<nhóm>.json`, khoá `<clip_id>#sNN` (một cảnh) hoặc `<clip_id>` (cả clip):
```json
{"<clip_id>#s03": {"desc": "ai làm gì ở đâu, cụ thể", "scene_type": "hành động", "scene": "...", "tags": ["..."],
  "move": "chỉ ghi khi sửa máy đo", "size": "...", "angle": "...",
  "highlights": [{"start": 4.0, "end": 12.0, "why": "...", "score": 10}], "content": 9, "role": "hook",
  "risks": ["hút thuốc 41–46s"], "usable": true, "reject_reason": null, "in": 4.2, "out": 11.8}}
```
Ưu tiên khi gộp: Claude > AI local > máy. Loại một đoạn thì ghi khoảng giây, không loại cả clip nếu phần còn lại dùng được.

## 4. Bảng log & báo cáo
`review.py log .` → `clip_log.html` (có ảnh, lọc "Dùng được / ND ≥ 7 / Bị loại"), `clip_log.csv` (mở Sheets),
`clip_log.json`. Gửi anh html + csv. Báo cáo 1 phút đọc: tổng clip/cảnh theo thiết bị, bao nhiêu dùng được, file
hỏng, 5–8 khoảnh khắc mạnh nhất (clip + giây + vì sao), đoạn loại vì nội dung, 3–6 ý tưởng video, giới hạn còn lại.

## 5. Hiệu chỉnh theo mắt anh (khi có thời gian)
`calibrate.py sample . --n 40` → đưa 40 cảnh lên một trang Artifact cho anh chấm (cách đặt máy, chuyển động, cỡ cảnh,
ổn định, nét) → lưu đáp án → `calibrate.py fit . answers.json` → chạy lại `shots.py --force`. Ghi kết quả vào AGENTS.md.

## Ghi nhớ
- Sửa bộ công cụ/quy trình → nhật ký trong `TroLySocial/AGENTS.md`; tiến độ dự án → `<dự án>/_SOCIAL/AGENTS.md`;
  đồng bộ repo `kieentrong/footage-logging`.
- Máy ảo ~10GB ổ, mỗi lệnh ≤180s: dùng `--budget`, gom file thành `.tar` trước khi stage, commit file sửa dưới tên
  mới rồi `mv` (tránh bản cũ bị cache), kiểm `md5sum` hai bên.
- Không xoá/đổi tên source của anh; mọi kết quả chỉ ghi vào `_SOCIAL/`.
- Trả lời anh bằng tiếng Việt.
