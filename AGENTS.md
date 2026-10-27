# AGENTS.md — footage-logging

## Dự án
Skill Claude "Footage Logging" (log & lọc source quay) của NEX Picture, kèm các script nó dùng. Tách ra từ skill `tro-ly-social` ngày 27/10/2026.

## Quy ước
- `SKILL.md` frontmatter `name: footage-logging`, phải khớp tên skill trên tài khoản Claude.
- Script gốc đang chạy thật nằm ở `/Volumes/NEX4/Tai Nguyen/TroLySocial/tools`; sửa ở đâu thì đồng bộ sang nơi kia và ghi nhật ký ở cả hai AGENTS.md.
- Không commit footage, transcript, notes của dự án khách, `node_modules`, model Whisper, API key.

## Việc còn mở
- `tools/local_describe.py` (AI local Ollama + Qwen2.5-VL mô tả clip trên Mac): chưa viết, chờ cấu hình Mac (chip/RAM).

## Nhật ký thay đổi
### 2026-10-27 — Khởi tạo repo
- SKILL.md từ tài khoản Claude; tools: analyze.py, transcribe.mjs, review.py, setup_vm.sh, mac_whisper.sh, mac_transcribe.py; docs/pipeline.md (sao từ TroLySocial).
- Thêm README.md, AGENTS.md, .gitignore.
