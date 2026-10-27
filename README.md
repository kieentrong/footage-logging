# Footage Logging

Claude Skill log & lọc source quay cho dự án NEX Picture: QC kỹ thuật từng giây, bóc băng, mô tả từng clip, đánh dấu đoạn hay / đoạn loại, xuất bảng log như một assistant editor.

## Quy trình

Ba tầng: **máy đo** (máy ảo Linux) → **AI local** (Mac chip M, miễn phí) → **Claude xem 2 lượt**. Bảng log mỗi dòng là một CẢNH.

| Bước | Công cụ | Kết quả |
|---|---|---|
| 1. Quét + QC thô | `tools/analyze.py` | thiết bị, proxy, cờ từng giây, file hỏng |
| 2. Đo từng cảnh | `tools/shots.py` | chia cảnh; optical flow → cách đặt máy (chân máy/gimbal/slider/cầm tay/POV), chuyển động (pan/tilt/push/pull/zoom/truck/pedestal/follow/roll, hướng, tốc độ); mediapipe → cỡ cảnh ECU→EWS, số người, bố cục, headroom, crop 9:16; nét, ổn định, phơi sáng, flicker, nhiễu, ám màu, vật cản, profile màu, slow-mo; âm thanh; mic rời khớp giờ; nhóm take; điểm KT + điểm đáng chú ý; contact sheet có chú thích |
| 3. Bóc băng + mô tả thô | `tools/mac_local.sh` (mlx-whisper large-v3-turbo + Qwen2.5-VL) hoặc nhấp đúp `tools/chay_ai_local.command` | transcript tiếng Việt chuẩn, `vlm/<clip>__sNN.json` |
| 4. Claude lượt 1 | `tools/review.py pages` | xem toàn cảnh, ghi notes theo cảnh |
| 5. Claude lượt 2 | `tools/review.py candidates` + `strip` | dải khung 0.4s: chốt in/out, sửa máy đoán sai, bắt rủi ro |
| 6. Bảng log | `tools/review.py log` | `clip_log.html` (có ảnh, lọc), `clip_log.csv` (~47 cột), `clip_log.json` |
| 7. Hiệu chỉnh | `tools/calibrate.py` + `calib/trang_cham.html` | anh chấm 40 cảnh → dò ngưỡng → `tools/thresholds.json` |

Kết quả ghi vào `<dự án>/_SOCIAL/analysis/`. Skill `tro-ly-social` đọc lại bảng log này để dựng video.

## Cấu trúc

```
SKILL.md                 # skill nạp vào Claude
tools/
  analyze.py             # quét metadata + QC thô
  shots.py               # đo theo từng cảnh (khúc 45s, song song, có cache)
  transcribe.mjs         # Whisper small ONNX offline (máy ảo, dự phòng)
  mac_local.sh           # Mac: cài + chạy mlx-whisper / mlx-vlm
  mac_whisper.sh         # Mac: mlx-whisper large-v3-turbo
  mac_transcribe.py      #   (mac_whisper.sh gọi)
  mac_describe.py        # Mac: Qwen2.5-VL mô tả thô từng cảnh
  chay_ai_local.command  # nhấp đúp để chạy phần Mac
  review.py              # pages / candidates / strip / log
  calibrate.py           # lấy mẫu + dò ngưỡng
  setup_vm.sh            # chuẩn bị máy ảo (opencv, mediapipe, Whisper small)
calib/trang_cham.html    # trang chấm (Artifact có db) — bản lưu
docs/pipeline.md         # lệnh chi tiết + các bẫy kỹ thuật đã gặp
```

## Cài đặt

- **Skill:** lưu nội dung `SKILL.md` qua giao diện Claude (Settings → Skills).
- **Công cụ:** hiện skill gọi bộ công cụ tại `/Volumes/NEX4/Tai Nguyen/TroLySocial/tools`. Repo này giữ bản sao các script liên quan tới log; khi sửa script thì cập nhật cả hai nơi.
- Yêu cầu máy ảo: `ffmpeg`, Python 3 (`opencv-python-headless`, `numpy`, `pillow`, `mediapipe==0.10.14`), Node 18+ (`@huggingface/transformers`, `sts-whisper-small`) — `setup_vm.sh` tự cài.
- Yêu cầu Mac: chip M, Python 3.9+; `mac_local.sh install` tạo `~/.tls_mlx`, lần đầu tải model ~6–7GB.
