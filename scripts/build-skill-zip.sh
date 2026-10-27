#!/usr/bin/env bash
# Đóng gói skill thành dist/footage-logging.zip để tải lên Claude (Customize → Skills → Upload a skill).
# Trong zip là thư mục footage-logging/ (tên thư mục phải khớp "name" trong SKILL.md).
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
NAME=$(sed -n 's/^name: *//p' SKILL.md | head -1)
TMP=$(mktemp -d); mkdir -p "$TMP/$NAME" dist
cp SKILL.md LICENSE "$TMP/$NAME/"
cp -R tools docs calib "$TMP/$NAME/"
rm -rf "$TMP/$NAME/docs/assets" "$TMP/$NAME/tools/__pycache__" "$TMP/$NAME/tools/thresholds.json"
find "$TMP/$NAME" -name '.DS_Store' -delete
rm -f "dist/$NAME.zip"; (cd "$TMP" && zip -qr "$ROOT/dist/$NAME.zip" "$NAME")
rm -rf "$TMP"; echo "→ dist/$NAME.zip ($(du -h "dist/$NAME.zip" | cut -f1))"
