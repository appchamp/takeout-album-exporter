# Changelog

## v1.1.0 (2026-08-29)

### 追加

- CLI `-v` / `--verbose` による利用者向け説明のファイル単位逐次出力（未指定時の出力と終了コードは不変）
- GUI の既定 ON の Verbose output、cooperative Cancel、処理中の終了確認
- Version・著作者・MIT License・Project URL を表示する About ダイアログ
- macOS 向け Tkinter GUI（`photo-date-restore-gui` / `python -m photo_date_restore.gui`）。copy mode 専用で、dry-run・timezone・出力上書き・監査 report を設定できる
- `Photo Date Restore.app` を再現可能にビルドする PyInstaller の spec。ExifTool は同梱せず外部依存のまま
- GUI へ進行状況を通知するための、pipeline のディレクトリ単位の任意 progress コールバック（CLI の挙動は不変）
- GUI へ読み込み開始を通知する、pipeline のディレクトリ単位の任意 directory_start callback（CLI の挙動は不変）
- 解析フェーズの進捗を通知する、pipeline のディレクトリ単位の任意 analysis_progress コールバック（CLI の挙動は不変）
- GUI 起動時の ExifTool 自動検出（`PATH` → `/opt/homebrew/bin` → `/usr/local/bin` の順。未検出時も GUI は起動し、Start 時に導入手順を案内して停止）
- GUI の入力パスの `~` 展開と、出力先を Finder で開く `Open Output Folder`
- `.app` の bundle version（`CFBundleShortVersionString` / `CFBundleVersion`）と著作権表記を、インストール済み package metadata から設定

### 変更

- audit report の内部 status は保持したまま、verbose 表示だけを利用者向けの説明へ変更
- Cancel 時も確定済みの部分結果を保持し、指定時は監査 report を保存
- ExifTool metadata read をディレクトリ単位の一括読み取りから50件ずつのバッチ読み取りへ変更。判定（TZ_INFERRED 等の sibling offset 推定を含む）は従来通りディレクトリ全体の metadata が揃ってから実行し、結果は変わらない
- GUI へ metadata read の進捗（`Reading metadata:` → `Analyzing:`）を表示する任意の metadata_progress コールバックを追加（CLI の挙動は不変）
- Cancel がバッチ境界でも反応するようになり、大きなディレクトリでの Cancel 待ち時間を短縮
- GUI の progress bar を、metadata read・解析の進捗に応じて indeterminate から determinate へ切り替えるよう変更
- GUI の正常完了・Cancel 完了時の別ウィンドウ（popup）通知を廃止し、メイン画面のログ・status に一本化（エラー時の dialog は維持）

### 修正

- `--version` を単独で指定したときに、必須の `input` と `--output` / `--in-place` を求めるエラーで終了していた問題を修正（他の引数と併用したときの挙動は不変）

### ドキュメント

- `README-ja.md`を日本語正本として新設し、`README.md`をその英訳として整理
- 利用マニュアルと設計書を`docs/ja/`・`docs/en/`へ分離し、旧`docs/design.md`は互換案内として維持
- 実CLIに照合したQuick Start、実データdry-run例、report/status、timezone、in-place、JSON退避、安全な推奨ワークフローを追加
- README と利用マニュアルを利用者向けに整理し、GUI の配布版と CLI の必要ソフトウェアを明確化
- GUI のソースビルドと maintainer 向けリリース手順を別ドキュメントへ分離し、Release ZIP を `release/` フォルダへ配置

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
