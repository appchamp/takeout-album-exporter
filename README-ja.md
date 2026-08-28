# 写真日時・メタデータ修復ツール（Google フォトの Google Takeout データ）

English: [README.md](README.md)

Google Takeout から展開した Google フォトの写真や動画と sidecar JSON を安全に照合し、欠けた撮影日時と filesystem `mtime` を復元する Python CLI です。既存の信頼できる EXIF/XMP 撮影日時を優先し、必要な場合だけ JSON `photoTakenTime` を使います。

- 詳細マニュアル（日本語正本）: [docs/ja/usage.md](docs/ja/usage.md)
- 設計・安全仕様: [docs/ja/design.md](docs/ja/design.md)

## 概要

Google Takeout では、写真本体と撮影時刻が次のように分かれていることがあります。

```text
photo.jpg
photo.jpg.supplemental-metadata.json
```

本ツールは同じディレクトリ内の JSON を一意に対応付けます。既存の正しい撮影日時は上書きせず、根拠が不十分なときは推測で `DateTimeOriginal` を書きません。JSON の `creationTime` は撮影日時に使いません。

## インストール（macOS の例）

以下は**リポジトリのルートで実行**します。`/path/to/takeout-photo-date-restorer` は、このリポジトリを置いた場所へ置き換えてください。

```bash
cd /path/to/takeout-photo-date-restorer

python3 --version
python3 -m venv .venv
source .venv/bin/activate

python --version
which python

brew install exiftool
exiftool -ver

python -m pip install -e .
python -m photo_date_restore --help
```

`pyproject.toml` が要求する Python は **3.9 以上**です。仮想環境を有効化していない場合も、リポジトリのルートから `.venv/bin/python -m photo_date_restore` と実行できます。

`photo-date-restore` は、インストール時に作られる console script が現在の `PATH` から見つかる場合だけ使える短縮形です。マニュアルでは環境差の少ない `python -m photo_date_restore` を基本とします。

ExifTool がないと、CLI は処理開始前に停止します。macOS では上記の `brew install exiftool` で導入できます。

## Quick Start

そのままコピーして、パスだけ置き換えられます。

```bash
cd /path/to/takeout-photo-date-restorer

python3 -m venv .venv
source .venv/bin/activate

python -m pip install -e .
```

### テスト実行（dry-run）

まず、実際のファイルを変更せずに処理内容を確認します。

```bash
python -m photo_date_restore \
  "/path/to/Google Photos/Album" \
  --output "./output" \
  --report "./report.csv"
```

この段階では写真のコピー、EXIF更新、mtime変更は行われません。report を確認してください。

### 本番実行

dry-runのreportを確認し、問題がなければ `--apply` を追加して実行します。

```bash
python -m photo_date_restore \
  "/path/to/Google Photos/Album" \
  --output "./output" \
  --report "./report.csv" \
  --apply
```

`--output DIR` は元データを変更せず、`--apply` 時に修復済みコピーを別フォルダへ作成します。元 Takeout を保護したい場合の推奨モードです。詳細な手順、timezone、report、in-place、JSON 退避、エラー対処は [利用マニュアル](docs/ja/usage.md) を参照してください。

## GUI 版（macOS）

Tk を使える Python と ExifTool が必要です。macOS の Homebrew では次のように準備します。ExifTool はアプリに同梱されません。

```bash
brew install python-tk@3.14
brew install exiftool
```

パッケージをインストール後、次のいずれかで起動します。

```bash
photo-date-restore-gui
python -m photo_date_restore.gui
```

`Input folder` と `Output folder` を選び、必要に応じて dry-run、timezone、既存出力の上書き、監査 report（CSV / JSONL）を設定して `Start` を押します。ログでディレクトリごとの進行と結果を確認でき、完了後は `Open Output Folder` で出力先を Finder に表示できます。

GUI は copy mode 専用です。`--in-place` と `--move-json` は引き続き CLI 専用です。CLI の引数・動作は変更されず、引き続き完全に利用できます。

### `.app` のビルド

GUI 開発用の `.venv-gui` で、リポジトリのルートから実行します。

```bash
./.venv-gui/bin/pyinstaller --noconfirm packaging/photo-date-restore-gui.spec
```

生成物は `dist/Photo Date Restore.app` です。この `.app` に ExifTool は含まれません。起動時に `PATH`、`/opt/homebrew/bin`、`/usr/local/bin` の順で ExifTool を探します。

## 安全上の注意

- 必ず **dry-run → report 確認 → apply → 出力確認** の順で進めてください。
- 元の Google Takeout そのものへ、最初から `--in-place --apply` を実行しないでください。`--in-place` はバックアップ済みの作業コピー向けです。
- `--timezone Asia/Tokyo` は、日本で撮影したことが明確なアルバムだけに指定します。海外写真を含む Takeout 全体には根拠なく指定しません。
- `--move-json` は上級者向けです。JSON を削除せず、成功した sidecar だけを退避します。

## 代表的な利用例

開発サンプルは読み取り専用です。`sources/Takeout` に `--in-place --apply` は実行しないでください。

```bash
python -m photo_date_restore \
  "sources/Takeout/Google フォト/サンプルアルバムA" \
  --output "./test-output/group-photo" \
  --report "./reports/group-photo.csv"
```

timezone を確定できない場合は `JSON_TIME_MTIME_ONLY` となり、撮影日時メタデータは書き込まず `mtime` のみを復元します。日本撮影と確認済みの場合だけ、詳細マニュアルの `--timezone Asia/Tokyo --apply` 例を使います。

```bash
python -m photo_date_restore \
  "sources/Takeout/Google フォト/サンプルアルバムB" \
  --output "./test-output/library-fair" \
  --report "./reports/library-fair.csv"
```

`EXIF_JSON_MATCH_TZ_GPS` は GPS 由来の timezone 根拠で既存日時と JSON が整合したことを、`EXIF_JSON_MATCH_TZ_INFERRED` は同一ディレクトリの根拠から整合したことを示します。既存 EXIF/XMP は上書きしません。

詳しくは [docs/ja/usage.md](docs/ja/usage.md) を参照してください。

## 著作者

Kimiya Kitani

## ライセンス

MIT License. 詳細は [LICENSE](LICENSE) を参照してください。
