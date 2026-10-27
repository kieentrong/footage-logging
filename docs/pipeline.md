# Pipeline kỹ thuật — Footage Logging

Tài liệu tra cứu cho người chạy tay hoặc cho Claude khi cần chi tiết. Hướng dẫn cài đặt và dùng nhanh: xem [README](../README.md).

## Thứ tự chạy

```
analyze.py → shots.py (+ --mics, --takes) → [Mac] mac_local.sh all → review.py pages → Claude lượt 1
          → review.py candidates / strip → Claude lượt 2 (notes) → review.py log → (tuỳ chọn) calibrate.py
```

Mọi script nhận `<dự án>` là thư mục gốc chứa footage và ghi vào `<dự án>/$FL_OUT/analysis/` (mặc định `_SOCIAL/analysis/`).
Script có cache theo từng clip: chạy lại chỉ làm phần còn thiếu, thêm `--force` để làm lại.

## Cấu trúc thư mục kết quả

```
_SOCIAL/analysis/
  clips/<id>.json        # analyze.py: metadata, thiết bị, proxy, cờ QC từng giây, điểm quality
  sheets/<id>.jpg        # analyze.py: contact sheet 6 khung
  shots/<id>.json        # shots.py: danh sách cảnh + toàn bộ số đo của từng cảnh
  sheets2/<id>.jpg       # shots.py: contact sheet có chú thích (mũi tên hướng máy, khung mặt, thanh màu theo giây)
  kf/<id>__sNN.jpg       # shots.py: lưới 2×2 khung của từng cảnh (cho AI local / Claude)
  transcripts/<id>.json  # mlx-whisper hoặc Whisper small: {lang, model, segments:[{start,end,text,words?}]}
  vlm/<id>__sNN.json     # AI local (Qwen2.5-VL): mô tả thô từng cảnh
  pages/page<tag>_NNN.*  # review.py pages: trang ảnh + .txt cho Claude xem lượt 1
  strips/<id>_<a>-<b>.jpg# review.py strip: dải khung để chốt in/out
  notes/notes_*.json     # Claude ghi (lượt 1 + 2)
  clip_log.html|csv|json # review.py log: bảng log cuối cùng, mỗi dòng một cảnh
  calib/                 # calibrate.py: sample.json, img/, cham.html, report.md
```

## 1. analyze.py — quét + QC thô

```bash
python3 tools/analyze.py <dự án> [--only POV "Day 2"] [--workers 4] [--budget 135 --cost 0.4] [--force]
```

- Tự nhận thiết bị từ metadata/tên file: kính Ray-Ban Meta → `POV`; iPhone/Samsung/Android → `PHONE`; GoPro/DJI → `ACTION`;
  Sony và máy khác → `CAM`. Máy chính tự dùng proxy trong thư mục `Proxy/` (`<tên>_Proxy.*`) nếu có.
- Giờ quay lấy theo múi giờ `FL_TZ` (giờ so với UTC, mặc định `7`).
- Bỏ qua thư mục `_SOCIAL`, `99_EXPORT`, `Proxy`, `THMBNL`, `SUB`, `03_ELEMENT`, `.Trash`, file `._*`.
- Cờ mỗi giây: `dark`, `blown`, `blur`, `shaky` (ngưỡng nới cho POV/action), `whip`. Đoạn sạch ≥1.5s = `usable`. Điểm `quality` 0–10.
- File hỏng (thiếu moov atom…) → `error: corrupt`.

## 2. shots.py — đo từng cảnh

```bash
python3 tools/shots.py <dự án> [--only POV] [--workers 4] [--budget 140] [--cost 0.9] [--force] [--ids <id> …]
python3 tools/shots.py <dự án> --mics     # tìm file WAV mic rời khớp giờ quay với từng clip
python3 tools/shots.py <dự án> --takes    # gom nhóm take giống nhau, chọn take tốt nhất
```

- Clip dài được chia khúc 45s, đo song song (`--workers`), ghép lại; khúc tạm nằm trong `~/.tls_cache/shots/`
  (ảnh nén JPEG, tự xoá sau khi ghép). Tiến trình sập thì tự khởi động lại; khúc làm sập 2 lần bị bỏ qua.
- **Chia cảnh:** cắt cứng (histogram), trôi cảnh (POV đi sang chỗ khác), cảnh dài >20s chia nhỏ.
- **Chuyển động:** optical flow Farneback → mô hình tương tự (tịnh tiến tx/ty, tỉ lệ, xoay) + phần dư (thị sai).
  Ít thị sai → pan/tilt; nhiều thị sai → truck/dolly; tỉ lệ đều → zoom; tỉ lệ + thị sai → push/pull.
  Độ giật cao tần → chân máy / gimbal-slider / cầm tay.
- **Người:** mediapipe face + pose → số người, cỡ cảnh (chiều cao mặt / dáng người), vị trí chủ thể, headroom, crop 9:16.
  Không có mediapipe cũ (Python 3.13+) → dùng Haar + HOG của OpenCV nếu có, kém chính xác hơn.
- **Kỹ thuật:** nét chủ thể vs rìa (DOF), focus hunting, lệch nét, nhoè; phơi sáng, vùng cháy/sập; flicker; nhiễu
  (Immerkær); ám màu (Lab); vật cản rìa khung; profile màu (S-Log3/HLG/Rec709 từ metadata, Sony XML); slow-mo.
- **Âm thanh:** mức dB, clip đỉnh, gió (<150Hz), đoán nhạc nền, có thoại (theo transcript), đỉnh âm thanh (cười, hét).
- **Điểm:** KT 0–10 và "đáng chú ý" (máy). Điểm nội dung cuối cùng do Claude chấm.

Tốc độ tham khảo (4 nhân, không GPU): HEVC từ kính/điện thoại ~0.7–0.9s xử lý / giây video / tiến trình; proxy ProRes ~0.15–0.3.

### Ngưỡng

Ngưỡng nằm trong `TH` đầu `shots.py`, ghi đè bằng `tools/thresholds.json` (do `calibrate.py fit` tạo). Đổi thuật toán
thì tăng `VERSION` để các clip được đo lại.

| Khoá | Ý nghĩa | Mặc định |
|---|---|---|
| `jit_tripod`, `jit_smooth`, `jit_hand` | độ giật cao tần: dưới ngưỡng → chân máy / gimbal-slider / cầm tay | 0.0018 · 0.0055 · 0.016 |
| `move_min` | tịnh tiến (phần bề rộng khung/giây) dưới mức này coi như đứng yên | 0.012 |
| `zoom_min` | tỉ lệ / giây tối thiểu để coi là zoom/push | 0.010 |
| `parallax_hi` | thị sai / chuyển động > ngưỡng → truck/dolly | 0.30 |
| `size_face` | chiều cao mặt / khung cho ECU, CU, MCU, MS, MWS, WS | 0.45 · 0.22 · 0.13 · 0.075 · 0.035 · 0.012 |

## 3. Bóc băng

**Mac Apple Silicon (khuyên dùng):**
```bash
bash tools/mac_local.sh install                     # một lần: venv ~/.tls_mlx, mlx-whisper + mlx-vlm
bash tools/mac_local.sh whisper  "<dự án>" [--only POV] [--force]
bash tools/mac_local.sh describe "<dự án>" [--only POV] [--min-interest 4]
bash tools/mac_local.sh all      "<dự án>"
```
hoặc nhấp đúp `tools/chay_ai_local.command` → chọn folder dự án (nhớ folder lần trước).

- mlx-whisper large-v3-turbo ghi `transcripts/<id>.json` với `model: mlx-whisper-large-v3-turbo` + mốc từng từ.
  Mỗi clip nhận một ngôn ngữ theo 30s đầu: clip trộn Việt/Anh nhiều thì kiểm lại đoạn tiếng còn lại.
- Qwen2.5-VL: ≥16GB RAM → bản 7B 4-bit (~5GB), <16GB → bản 3B. Đổi model: `TLS_VLM_MODEL=mlx-community/<tên>`.

**Không có Mac:**
```bash
bash tools/setup.sh --whisper
node ~/.footage-logging/whisper/transcribe.mjs "<dự án>" [--only POV] [--budget 150]
```
Whisper small ONNX offline, tự nhận vi/en theo cửa sổ 30s, bỏ đoạn im lặng và ảo giác. Tiếng Anh khá, tiếng Việt kém.
Không ghi đè transcript đã có.

## 4. review.py — cho Claude xem và gộp bảng

```bash
python3 tools/review.py pages <dự án> [--only POV] [--per 3] [--minq 0] [--tag _pov]
python3 tools/review.py candidates <dự án> [--top 40] [--only POV]
python3 tools/review.py strip <dự án> <clip_id> <từ_giây> <đến_giây> [--step 0.4]
python3 tools/review.py log <dự án>
```

- `pages`: ghép contact sheet có chú thích thành trang ảnh + `.txt` (số đo máy + lời thoại mới nhất + mô tả AI local từng cảnh).
- `candidates`: cảnh ứng viên cho lượt 2 (điểm đáng chú ý cao, AI local chấm cao, có đỉnh âm thanh).
- `strip`: dải khung đều nhau trong một đoạn, một lần giải mã.
- `log`: gộp máy đo + AI local + notes của Claude (ưu tiên Claude > AI local > máy) → `clip_log.html/csv/json`, 49 cột:

> Cảnh · File · Thiết bị · Giờ quay · Từ/Đến · In/Out đề xuất · Cách đặt máy · Chuyển động · Tốc độ · Cỡ cảnh · Góc máy ·
> DOF · Bố cục · Headroom · Tốc độ khung · Crop 9:16 · Ổn định · Nét · Phơi sáng · Profile màu · Ám màu · Nhiễu · Flicker ·
> Vật cản · Loại cảnh · Bối cảnh · Người · Số người · Hành động · Mô tả · Tag · Thời điểm · Loại tiếng · Lỗi tiếng · Mức (dB) ·
> Lời thoại · Mic rời · Điểm KT · Điểm ND · Vai trò · Đoạn hay · Rủi ro đăng · Take · Dùng được · Lý do loại · Nguồn · Ảnh

Notes của Claude (`notes/notes_*.json`), khoá `<clip_id>#sNN` hoặc `<clip_id>`:
```json
{"<clip_id>#s03": {"desc": "...", "scene_type": "...", "scene": "...", "people": ["..."], "action": "...", "tags": ["..."],
  "move": "...", "size": "...", "angle": "...", "highlights": [{"start": 4, "end": 12, "why": "...", "score": 9}],
  "content": 9, "role": "hook", "risks": ["..."], "usable": true, "reject_reason": null, "in": 4.2, "out": 11.8}}
```

## 5. calibrate.py — hiệu chỉnh ngưỡng

```bash
python3 tools/calibrate.py sample <dự án> [--n 40]     # chọn mẫu trải đều (70% máy chính, 20% POV, 10% điện thoại)
python3 tools/calibrate.py page   <dự án>              # → analysis/calib/cham.html (ảnh nhúng sẵn)
python3 tools/calibrate.py fit    <dự án> answers.json # → tools/thresholds.json + analysis/calib/report.md
python3 tools/shots.py <dự án> --force                 # đo lại với ngưỡng mới
```
Trang chấm lưu trong trình duyệt (localStorage) và có nút "Tải answers.json". Đăng trang lên claude.ai thành Artifact
có capability `db` thì kết quả tự lưu vào collection `answers` để Claude đọc thẳng.

## Bẫy đã gặp

- **Vật lớn chạy qua khung** (tàu, xe, người đi sát máy) làm optical flow tưởng máy quay đang chuyển động → Claude sửa ở lượt 2.
- **POV** gần như luôn "đi tới / quay đầu"; DOF và rig chỉ có nghĩa với máy chính.
- **Ổ đầy** làm tiến trình đo sập giữa chừng: kiểm `df -h ~` (khúc tạm nằm ở `~/.tls_cache`).
- **mediapipe**: tạo lại bộ nhận diện cho mỗi khúc gây rò bộ nhớ → shots.py giữ một bộ cho mỗi tiến trình. Bản mediapipe mới
  (≥0.10.30) đã bỏ `mp.solutions` → cần Python ≤3.12 + `mediapipe==0.10.14` để có độ chính xác tốt nhất.
- **Shell giới hạn thời gian mỗi lệnh** (máy ảo của ứng dụng Claude): luôn chạy với `timeout 175 … --budget 140` và lặp lại;
  file chuyển qua lại giữa máy ảo và máy thật có thể bị giao bản cũ khi dùng lại cùng đường dẫn → đổi tên file tạm, kiểm `md5sum`.
- Đường dẫn có dấu cách: luôn đặt trong ngoặc kép.
