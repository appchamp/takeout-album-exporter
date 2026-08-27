# photo-date-restore

Google Takeout でエクスポートした Google フォトの写真・動画について、失われた
「撮影日時」メタデータと `mtime` を、Takeout の JSON sidecar（`*.supplemental-metadata.json`
等）を根拠に **安全に** 復元する Python CLI ツールです。

設計の詳細・判断根拠は [`docs/design.md`](docs/design.md) を参照してください。
本 README は利用者向けの最小限の使い方と注意事項をまとめたものです。

## これは何をするツールか

1. 指定フォルダ以下を再帰的に走査し、写真・動画と Google Takeout の JSON sidecar を対応付ける
2. 既存の EXIF / XMP と JSON `photoTakenTime` を照合し、矛盾がないか確認する
3. 信頼できる撮影日時を決定し、必要な場合のみメタデータへ書き込む
4. ファイルシステムの `mtime` を撮影日時に修正する
5. すべての判断を監査レポート（CSV / JSONL）に残す

## 基本方針（重要）

- **既存の EXIF を最優先します。** EXIF が既にある場合、このツールはそれを書き換えません。
  JSON とは照合のみ行い、矛盾があれば `EXIF_JSON_CONFLICT` として記録し、書き込みません。
- **JSON `photoTakenTime` は、EXIF が無い場合の復元元です。** EXIF がある写真ではこの値で
  上書きすることはありません。
- **JSON `creationTime` は v1.0 では撮影日時の復元に使用しません。** これは実データ調査の結果、
  「一括アップロード日時」に近い値であり撮影日時ではないことが確認されているためです
  （読み取り・レポート表示のみ行います。将来のオプション機能として設計だけ残しています）。
- **既定は dry-run です。** 実際にファイルへ書き込むには `--apply` を明示的に指定する必要があります。
- **タイムゾーンは推測しません。** 撮影地のタイムゾーンは実行環境のタイムゾーンと一致するとは
  限らないため、システムのローカルタイムゾーンを既定値として使うことはありません。
  タイムゾーンが十分な根拠（EXIF の明示的なオフセット、GPS、同一アルバム内の複数ファイルからの
  推定、または `--timezone` の明示指定）で確定できない場合、**ローカル日時メタデータの書き込みは
  スキップし、`mtime` のみを復元します**（status: `JSON_TIME_MTIME_ONLY`）。JSON の
  `photoTakenTime` は UTC の絶対時刻なので、タイムゾーンが不明でも `mtime` の復元には使えます。
- **JSON sidecar を削除しません。** `--move-json` で退避することはできますが、削除機能はありません。

## 動作要件

- Python 3.9 以上
- [ExifTool](https://exiftool.org/)（`brew install exiftool` などで別途インストールが必要です）

## インストール

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 使い方

### copy mode（推奨）

原本には一切触れず、別フォルダへ復元済みのコピーを出力します。

```bash
# 1. まず何が起きるか確認する（既定 dry-run。何も書き込まれません）
photo-date-restore INPUT --output OUTPUT --report report.csv

# 2. 問題なければ実行する
photo-date-restore INPUT --output OUTPUT --apply --report report.csv

# 3. タイムゾーンを明示する（推奨。EXIF/GPS から確定できないファイルを救済します）
photo-date-restore INPUT --output OUTPUT --apply --timezone Asia/Tokyo
```

`python -m photo_date_restore INPUT --output OUTPUT` の形式でも同様に実行できます。

copy mode では:

- 原本（INPUT）は一切変更しません
- OUTPUT には写真・動画本体のみをコピーします（JSON sidecar はコピーしません。
  原本側の JSON はそのまま残ります）
- OUTPUT に同名ファイルが既にあり、かつ内容が既に正しい場合は再書き込みしません（`NO_CHANGE`）
- 何度実行しても安全です（idempotent）

### in-place mode（注意が必要）

原本を直接書き換えます。**事前に必ず別媒体へバックアップしてください。**

```bash
photo-date-restore INPUT --in-place --apply --timezone Asia/Tokyo
```

- `--in-place` の明示指定と `--apply` の両方が必須です（うっかり上書きを防ぐため）
- 対話端末では確認プロンプトが出ます（`--yes` で省略可）
- 書き込みは ExifTool の `_original` バックアップ方式を使い、読み戻し検証に成功して初めて
  バックアップを削除します。検証に失敗した場合はバックアップから自動的に復旧します
- JSON sidecar は既定では移動しません

正常完了して一意に対応した sidecar だけを退避する場合は、`--move-json DIR` を指定します。
このオプションは in-place mode 専用で、dry-run では移動予定だけをレポートし、`--apply` 時のみ
入力からの相対パスを保って移動します。実際に移動できた対応は、退避先ルートの
`_sidecar_index.csv`（UTF-8、BOM なし）へ記録されます。既存行は保持され、同じ対応は重複しません。
移動先に同名ファイルがある場合は上書きせずスキップし、index にも成功行として記録しません。
退避後に同じ INPUT を再走査すると sidecar は元位置にないため、そのメディアは `NO_JSON` になります。

```bash
photo-date-restore INPUT --in-place --apply --move-json /backup/json --timezone Asia/Tokyo
```

## レポート

`--report report.csv`（または `.jsonl`）で、ファイルごとの判断根拠（どの JSON と対応付いたか、
既存日時と JSON の差分、採用した日時とその根拠、実施した/計画した操作、`status` 等）を出力します。
JSON 退避を指定した場合は `planned_json_action` と `planned_json_destination` も記録します。
CSV は Excel での文字化けを避けるため UTF-8 BOM 付きで出力します（`--csv-no-bom` で無効化可）。

## タイムゾーンの決定ロジック

以下の順で信頼度が高いものを採用します。上位が確定できない場合のみ下位を試します。

1. EXIF の明示的なオフセットタグ（`OffsetTimeOriginal` 等）
2. 本体の `GPSDateTime` と撮影日時の差から算出したオフセット
3. 同一ディレクトリ内の複数ファイル（既定 3 件以上）で一貫して確認されたオフセット
4. `--timezone` の明示指定
5. 上記いずれでも確定できない場合 → **推測しません**。この場合、撮影日時メタデータの
   書き込みはスキップし、`mtime` のみを JSON の絶対時刻から復元します

## 対応ファイル形式（v1.0）

| 形式 | 解析 | mtime 復元 | メタデータ書き込み |
| --- | --- | --- | --- |
| JPEG / TIFF | ○ | ○ | ○ |
| PNG | ○ | ○ | ○（XMP 経由。実測で安全性を確認済み） |
| HEIC / MP4 / MOV 等 | ○ | ○ | × （将来 `--enable-heic` / `--enable-video` として opt-in 予定。実サンプル未検証のため v1.0 では非対応） |

## 既知の注意事項

- **macOS の birth time（作成日時）について**: `os.utime()` で `mtime` を過去に設定すると、
  APFS では副作用として birth time も自動的に引き下がることが実機で確認されています。
  ただし、これは Python の標準機能で明示的に制御しているものではなく、ファイルシステムや
  OS のバージョンによって挙動が異なる可能性があります。birth time を正確に制御する機能は
  v1.0 のスコープに含まれません。
- 元の Google Takeout データは、このツールを実行する前に **別途必ず保存しておいてください**。
  copy mode では原本は変更されませんが、in-place mode を使う場合は特に重要です。
- ExifTool が別途インストールされている必要があります。

## 開発

```bash
pip install -e ".[dev]"
pytest
```

`tests/` には sidecar マッチング・日時決定・タイムゾーン推定の単体テストに加えて、
`sources/Takeout`（読み取り専用）を使った受入テストが含まれます。受入テストは
`--output <tmpdir>` のみを使用し、原本を書き換えるテストは一時ディレクトリへコピーした
複製に対してのみ実行します。
