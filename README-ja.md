# 写真日時・メタデータ修復ツール（Google フォトの Google Takeout データ）

English: [README.md](README.md)

Version 1.1.0 / MIT License / <https://github.com/kimipooh/takeout-album-exporter>

Google Photos Takeout から書き出した写真・動画について、Google の JSON メタデータと既存の EXIF/XMP 情報を参照し、欠けた撮影日時と filesystem `mtime` を安全に復元・調整する Python CLI ツールです。macOS 向けには、同じ機能を GUI から利用できる Apple Silicon 版 `Photo Date Restore.app` も提供しています。

[GUI 版の使い方](#gui-版macos) | [CLI 版の使い方](#quick-start)

- 詳細マニュアル（日本語正本）: [docs/ja/usage.md](docs/ja/usage.md)
- 開発者向け GUI ビルド: [docs/ja/development.md](docs/ja/development.md)
- maintainer 向けリリース手順: [docs/ja/release.md](docs/ja/release.md)
- 設計・安全仕様: [docs/ja/design.md](docs/ja/design.md)

## アプリ版（macOS Apple Silicon）の利用方法

1. [GitHub Release](https://github.com/kimipooh/takeout-album-exporter/releases) から Apple Silicon 版 ZIP をダウンロードします。
2. ZIP を展開します。
3. ExifTool を導入します: `brew install exiftool`
4. `Photo Date Restore.app` を起動し、まず dry-run で確認します。

配布済み `.app` には Python/Tk runtime が同梱されているため、利用者が Python、Tk、PyInstaller を導入する必要はありません。詳しくは [GUI 版](#gui-版macos) と [利用マニュアル](docs/ja/usage.md) を参照してください。

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

## 利用形態ごとの必須・推奨ソフトウェア

### macOS GUI 版を使う場合

- **必須**: ExifTool
- **不要**: Python、Tk、PyInstaller（配布済み `.app` には Python/Tk runtime を同梱）
- **推奨**: GitHub Release から Apple Silicon 版 ZIP を入手し、Homebrew で ExifTool を導入

### CLI 版を使う場合

- **必須**: Python 3.9 以上、ExifTool
- **推奨**: Python virtual environment、Homebrew 等による依存ソフトウェアの導入
- 詳細なオプション、安全な操作順、トラブルシュートは [利用マニュアル](docs/ja/usage.md) を参照してください。

### GUI 版をソースからビルドする場合

Python 3.14 + Tk、PyInstaller、GUI 用 virtual environment が必要です。一般利用者向けの操作ではありません。手順は [開発者向けドキュメント](docs/ja/development.md) を参照してください。

## Homebrew と ExifTool

ExifTool は GUI と CLI のどちらにも必要な外部依存で、`.app` には同梱していません。Homebrew は必須ではありませんが、macOS での推奨パッケージ管理手段です。未導入の場合は [Homebrew 公式サイト](https://brew.sh/) を参照してください。

```bash
brew install exiftool
exiftool -ver
```

GUI は起動時に `PATH`、`/opt/homebrew/bin`、`/usr/local/bin` の順で ExifTool を簡潔に探します。見つからない場合も GUI は起動し、`Start` 時に案内して停止します。

## Quick Start

CLI の最短手順です。以下は**リポジトリのルートで実行**します。

```bash
cd /path/to/takeout-photo-date-restorer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

### テスト実行（dry-run）

```bash
python -m photo_date_restore \
  "/path/to/Google Photos/Album" \
  --output "./output" \
  --report "./report.csv"
```

この段階では写真のコピー、EXIF 更新、mtime 変更は行われません。report を確認してください。

### 本番実行

dry-run の report を確認し、問題がなければ `--apply` を追加します。

```bash
python -m photo_date_restore \
  "/path/to/Google Photos/Album" \
  --output "./output" \
  --report "./report.csv" \
  --apply
```

`--output DIR` は元データを変更せず、`--apply` 時に修復済みコピーを別フォルダへ作成します。詳細は [利用マニュアル](docs/ja/usage.md) を参照してください。

### 逐次出力と監査 report

`-v` / `--verbose` を追加すると、dry-run を含め処理したファイルごとに 1 行ずつ利用者向けの説明を表示します。`--report` では CSV / JSONL の監査 report を保存でき、内部 status はそのまま記録されます。

## GUI 版（macOS）

配布済み `Photo Date Restore.app` を使う場合は ExifTool だけが必要です。ZIP を [GitHub Release](https://github.com/kimipooh/takeout-album-exporter/releases) から取得して展開し、`Photo Date Restore.app` を起動してください。Python/Tk は不要です。

この `.app` は unsigned / not notarized です。初回起動時に macOS の警告が表示される場合は、「システム設定 > プライバシーとセキュリティ」から起動を許可してください。

GUI は copy mode 専用です。`Input folder` と `Output folder` を選択し、既定 ON の dry-run と Verbose output、timezone、既存出力の上書き、監査 report を設定して `Start` を押します。`Cancel` は次の metadata-read バッチ境界または現在の書込み完了後に反応し、部分結果と監査 report を保持します。詳細は [利用マニュアルの GUI 章](docs/ja/usage.md#4-gui-版macos) を参照してください。

ソースから GUI を起動・ビルドする場合は、[開発者向けドキュメント](docs/ja/development.md) を参照してください。

## 安全上の注意

- 必ず **dry-run → report 確認 → apply → 出力確認** の順で進めてください。
- 元の Google Takeout そのものへ、最初から `--in-place --apply` を実行しないでください。`--in-place` はバックアップ済みの作業コピー向けです。
- `--timezone Asia/Tokyo` は、日本で撮影したことが明確なアルバムだけに指定します。海外写真を含む Takeout 全体には根拠なく指定しません。
- `--move-json` は上級者向けです。JSON を削除せず、成功した sidecar だけを退避します。

## 著作者

Kimiya Kitani

## プロジェクト

<https://github.com/kimipooh/takeout-album-exporter>

## ライセンス

MIT License. Copyright (c) 2026 Kimiya Kitani. 詳細は [LICENSE](LICENSE) を参照してください。
