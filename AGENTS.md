# AGENTS.md — footage-logging

Hướng dẫn cho người (và agent) sửa repo này.

## Repo là gì
Claude Skill "Footage Logging": `SKILL.md` (Claude đọc) + `tools/` (script nó gọi) + `docs/pipeline.md` (tra cứu) +
`calib/template.html` (trang chấm hiệu chỉnh). Bản cộng đồng, không gắn đường dẫn hay dự án cụ thể nào.

## Quy ước
- `SKILL.md`: frontmatter `name: footage-logging` phải khớp tên thư mục khi đóng gói; mô tả < 1024 ký tự, không có `<` `>`.
- Script không bao giờ ghi vào ngoài `<dự án>/$FL_OUT/` (mặc định `_SOCIAL/`) và `~/.tls_cache`, `~/.tls_mlx`,
  `~/.footage-logging`. Không xoá, đổi tên, ghi đè source.
- Đổi thuật toán đo trong `shots.py` → tăng `VERSION`. Đổi ngưỡng mặc định → cập nhật bảng ngưỡng trong `docs/pipeline.md`.
- Không commit footage, transcript, notes, ảnh của dự án thật (kể cả trang chấm đã nhúng ảnh), `node_modules`, model, API key.
- Trước khi phát hành: chạy kiểm thử khói (README → "Kiểm thử nhanh"), `bash scripts/build-skill-zip.sh`, ghi `CHANGELOG.md`.

## Nhật ký
Xem [CHANGELOG.md](CHANGELOG.md).
