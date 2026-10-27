---
name: footage-logging
description: Log & lọc source quay (footage logging) như một assistant editor — QC kỹ thuật từng giây, chia cảnh, nhận diện cách đặt máy/chuyển động/cỡ cảnh, bóc băng, mô tả từng cảnh, đánh dấu đoạn hay/đoạn loại, xuất bảng log HTML/CSV. Dùng khi người dùng nhắc lọc source, log source, bóc băng, xem footage, clip nào dùng được, tìm đoạn hay, hoặc đưa một folder video đã quay.
---

# Footage Logging — log & lọc source theo từng cảnh

Người dùng đưa một folder dự án đã quay → mình làm đúng việc của assistant editor ngồi log source: xem hết,
QC kỹ thuật, bóc băng, mô tả từng cảnh, đánh dấu đoạn hay, loại đoạn hỏng, xuất bảng log để họ (hoặc bước dựng
sau) dùng ngay. Để xem kỹ mà không tốn sức, việc chia 3 tầng: **máy đo** (script, chạy trên máy có footage)
→ **AI local** (tuỳ chọn, Mac Apple Silicon, miễn phí) → **Claude xem 2 lượt**. Kết quả là bảng log mỗi dòng
một CẢNH (không phải một clip).

## Bộ công cụ
Thư mục `tools/` nằm cạnh file SKILL.md này (gọi là `$T`). Đọc `docs/pipeline.md` khi cần chi tiết lệnh, ngưỡng, bẫy.

| Tool | Việc |
|---|---|
| `setup.sh` | kiểm tra/cài ffmpeg, opencv, numpy, pillow, mediapipe (`--whisper`: thêm Whisper small offline) |
| `analyze.py` | quét metadata, nhận thiết bị (máy chính / POV kính / điện thoại / action cam), proxy, QC thô từng giây |
| `shots.py` | **chia cảnh** + đo từng cảnh, contact sheet có chú thích, lưới 2×2 khung cho AI; `--mics`, `--takes` |
| `mac_local.sh` · `chay_ai_local.command` | Mac Apple Silicon: mlx-whisper large-v3-turbo (bóc băng) + Qwen2.5-VL (mô tả thô từng cảnh) |
| `transcribe.mjs` | Whisper small offline (Node) — chỉ dùng khi không có Mac Apple Silicon |
| `review.py` | `pages` (lượt 1), `candidates` + `strip` (lượt 2), `log` (gộp bảng) |
| `calibrate.py` | `sample` → `page` (trang chấm tay) → `fit` (dò lại ngưỡng → `tools/thresholds.json`) |

Mọi kết quả ghi vào `<dự án>/_SOCIAL/analysis/` (đổi tên thư mục bằng biến môi trường `FL_OUT`). Không bao giờ
xoá, đổi tên hay ghi đè file source.

## 0. Bắt đầu
- Xác định môi trường chạy:
  - **Có shell trên chính máy chứa footage** (Claude Code, terminal macOS/Linux, WSL): chạy thẳng các lệnh dưới.
  - **Shell bị giới hạn thời gian mỗi lệnh** (vd. máy ảo của ứng dụng Claude nối tới folder trên máy người dùng,
    ~180s/lệnh): luôn thêm `timeout 175 … --budget 140` và lặp lệnh tới khi script báo còn 0. Cần quyền đọc folder
    dự án và folder chứa `tools/`; thiếu thì xin một lần.
- `bash $T/setup.sh` (lần đầu). Nếu script báo dùng OpenCV thay mediapipe thì cỡ cảnh/số người kém chính xác hơn —
  nói rõ với người dùng.
- Dự án đã có `_SOCIAL/analysis/` thì đọc `_SOCIAL/AGENTS.md` (nếu có) trước — mọi tool có cache, không làm lại phần đã xong.
- Khảo sát nhanh: số clip, tổng thời lượng theo nhóm thiết bị, có proxy / mic rời không → báo người dùng 3–4 dòng
  + ước lượng thời gian trước khi chạy lớn. Chỉ hỏi khi thật cần (dự án dùng để làm gì, nhân vật nào cần gọi tên).

## 1. Máy đo
```bash
cd "<dự án>"
python3 $T/analyze.py .                                   # thêm --only POV "Day 2" để chạy từng nhóm
python3 $T/shots.py .                                     # chia cảnh + đo; máy chính tự dùng proxy nếu có
python3 $T/shots.py . --mics ; python3 $T/shots.py . --takes   # mic rời khớp giờ · gom take giống nhau
touch _SOCIAL/analysis/shots/_DONE                        # báo phần Mac chuyển sang mô tả mọi cảnh
```
- Tham số tốc độ: `--cost` = giây xử lý / giây video (HEVC từ kính/điện thoại ~0.9, proxy ProRes ~0.15–0.3),
  `--budget` = số giây tối đa một lượt. Script có cache: chạy lại chỉ làm phần còn thiếu.
- File hỏng (thiếu moov atom…) được ghi `error` → phải báo người dùng tên file.
- Mỗi cảnh có: cách đặt máy (chân máy / gimbal / slider / cầm tay / POV), chuyển động (pan, tilt, push/pull, zoom,
  truck, pedestal, follow, roll; hướng + tốc độ), cỡ cảnh (ECU→EWS), số người, bố cục 1/3, headroom, DOF,
  crop 9:16, ổn định (rung, lia gắt), nét (out nét, lệch nét, hunting, nhoè), phơi sáng, flicker, nhiễu, ám màu,
  vật cản rìa khung, profile màu (S-Log3/HLG/Rec709), slow-mo, âm thanh (thoại, nhạc, gió, clip đỉnh), in/out đề xuất,
  điểm KT 0–10, điểm "đáng chú ý".
- Mọi số đo là MÁY ĐOÁN. Bẫy đã biết: vật lớn chạy qua khung (tàu, xe) làm máy tưởng máy quay chuyển động;
  POV luôn "đi tới/quay đầu"; DOF chỉ có nghĩa với máy chính; zoom vs dolly chỉ là đoán.

## 2. Bóc băng + AI local
- **Có Mac Apple Silicon:** `bash $T/mac_local.sh all "<dự án>"` (hoặc người dùng nhấp đúp
  `tools/chay_ai_local.command` rồi chọn folder dự án). Lần đầu tải ~6–7GB model.
  - mlx-whisper large-v3-turbo: transcript chuẩn (tiếng Việt tốt hơn hẳn Whisper small), có mốc từng từ.
  - Qwen2.5-VL viết `vlm/<clip>__sNN.json`: mô tả, loại cảnh, góc máy, cỡ cảnh, thời điểm, rủi ro, điểm nội dung,
    vai trò. Mô tả thô, hay chung chung và chấm "hook" quá tay → chỉ dùng để lọc, Claude chốt.
  - Nếu Claude không gõ được vào Terminal của Mac (chỉ bấm), nhờ người dùng nhấp đúp file `.command`.
- **Không có Mac:** `bash $T/setup.sh --whisper` rồi `node ~/.footage-logging/whisper/transcribe.mjs . --budget 150`.
  Whisper small nghe tiếng Anh ổn, tiếng Việt kém → chỉ để định vị và hiểu nội dung; khi trích lời thì sửa theo
  ngữ cảnh, đoạn không chắc ghi `(nghe không rõ)`, tuyệt đối không bịa lời.
- Transcript đã có (vd. bản mlx) không bị ghi đè bởi bản kém hơn.

## 3. Claude xem 2 lượt (phần quan trọng nhất)
**Lượt 1 — toàn cảnh:** `python3 $T/review.py pages . --only POV --per 3 --tag _pov` → xem từng ảnh trang
(contact sheet có mũi tên hướng máy, khung mặt, thanh màu xanh/vàng/đỏ theo giây) + đọc `.txt` cùng tên (số đo,
lời thoại mới nhất, mô tả AI local). Footage BTS/POV/điện thoại xem hết — thường là xương sống câu chuyện. Máy chính
dựa vào AI local + `--minq`, chỉ xem ảnh những cảnh nổi bật, nhưng vẫn đọc hết transcript (máy chính hay giấu
chuyện hay: nhiều take một câu thoại, người lạ được mời vào khung…).

**Lượt 2 — chi tiết:** `review.py candidates . --top 40` rồi `review.py strip . <clip_id> <từ> <đến> --step 0.4`
cho đoạn ứng viên → xem dải khung để chốt in/out chính xác, sửa chuyển động/cỡ cảnh máy đoán sai, bắt rủi ro.

Ghi `_SOCIAL/analysis/notes/notes_<nhóm>.json`, khoá `<clip_id>#sNN` (một cảnh) hoặc `<clip_id>` (cả clip):
```json
{"<clip_id>#s03": {"desc": "ai làm gì ở đâu, cụ thể", "scene_type": "hành động", "scene": "...", "tags": ["..."],
  "move": "chỉ ghi khi sửa máy đo", "size": "...", "angle": "...",
  "highlights": [{"start": 4.0, "end": 12.0, "why": "...", "score": 10}], "content": 9, "role": "hook",
  "risks": ["hút thuốc 41–46s"], "usable": true, "reject_reason": null, "in": 4.2, "out": 11.8}}
```
Cách nhìn của editor:
- Mô tả việc thật đang diễn ra (ai, làm gì, ở đâu), không tả chung chung kiểu "cảnh đẹp".
- Highlight = phản ứng thật, câu thoại đắt, sự cố, hành động khó, cảnh "kết quả" đẹp, khoảnh khắc lộ thiết bị đang làm việc.
- Tag cả vật/chủ đề xuất hiện để sau này tìm cảnh trám theo lời.
- Loại kèm lý do: hỏng kỹ thuật, và những thứ máy không bắt được — hút thuốc, cảnh thiếu lịch sự, thông tin riêng
  (màn hình tin nhắn, giấy tờ, biển số), trẻ em, người lạ nhìn rõ mặt, thông tin nhạy cảm về công việc (giá, hợp đồng,
  nền tảng thuê). Loại theo khoảng giây, không loại cả clip nếu phần còn lại dùng được.
- Ưu tiên khi gộp: Claude > AI local > máy.

## 4. Bảng log & báo cáo
`python3 $T/review.py log .` → `clip_log.html` (có ảnh, lọc "Dùng được / ND ≥ 7 / Bị loại"), `clip_log.csv`
(~49 cột, mở bằng Excel/Sheets), `clip_log.json` (cho bước dựng). Gửi người dùng html + csv.

Báo cáo đọc trong 1 phút: tổng clip / cảnh / thời lượng theo thiết bị; bao nhiêu dùng được; file hỏng (tên file);
5–8 khoảnh khắc mạnh nhất (clip + giây + vì sao); các đoạn loại vì nội dung; 3–6 ý tưởng video rút ra từ source;
giới hạn còn lại (phần nào chưa xem kỹ, transcript nào chưa chuẩn, máy đo dùng OpenCV thay mediapipe…).

## 5. Hiệu chỉnh theo mắt người dùng (tuỳ chọn)
`calibrate.py sample . --n 40` → `calibrate.py page .` tạo `analysis/calib/cham.html` (ảnh nhúng sẵn, mở bằng
trình duyệt; hoặc đăng thành trang Artifact có db) → người dùng chấm 5 ô mỗi cảnh, bấm "Tải answers.json" →
`calibrate.py fit . answers.json` ghi `tools/thresholds.json` + `analysis/calib/report.md` → `shots.py . --force`.

## Ghi nhớ
- Dự án có `_SOCIAL/AGENTS.md` thì ghi tiến độ vào đó (đã log nhóm nào, còn nhóm nào, quyết định gì).
- Shell giới hạn thời gian: gom nhiều file nhỏ thành `.tar` trước khi chuyển, kiểm `md5sum`/`wc -c` hai bên sau khi chuyển.
- Trả lời bằng ngôn ngữ người dùng đang dùng.
