# Footage Logging

Claude Skill log & lọc source quay cho dự án NEX Picture: QC kỹ thuật từng giây, bóc băng, mô tả từng clip, đánh dấu đoạn hay / đoạn loại, xuất bảng log như một assistant editor.

## Quy trình

| Bước | Công cụ | Kết quả |
|---|---|---|
| 1. QC kỹ thuật | `tools/analyze.py` | cờ tối / cháy / mờ / rung / lia cho từng giây, đoạn dùng được, điểm chất lượng 0–10, contact sheet 6 khung, phát hiện file hỏng |
| 2. Bóc băng | `tools/transcribe.mjs` (Whisper small, offline) hoặc `tools/mac_whisper.sh` (mlx-whisper large-v3-turbo trên Mac chip M) | transcript có timecode, tự nhận tiếng Việt / tiếng Anh |
| 3. Xem & mô tả | `tools/review.py pages` + Claude đọc contact sheet | notes từng clip: mô tả, bối cảnh, người, tag, highlight (giây, lý do, điểm), lý do loại |
| 4. Bảng log | `tools/review.py log` | `clip_log.html` (có ảnh), `clip_log.csv`, `clip_log.json` |

Kết quả ghi vào `<dự án>/_SOCIAL/analysis/`. Skill `tro-ly-social` đọc lại bảng log này để dựng video.

## Cấu trúc

```
SKILL.md            # skill nạp vào Claude
tools/
  analyze.py        # quét metadata + QC kỹ thuật + contact sheet
  transcribe.mjs    # Whisper small ONNX offline (máy ảo Linux)
  mac_whisper.sh    # cài & chạy mlx-whisper trên Mac Apple Silicon
  mac_transcribe.py # script Python mà mac_whisper.sh gọi
  review.py         # trang ảnh cho AI xem + gộp bảng log
  setup_vm.sh       # chuẩn bị máy ảo mỗi phiên
docs/pipeline.md    # lệnh chi tiết + các bẫy kỹ thuật đã gặp
```

## Cài đặt

- **Skill:** lưu nội dung `SKILL.md` qua giao diện Claude (Settings → Skills).
- **Công cụ:** hiện skill gọi bộ công cụ tại `/Volumes/NEX4/Tai Nguyen/TroLySocial/tools`. Repo này giữ bản sao các script liên quan tới log; khi sửa script thì cập nhật cả hai nơi.
- Yêu cầu: `ffmpeg`, Python 3 (`opencv-python-headless`, `numpy`, `pillow`), Node 18+ (`@huggingface/transformers`, `sts-whisper-small` — `setup_vm.sh` tự cài).
