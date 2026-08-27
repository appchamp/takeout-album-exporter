# Changelog

## v1.0.0 (2026-08-27)

初版リリース。設計は [`docs/design.md`](docs/design.md) を参照。

### 追加

- `photo-date-restore` CLI（`python -m photo_date_restore` としても実行可能）
- JSON sidecar の逆引き索引によるメディア対応付け（`.json` / `.supplemental-metadata.json` /
  切り詰め / `(n)` 重複 / title 照合 / NFC・NFD 正規化に対応）
- EXIF/XMP と JSON `photoTakenTime` の照合、タイムゾーン差の根拠別判定
  （`EXIF_JSON_MATCH_TZ_EXPLICIT` / `_GPS` / `_INFERRED` / `EXIF_JSON_POSSIBLE_TZ`）
- タイムゾーン未確定時は撮影日時メタデータの書き込みをスキップし `mtime` のみ復元
  （`JSON_TIME_MTIME_ONLY`）。システムローカルタイムゾーンは既定値として使用しない
- JPEG/TIFF/PNG への `write_media_datetime()` による非破壊メタデータ書き込み + 読み戻し検証
- copy mode（既定・推奨）/ in-place mode（明示指定 + `--apply` 必須）
- dry-run 既定、`--apply` で実書き込み
- CSV（UTF-8 BOM 付き）/ JSONL 監査レポート
- idempotency（再実行で `NO_CHANGE` になること）
- `--move-json DIR` による、成功した一意sidecarのみの安全な退避（相対パス保持、dry-run表示、上書き禁止）

### v1.0 のスコープ外（将来機能として設計のみ残置）

- `--json-fallback creation-time`（JSON `creationTime` を撮影日時 fallback として使う機能）
- HEIC / 動画（MP4, MOV 等）へのメタデータ書き込み（`--enable-heic` / `--enable-video`）
- macOS birth time の明示制御
