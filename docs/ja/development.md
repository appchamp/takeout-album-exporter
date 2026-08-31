# GUI 開発ガイド

英語: [../en/development.md](../en/development.md)

この文書は、`Photo Date Restore.app` をソースからビルドする開発者向けです。配布済み `.app` を使うだけなら、Python/Tk/PyInstaller は不要です。利用者向けの操作は [usage.md](usage.md) を参照してください。

## 必要なもの

- Python 3.14 + Tk
- PyInstaller
- ExifTool（実行時の外部依存）

macOS では、`python-tk@3.14` を Homebrew で導入すると、依存として `python@3.14` と `tcl-tk` も導入されます。

```bash
brew install python-tk@3.14
brew install exiftool
```

## GUI 用環境とビルド

リポジトリのルートで外部 GUI 環境 `$HOME/.venvs/takeout-album-exporter/gui` を用意し、インストール済み package metadata を更新してからビルドします。

```bash
"$HOME/.venvs/takeout-album-exporter/gui/bin/pip" install -e . --no-deps
"$HOME/.venvs/takeout-album-exporter/gui/bin/pyinstaller" --noconfirm packaging/photo-date-restore-gui.spec
```

生成物は `dist/Photo Date Restore.app` です。spec は `packaging/photo-date-restore-gui.spec` を使います。

`.app` の About 表示と bundle version（`CFBundleShortVersionString` / `CFBundleVersion`）はインストール済み package metadata から取得します。version を変更した場合は、ビルド前に必ず上記の editable install を再実行してください。

起動した `.app` は ExifTool を同梱せず、`PATH`、`/opt/homebrew/bin`、`/usr/local/bin` を順に検索します。

配布 ZIP の作成、検証、手動 GUI テストは [release.md](release.md) を参照してください。
