# 写真日時・メタデータ修復ツール（Google フォトの Google Takeout データ）

English: [README.md](README.md)

Version 1.1.0 / MIT License / <https://github.com/kimipooh/takeout-album-exporter>

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

## 主な機能

- Google フォトの写真・動画について、sidecar JSON と既存 EXIF/XMP を照合して撮影日時と filesystem `mtime` を復元
- dry-run が既定。実際の書き込みは `--apply` を明示したときだけ
- 元データを変更しない copy mode 主体（GUI は copy mode 専用）
- 逐次出力（verbose）でファイルごとの処理結果を利用者向けの説明として表示
- 監査 report（CSV / JSONL）に内部 status を保存
- 根拠のある timezone だけを使う安全側の timezone 処理
- ExifTool による metadata の読み書きと読み戻し検証
- macOS GUI（`.app` 配布あり）、処理中の Cancel、About ダイアログ

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

### 逐次出力（verbose）

`-v` / `--verbose` を追加すると、dry-run を含め処理したファイルごとに 1 行ずつ利用者向けの説明を表示します。指定しない場合の出力は従来どおり最終集計のみです。

### 監査 report

`--report` で CSV / JSONL の監査 report を保存できます。report には内部 status（`EXIF_JSON_MATCH_TZ_GPS`、`JSON_TIME_MTIME_ONLY` など）がそのまま記録されます。verbose の画面表示は利用者向けに言い換えた説明であり、report の内部 status とは別物です。後から結果を検証するときは report を参照してください。

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

画面の項目は次のとおりです。

- `Input folder` / `Output folder`
- `Dry run (analyze only, write nothing)` — **既定 ON**
- `Verbose output (show each processed file)` — **既定 ON**
- `Overwrite existing files in output folder`
- 監査 report の保存（CSV / JSONL）
- `Start` / `Cancel`
- `Open Output Folder`

`Input folder` と `Output folder` を選び、既定で有効な Verbose output と dry-run、timezone、既存出力の上書き、監査 report（CSV / JSONL）を設定して `Start` を押します。ExifTool の metadata read はディレクトリごとに最大100件ずつのバッチで行われるため、ログには `[100/1896] Reading metadata...` のような読み込み進捗が表示され、その後 `Analyzing:` に切り替わってから dry-run でもファイル単位の利用者向け説明が表示されます。`Cancel` は次のバッチ境界（metadata read は概ね1バッチ以内）または書き込み中の現在のファイルの完了後に反応し、確定済みの部分結果と監査 report は保持します。完了後の結果はメイン画面のログにそのまま表示され（別ウィンドウは出ません）、`Open Output Folder` で出力先を Finder に表示できます。

アプリメニューまたは Help メニューの About では、Version、著作者、MIT License、Project URL を確認できます。

GUI は copy mode 専用です。`--in-place` と `--move-json` は引き続き CLI 専用です。CLI の引数・動作は変更されず、引き続き完全に利用できます。

### ExifTool（外部依存）

ExifTool は本ツールの外部依存であり、`.app` には同梱していません。Homebrew などで別途インストールしてください。

```bash
brew install exiftool
```

起動時に次の順で ExifTool を自動検出します。

1. `PATH` 上の `exiftool`
2. `/opt/homebrew/bin/exiftool`（Apple Silicon の Homebrew）
3. `/usr/local/bin/exiftool`（Intel の Homebrew）

見つからない場合も GUI は起動し、`Start` 時に導入手順を案内して停止します。

### macOS アプリ（.app）のダウンロード

Apple Silicon 向けのビルド済み ZIP を GitHub Release に添付しています。

`Photo-Date-Restore-v1.1.0-macOS-Apple-Silicon.zip`

この `.app` は署名・公証を行っていません（unsigned / not notarized）。初回起動時に macOS のセキュリティ警告が表示されることがあります。その場合は「システム設定 > プライバシーとセキュリティ」から起動を許可してください。ExifTool は別途インストールが必要です。

### `.app` のビルド

GUI 開発用の `.venv-gui` で、リポジトリのルートから実行します。

```bash
./.venv-gui/bin/pip install -e . --no-deps
./.venv-gui/bin/pyinstaller --noconfirm packaging/photo-date-restore-gui.spec
```

生成物は `dist/Photo Date Restore.app` です。`dist/` は生成物のため Git 管理対象外です。

Release 用 ZIP の作成手順とチェックサムの取り方は [docs/ja/usage.md](docs/ja/usage.md) の「4.4 Release 用 ZIP の作成と検証」を参照してください。

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

## プロジェクト

<https://github.com/kimipooh/takeout-album-exporter>

## ライセンス

MIT License. Copyright (c) 2026 Kimiya Kitani. 詳細は [LICENSE](LICENSE) を参照してください。
