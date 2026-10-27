---
name: "footage-logging"
description: "Log & lọc source quay (footage logging) cho dự án NEX: QC kỹ thuật, bóc băng, mô tả từng clip, đánh dấu đoạn hay/loại, xuất bảng log như editor. Dùng khi nhắc lọc source, log source, bóc băng, xem footage."
---

# Footage Logging — log & lọc source

Anh Kiên đưa một folder dự án đã quay → mình làm đúng việc của một assistant editor ngồi log source:
xem hết, QC kỹ thuật, bóc băng, mô tả từng clip, đánh dấu đoạn hay, loại đoạn hỏng, xuất bảng log để anh (hoặc bước dựng sau) dùng ngay.
Skill này chỉ lo phần LOG. Dựng video ngắn, caption, lịch đăng là việc của skill `tro-ly-social` (nó đọc lại kết quả log của skill này).

Dùng khi anh nói: "lọc source", "log source", "bóc băng", "xem footage giúp", "clip nào dùng được", "tìm đoạn hay", "đánh dấu source", hoặc chỉ đưa folder dự án và bảo xem qua.

## Bộ công cụ
Dùng chung bộ TroLySocial trên ổ của anh: `/Volumes/NEX4/Tai Nguyen/TroLySocial` (trong shell: `~/mnt/Tai Nguyen/TroLySocial`).
Trước khi chạy, đọc `TroLySocial/AGENTS.md` (kiến trúc + nhật ký) và `docs/pipeline.md` (lệnh + bẫy kỹ thuật) bằng `device_bash`.
- `tools/analyze.py` — quét metadata, QC từng giây, contact sheet 6 khung/clip
- `tools/transcribe.mjs` — Whisper offline, tự nhận vi/en, lọc ảo giác
- `tools/review.py` — `pages` (trang ảnh cho AI xem) và `log` (gộp bảng log)

## 0. Bắt đầu
- Cần quyền 2 folder: folder dự án và `/Volumes/NEX4/Tai Nguyen`. Thiếu thì `device_request_folder_access` (xin 1 lần, nêu lý do).
- `bash "$HOME/mnt/Tai Nguyen/TroLySocial/tools/setup_vm.sh"`.
- Dự án đã có `_SOCIAL/AGENTS.md` / `_SOCIAL/analysis/` thì đọc trước — mọi tool có cache, không chạy lại phần đã xong.
- Khảo sát nhanh cấu trúc folder (POV, 01_SOURCE/Day N, Proxy, Mic…), đếm clip + tổng thời lượng theo nhóm, báo anh 3–4 dòng và ước lượng thời gian trước khi chạy lớn.
- Chỉ hỏi khi thật cần: dự án dùng cho mục đích gì (phim chính / social / cả hai), có nhân vật nào cần nhận diện tên không.

## 1. QC kỹ thuật (analyze.py)
```bash
T="$HOME/mnt/Tai Nguyen/TroLySocial/tools"; cd "$HOME/mnt/<dự án>"
timeout 175 python3 "$T/analyze.py" . --only POV "01_SOURCE/Day 2" --budget 135 --cost 0.03
```
- Lặp tới khi in `còn lại 0`. POV HEVC dùng `--cost 0.3`, proxy ProRes `--cost 0.03`.
- Tự nhận thiết bị: Ray-Ban Meta → POV, iPhone → PHONE, GoPro/DJI → ACTION, Sony → CAM (tự dùng proxy nếu có).
- Cờ mỗi giây: `dark`, `blown`, `blur`, `shaky` (ngưỡng nới cho POV/action), `whip`. Đoạn sạch ≥1.5s = `usable`. Điểm `quality` 0–10.
- File hỏng (thiếu moov atom…) ghi `error: corrupt` → phải báo anh tên file.

## 2. Bóc băng (transcribe.mjs)
```bash
cd "$HOME/mnt/<dự án>"; timeout 172 node ~/tls/transcribe.mjs . --only POV --budget 150
```
- Lặp tới khi `DONE`. Ưu tiên clip có thoại: POV, phỏng vấn, mic rời.
- Whisper small nghe tiếng Anh ổn, tiếng Việt kém → transcript dùng để định vị và hiểu nội dung; khi trích lời vào log thì sửa lại theo ngữ cảnh, đoạn không chắc ghi `(nghe không rõ)`, tuyệt đối không bịa lời.
- Nếu trong `transcripts/` đã có json do anh chạy mlx-whisper large-v3 trên Mac thì giữ nguyên, không ghi đè.

## 3. Xem & mô tả (phần quan trọng nhất)
```bash
python3 "$T/review.py" pages . --only POV --per 4                                 # BTS/POV: xem hết
python3 "$T/review.py" pages . --only "01_SOURCE/Day 3" --per 8 --minq 8 --tag _d3  # máy chính: lọc Q≥8 trước
cd _SOCIAL/analysis && tar cf pages_x.tar pages/page_d3_*                            # gom 1 file rồi device_stage_files
```
Xem **thật** từng trang ảnh (Read) + đọc `.txt` cùng tên (cờ kỹ thuật + lời thoại). Cần biết chính xác thời điểm (vd. xe/tàu chạy qua lúc nào) thì cắt dải khung 0.5s/khung bằng ffmpeg + cv2 rồi xem.

Nếu có `tools/local_describe.py` và Ollama chạy trên Mac (anh đã cài), cho model local mô tả thô toàn bộ clip trước, rồi mình chỉ xem lại ảnh các clip điểm cao / mô tả mơ hồ. Chưa có thì mình tự xem như trên.

Ghi `_SOCIAL/analysis/notes/notes_<nhóm>.json`:
```json
{"<clip_id>": {"desc": "việc đang diễn ra, cụ thể", "scene": "địa điểm", "people": ["tên"],
  "tags": ["..."], "highlights": [{"start": 4, "end": 12, "why": "vì sao hay", "score": 1-10}],
  "usable": true, "reject_reason": null, "rating": 1-5}}
```
Cách nhìn của editor:
- Mô tả việc thật đang diễn ra (ai làm gì, ở đâu), không tả chung chung kiểu "cảnh đẹp".
- Highlight = khoảnh khắc có phản ứng thật, câu thoại đắt, sự cố, hành động khó/gay cấn, cảnh "kết quả" đẹp, cảnh BTS lộ thiết bị đang làm việc. Ghi start–end theo giây trong clip.
- Tag cả vật/chủ đề xuất hiện (xe máy, chè, matcha, sân bay…) để sau này tìm cảnh trám theo lời.
- Loại kèm lý do rõ: hỏng kỹ thuật (rung/tối/mờ/out nét/file hỏng) và thứ máy không bắt được: hút thuốc, cảnh thiếu lịch sự với người khác, thông tin riêng (màn hình tin nhắn, giấy tờ, biển số), người lạ không muốn lên hình. Loại một đoạn thì ghi khoảng giây, không loại cả clip nếu phần còn lại dùng được.

## 4. Xuất bảng log
```bash
python3 "$T/review.py" log .
```
→ `_SOCIAL/analysis/clip_log.html` (có ảnh, mở bằng trình duyệt), `clip_log.csv` (mở Excel/Sheets), `clip_log.json` (cho bước dựng).
Gửi anh `clip_log.html` + `clip_log.csv` (stage rồi SendUserFile).

## 5. Báo cáo cho anh (ngắn, đọc 1 phút)
- Tổng số clip / thời lượng theo nhóm thiết bị; bao nhiêu dùng được; file hỏng (tên file).
- 5–8 khoảnh khắc mạnh nhất: tên clip + giây + 1 câu vì sao.
- Các đoạn đã loại vì lý do nội dung (hút thuốc, thông tin riêng…).
- 3–6 ý tưởng video/câu chuyện rút ra từ source (nếu dự án có làm social).
- Giới hạn: phần nào chưa xem kỹ (vd. máy chính mới lọc Q≥8), transcript tiếng Việt chưa chuẩn.

## Ghi nhớ
- Mọi sửa đổi bộ công cụ/quy trình: thêm dòng nhật ký vào `TroLySocial/AGENTS.md`; tiến độ log của dự án: `<dự án>/_SOCIAL/AGENTS.md` (đã log nhóm nào, còn nhóm nào).
- Sau khi commit file từ container lên ổ, so `wc -c` hai bên (ổ có độ trễ đồng bộ); gom nhiều file nhỏ thành `.tar` trước khi stage/commit.
- Không xoá/đổi tên file source của anh; mọi kết quả chỉ ghi vào `_SOCIAL/`.
- Trả lời anh bằng tiếng Việt.