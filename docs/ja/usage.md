# photo-date-restore 利用マニュアル

English: [../en/usage.md](../en/usage.md)

この文書は日本語正本です。短い導入は [README-ja.md](../../README-ja.md)、設計・安全判断は [design.md](design.md) を参照してください。

## 1. まず守ること

Google Takeout 原本は別途保存し、最初から原本へ `--in-place --apply` を実行しないでください。通常は、元データを変えない `--output DIR` を使います。必ず次の順で進めます。

1. dry-run
2. report 確認
3. apply
4. 出力確認

`--apply` を指定しない限り dry-run です。メディア、EXIF/XMP、`mtime`、JSON、output directory は変更しません。ただし `--report` を指定した dry-run は report ファイルだけを作成します。

このツールは JSON `creationTime` やファイル名を撮影日時に使わず、根拠がない timezone を推測しません。timezone が不明なときも JSON `photoTakenTime` の UTC instant を使って `mtime` だけ修復できる場合があります。

## 2. インストール（macOS を主例に最初から）

以下のコマンドはすべて**リポジトリのルートで実行**します。最初に移動してください。

```bash
cd /path/to/takeout-photo-date-restorer
```

### 2.1 Python を確認する

```bash
python3 --version
```

`pyproject.toml` の `requires-python` は `>=3.9` です。Python 3.9 以上が必要です。macOS では、仮想環境を作る前は `python3` を使うのが確実です。

### 2.2 仮想環境を作成・有効化する

```bash
python3 -m venv .venv
source .venv/bin/activate

python --version
which python
```

有効化後の `which python` は通常 `.venv/bin/python` を示します。この状態では `python` を使います。

Windows の PowerShell では、同じリポジトリのルートで次を使います。

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2.3 ExifTool を導入する

macOS では Homebrew の例です。

```bash
brew install exiftool
exiftool -ver
```

ExifTool が未導入の場合、CLI は処理開始前に `ExifTool executable not found` で停止します。写真のメタデータ読取り・書込みを安全に行うために必要です。別の場所にある場合は `--exiftool PATH` でも指定できます。

### 2.4 パッケージをインストールして確認する

```bash
python -m pip install -e .
python -m photo_date_restore --help
```

`python -m photo_date_restore` がこのマニュアルの主たる起動方法です。仮想環境を有効化し忘れた場合も、リポジトリのルートで次のように確実に起動できます。

```bash
.venv/bin/python -m photo_date_restore --help
```

インストールにより `photo-date-restore` という console script も生成されますが、これは**インストール済みで、かつ現在の `PATH` から利用可能な場合の短縮形**です。動作確認は可能です。

```bash
photo-date-restore --help
```

ただし環境によっては `photo-date-restore: command not found` になるため、以降の例では `python -m photo_date_restore` を使います。

## 3. Quick Start: まずこれだけ

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

写真のコピー、EXIF/XMP の変更、`mtime` の変更は行われません。何をする予定かだけを確認します。report を確認してください。

### 本番実行

問題がなければ、同じ条件で `--apply` を付けます。

```bash
python -m photo_date_restore \
  "/path/to/Google Photos/Album" \
  --output "./output" \
  --report "./report.csv" \
  --apply
```

## 4. GUI 版（macOS）

GUI は既存 CLI の copy mode を操作するための画面です。CLI の引数や動作は変わらず、引き続き完全に利用できます。GUI では `--in-place` と `--move-json` を公開せず、これらは CLI 専用です。

### 4.1 必要なものと起動

Python 3.14 用 Tk と ExifTool が必要です。ExifTool は `.app` に同梱されません。

```bash
brew install python-tk@3.14
brew install exiftool

photo-date-restore-gui
# または
python -m photo_date_restore.gui
```

### 4.2 使い方

1. `Input folder` と `Output folder` を選びます。
2. 既定の `Dry run (analyze only, write nothing)` と、既定で有効な `Verbose output (show each processed file)` のまま最初に確認します。timezone、既存出力の上書き、CSV / JSONL の監査 report を設定します。
3. `Start` を押します。ExifTool の metadata read はディレクトリごとに最大100件ずつのバッチで行われるため、ログにはまず読み込み進捗（`Reading metadata: <dir>`、バッチごとの `[100/1896] Reading metadata...`）が表示され、その後 `Analyzing: <dir>` に切り替わってから dry-run を含むファイル単位の利用者向け説明が表示されます。詳細な内部 status は監査 report にそのまま残ります。途中で止めるときは `Cancel` を押します。次のバッチ境界（metadata read は概ね1バッチ以内）または書き込み中の現在のファイルの完了後に反応し、確定済みの部分結果と監査 report は保持されます。アプリメニューまたは Help メニューの About から Version、著作者、MIT License、Project URL を確認できます。
4. 完了・キャンセルの結果はメイン画面のログにそのまま表示されます（別ウィンドウは出ません）。続けて `Open Output Folder` で出力先を Finder に開けます。

### 4.3 `.app` のビルド

リポジトリのルートで GUI 開発用環境を使います。

```bash
./.venv-gui/bin/pip install -e . --no-deps
./.venv-gui/bin/pyinstaller --noconfirm packaging/photo-date-restore-gui.spec
```

`.app` は Version と Project URL をインストール済みパッケージの metadata から読み取ります。version を変更した後に再インストールを省くと、About に古い値が表示されるため、ビルド前に必ず再インストールします。

生成物は `dist/Photo Date Restore.app` です。起動した `.app` は ExifTool を同梱せず、`PATH`、`/opt/homebrew/bin`、`/usr/local/bin` を順に検索します。

再インストールは About の表示だけでなく、`.app` の bundle version（`CFBundleShortVersionString` / `CFBundleVersion`）にも効きます。これらは spec がインストール済み package metadata から読み取るため、version を変更したらビルド前に必ず再インストールしてください。

### 4.4 Release 用 ZIP の作成と検証

`dist/` は PyInstaller の生成物、Release 用 ZIP は配布物であり、いずれも Git 管理対象外です（`.gitignore` で除外済み）。ZIP はリポジトリのルートに作成し、commit せずに GitHub Release へ添付します。

ZIP の作成には macOS の `ditto` を使います。`zip` コマンドは拡張属性を落とすことがあるため使いません。

```bash
ditto -c -k --sequesterRsrc --keepParent \
  "dist/Photo Date Restore.app" \
  "Photo-Date-Restore-v1.1.0-macOS-Apple-Silicon.zip"
```

作成した ZIP は、展開して `.app` が起動することを確認します。

```bash
mkdir -p /tmp/photo-date-restore-test

ditto -x -k \
  "Photo-Date-Restore-v1.1.0-macOS-Apple-Silicon.zip" \
  /tmp/photo-date-restore-test
```

チェックサムを算出し、Release の説明へ記載します。SHA-256 を主たる整合性確認値とし、MD5 は補助的な照合値として扱います。

```bash
shasum -a 256 "Photo-Date-Restore-v1.1.0-macOS-Apple-Silicon.zip"
md5 "Photo-Date-Restore-v1.1.0-macOS-Apple-Silicon.zip"
```

ハッシュ値はビルドのたびに変わるため、README やこのマニュアルへ埋め込まず、Release の説明にだけ記載します。

配布物は Apple Silicon（arm64）向けです。署名・公証を行っていないため（unsigned / not notarized）、利用者側で初回起動を許可する操作が必要になる場合があります。

### 4.5 手動 GUI テストチェックリスト

- GUI を起動できる
- Input / Output folder を選択できる
- dry-run、既定 ON の Verbose output、timezone、出力上書き、監査 report の各切替を確認できる
- dry-run でも Verbose output で処理ファイルごとに利用者向け説明が 1 行表示され、内部 status は report に残る
- 大きめのディレクトリで metadata read の進捗（`Reading metadata:` → `Analyzing:`）が長時間無表示にならず表示される
- Cancel が次のバッチ境界（metadata read は概ね1バッチ以内）または現在のファイルの完了後に安全に停止し、部分結果と report を保持する
- 正常完了・Cancel 完了時に別ウィンドウ（popup）が出ない
- アプリメニューまたは Help メニューの About で Version、著作者、MIT License、Project URL を確認できる
- ExifTool がある場合にパスがログへ表示される
- ExifTool がない場合に起動は継続し、Start 時に分かりやすく失敗する
- dry-run で Start して出力を作成しない
- apply で Start して copy mode の出力を確認する
- 不正な入力後もエラー表示から Start を再試行できる
- 成功後に `Open Output Folder` が有効になり Finder を開く

## 5. `--output` と dry-run / apply

`INPUT` に加えて、`--output DIR` または `--in-place` の一方が必須です。

```text
python -m photo_date_restore INPUT (--output DIR | --in-place) [OPTIONS]
```

`--output DIR` は推奨モードです。

- 入力の元データを変更しません。
- `--apply` 時に、入力からの相対パスを保って修復済みメディアコピーを別フォルダへ作成します。
- dry-run 時は output を指定していても、実際の output directory やメディアは作られません。
- sidecar JSON は copy mode の出力へコピーしません。

元 Takeout を保護したい場合はこのモードを選びます。apply では conflict 等で修復しないメディアも、そのままコピーされる場合があります。既存出力が異なる場合は既定で `OUTPUT_EXISTS` となり、上書きしません。

主なオプションは次のとおりです。

| オプション | 役割 |
| --- | --- |
| `--output DIR` | 別フォルダへ出力。`--in-place` と排他、推奨 |
| `--in-place` | 入力をその場で処理。作業コピーだけで使用 |
| `--apply` | 実際にコピー・書込み・移動を実行。未指定は dry-run |
| `-v`, `--verbose` | 処理したファイルごとに逐次行を表示 |
| `--timezone NAME` | IANA timezone 名（例 `Asia/Tokyo`） |
| `--report PATH` | CSV または JSONL の監査 report |
| `--move-json DIR` | 成功 sidecar を退避（`--in-place` 専用） |
| `--exiftool PATH` | ExifTool の実行ファイルを明示 |

dry-run 中にファイル単位の進行を表示するには、`-v` または `--verbose` を追加します。

```bash
python -m photo_date_restore \
  "/path/to/Google Photos/Album" \
  --output "./output" \
  -v
```

## 6. timezone を安全に扱う

JSON `photoTakenTime.timestamp` は UTC の絶対時刻です。一方、`DateTimeOriginal` は通常 timezone を持たないローカル時刻です。UTC の数字をそのまま書くと、撮影時刻を数時間ずらすおそれがあります。

### 指定が不要な場合

既存 EXIF の offset、GPS UTC 時刻、または同じディレクトリの十分な根拠から timezone を安全に判断できる場合です。既存の信頼できる撮影日時は JSON で上書きしません。

### 指定が必要な場合

EXIF 撮影日時がなく、JSON `photoTakenTime` だけがあり、撮影地が分かっている場合です。たとえば日本で撮影したことが明確な場合の手順です。

#### テスト実行（dry-run）

```bash
python -m photo_date_restore \
  "/path/to/Album" \
  --output "./output" \
  --timezone Asia/Tokyo
```

#### 本番実行

report を確認後、問題がなければ同じ条件で `--apply` を付けます。

```bash
python -m photo_date_restore \
  "/path/to/Album" \
  --output "./output" \
  --timezone Asia/Tokyo \
  --apply
```

### 指定してはいけない場合

海外で撮影した写真が混ざり得る Google Photos 全体へ、根拠なく次を付けないでください。

```text
--timezone Asia/Tokyo
```

timezone が分からなければ指定せず、`JSON_TIME_MTIME_ONLY` を report で確認してください。apply しても、ローカル撮影日時メタデータは書かず `mtime` だけを修復する安全な結果になります。

## 7. `--in-place`（上級者向け）

**元の Google Takeout そのものへ最初から in-place 実行しないでください。** 先にバックアップを作るか、copy mode で作成した作業コピーを使います。

### テスト実行（dry-run）

```bash
python -m photo_date_restore \
  "/path/to/copied-photos" \
  --in-place
```

### 本番実行

```bash
python -m photo_date_restore \
  "/path/to/copied-photos" \
  --in-place \
  --apply
```

対話端末では確認が表示されます。自動処理で確認を省略する必要がある場合だけ `--yes` を追加します。ExifTool の書込み後は読み戻し検証が成功するまで `<file>_original` を保持し、検証失敗時は復旧して `VERIFY_FAILED` を report します。

## 8. report の読み方

最初に **`status` を見ます**。次に、その判断の根拠、予定した操作、日時を確認します。

| 列 | 最初に確認する理由 |
| --- | --- |
| `file` | 対象ファイル |
| `status` | 最終判断と次に取るべき対応 |
| `existing_datetime` | 既存の撮影日時 |
| `existing_datetime_source` | 既存日時のタグ・根拠 |
| `json_photo_taken_time` | JSON が示す UTC の絶対時刻 |
| `selected_datetime` | 採用した撮影日時。timezone 不明なら空欄の場合あり |
| `selected_datetime_source` | 採用元（既存タグまたは `PHOTO_TAKEN_TIME`） |
| `timezone_source` | `EXPLICIT`、`GPS`、`INFERRED`、`CLI`、`NONE` |
| `difference_seconds` | EXIF と JSON の差。`32400` は 9 時間 |
| `planned_metadata_action` | 例: `WRITE`、`SKIP_TIMEZONE_REQUIRED`、`NONE` |
| `planned_mtime_action` | `SET` なら apply 時に `mtime` を設定 |
| `new_mtime` | apply 時に設定予定の UTC absolute instant |

dry-run では `planned_*` 列と `new_mtime` を見ます。`--report` は `.csv` なら既定で UTF-8 BOM 付き CSV、`.jsonl` なら JSONL を出力します。

### status と利用者の対応

| status | 意味 | 利用者の対応 |
| --- | --- | --- |
| `NO_CHANGE` | 修正不要、または既に期待どおり | そのままでよい |
| `OK_EXIF` | 信頼できる既存日時があり JSON 時刻は使えない | 既存値を保持 |
| `EXIF_JSON_MATCH` | EXIF と JSON が許容範囲で一致 | 原則そのまま |
| `EXIF_JSON_MATCH_TZ_EXPLICIT` | 明示 offset または CLI timezone で整合 | 原則そのまま |
| `EXIF_JSON_MATCH_TZ_GPS` | EXIF と JSON が GPS による timezone 差で整合 | 原則そのまま |
| `EXIF_JSON_MATCH_TZ_INFERRED` | 同一ディレクトリの根拠で timezone 差が整合 | 原則そのまま |
| `EXIF_JSON_POSSIBLE_TZ` | timezone 差らしいが独立根拠が弱い | 既存値を保持し、必要なら確認 |
| `EXIF_JSON_CONFLICT` | 日時が安全に説明できない | apply 前に確認。自動修正しない |
| `JSON_TIME_USED` | JSON から安全に復元可能 | apply 候補 |
| `JSON_TIME_MTIME_ONLY` | timezone 不足のため metadata を書けない | 撮影地が確かなら timezone 指定。不要なら mtime のみ apply 可 |
| `NO_JSON` | 対応 sidecar がない | 配置・退避済みかを確認 |
| `NO_DATE` | 信頼できる既存日時も `photoTakenTime` もない | 手動確認。`creationTime` は使わない |
| `AMBIGUOUS_JSON` | JSON 対応が一意でない | 自動修正しない |
| `OUTPUT_EXISTS` | 異なる出力先ファイルがある | 出力を比較し、安易に上書きしない |
| `VERIFY_FAILED` | 書込み後の検証に失敗 | `error` を確認。in-place は復旧対象 |
| `ERROR` | JSON 破損、I/O 等の処理エラー | `error` と `message` を確認して原因を直す |

`UNSUPPORTED` と `SKIPPED` は enum にありますが、現行の通常処理では原則として出ません。HEIC/動画等の metadata 書込み非対応は通常 `message` の `UNSUPPORTED_FORMAT_FOR_METADATA(...)` で示されます。

## 9. 実データの例（読み取り専用）

次の `sources/Takeout/...` は開発サンプルです。一般利用者は自分のパスに置き換えてください。これらへ `--in-place --apply` は実行しません。

### サンプルアルバムA

#### テスト実行（dry-run）

```bash
python -m photo_date_restore \
  "sources/Takeout/Google フォト/サンプルアルバムA" \
  --output "./test-output/group-photo" \
  --report "./reports/group-photo.csv"
```

timezone を確定できない場合は `JSON_TIME_MTIME_ONLY` となり、撮影日時メタデータを変更せず `mtime` のみを復元します。

#### 本番実行（日本で撮影したことが分かっている場合のみ）

```bash
python -m photo_date_restore \
  "sources/Takeout/Google フォト/サンプルアルバムA" \
  --output "./test-output/group-photo" \
  --timezone Asia/Tokyo \
  --report "./reports/group-photo-apply.csv" \
  --apply
```

### サンプルアルバムB

```bash
python -m photo_date_restore \
  "sources/Takeout/Google フォト/サンプルアルバムB" \
  --output "./test-output/library-fair" \
  --report "./reports/library-fair.csv"
```

`EXIF_JSON_MATCH_TZ_GPS` は GPS 由来の timezone 根拠で既存日時と JSON が整合したことを、`EXIF_JSON_MATCH_TZ_INFERRED` は同一ディレクトリの根拠から整合したことを示します。

ここでは既存 EXIF/XMP 撮影日時を上書きしません。

### Google Photos 全体

まず dry-run します。

```bash
python -m photo_date_restore \
  "sources/Takeout/Google フォト" \
  --output "./test-output/google-photos" \
  --report "./reports/google-photos.csv"
```

ここでは原則 timezone を指定しません。report を見て、撮影地が確かなアルバムだけを分けて判断します。

## 10. `--move-json`（上級者向け）

`--move-json` は in-place 専用で、JSON の削除ではなく退避です。入力外かつリポジトリの `sources/` 外の退避先を指定します。

### テスト実行（dry-run）

```bash
python -m photo_date_restore \
  "/path/to/copied-photos" \
  --in-place \
  --move-json "/path/to/json-backup"
```

### 本番実行

```bash
python -m photo_date_restore \
  "/path/to/copied-photos" \
  --in-place \
  --move-json "/path/to/json-backup" \
  --apply
```

- 完全に成功したメディアの、一意に対応した sidecar だけを退避します。
- conflict、`ERROR`、`AMBIGUOUS_JSON`、`JSON_TIME_MTIME_ONLY` 等は移動しません。
- 退避先では INPUT からの相対パスを保持し、`_sidecar_index.csv` を作成します。
- JSON は削除しません。退避後に元 INPUT を再走査すると sidecar がないため `NO_JSON` になります。
- 退避先の衝突は上書きせず、`planned_json_action=SKIP_DESTINATION_EXISTS` と記録します。

## 11. よくあるエラー

### `photo-date-restore: command not found`

console script が PATH にありません。次を実行してください。

```bash
source .venv/bin/activate
python -m photo_date_restore --help
```

### `No module named photo_date_restore`

リポジトリのルートにいることを確認し、パッケージを入れます。

```bash
python -m pip install -e .
```

### ExifTool not found

macOS では導入して確認します。

```bash
brew install exiftool
exiftool -ver
```

### `invalid IANA timezone`

`Asia/Tokoyo` は誤りです。正しくは次です。

```text
Asia/Tokyo
```

### output が作られない

dry-run では正常です。実際に output を作成するには、report 確認後に同じコマンドへ `--apply` を付けます。

## 12. 最も安全な利用例

1. Google Takeout 原本を別途保存する。
2. リポジトリへ移動する。
3. `.venv` を作成して有効化する。
4. ExifTool を確認する。
5. `python -m pip install -e .` を実行する。
6. アルバム 1 つで dry-run する。
7. report を確認する。
8. 必要なら、その撮影地が確かなアルバムだけに timezone を指定する。
9. `--output --apply` で修復済みコピーを作る。
10. 出力写真・report・`mtime` を確認する。
11. 問題がなければ対象範囲を広げる。
