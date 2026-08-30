# Google Takeout 写真・動画 撮影日時復元ツール 設計書

- 文書種別: 設計・保守仕様（日本語正本）
- 対象リポジトリ: `takeout-album-exporter`
- 状態: **v1.0 実装済み**。実装との差異は本書冒頭の「現行実装との対応」を優先する。
- 文字コード: UTF-8 (BOM なし)。本書は Codex CLI への実装引き継ぎ入力として機械処理されるため、`CLAUDE.md` の「機械処理される可能性が高い Markdown は BOM なし」規定を適用する。
- 実データ調査日: 2026-08-27
- 調査環境: macOS (Darwin 25.6.0, APFS), ExifTool 13.55, Python 3.9.6, ffmpeg あり

### 改訂履歴

| 日付 | 内容 |
| --- | --- |
| 2026-08-27 | 初版設計（実データ調査含む） |
| 2026-08-27（追補） | v1.0 実装に向けた方針修正: (1) §23-1 のタイムゾーン既定値を「システムローカル既定」から撤回し、根拠なき推測を禁止（§8.2, §23-1）。(2) `creationTime` fallback を v1.0 の実装対象外に確定し将来機能として明記（§7.1, §19.2）。(3) EXIF 書き込みを形式非依存の `write_media_datetime()` ディスパッチとして整理（§9.2, §20）。(4) `EXIF_JSON_MATCH_TZ` を根拠別に 4 分割（`_EXPLICIT` / `_GPS` / `_INFERRED` / `POSSIBLE_TZ`）し、単一ファイルの implied offset だけでは確定扱いにしないよう修正（§6.3, §15.3, §22.1）。この追補は前回設計の全面書き直しではなく、該当箇所のみの修正である。 |
| 2026-08-27（文書再編） | v1.0 実装・CLI・81テストに照合し、日本語正本として `docs/ja/` へ移設。利用方法は [`usage.md`](usage.md) へ分離し、未実装案を現行機能と区別した。 |

## 現行実装との対応

本書は初版の設計判断、実データ調査、将来案を情報を落とさず保持している。一方、実装後のモジュール構成やCLIは一部が当初案と異なる。現在利用できる操作は [`usage.md`](usage.md) と `photo-date-restore --help` を正とし、本書中の `--resume`、`--jobs`、`--json-fallback creation-time`、`--enable-heic`、`--enable-video`、`--add-offset`、`--edited-policy`、`--filename-date`、`albums.csv`、明示的なbirth time制御は、すべて未実装または将来案である。

現行v1.0の要点は次のとおり。

- 必須の排他的モードは `--output DIR` または `--in-place`。既定はdry-runで、実変更には `--apply` が必要。
- メタデータ書き込み対応はJPEG、TIFF、PNG。HEICと動画は解析・mtime対象になり得るが、メタデータ書き込みは未対応。
- `creationTime` は読み取りとレポート表示のみで、撮影日時には採用しない。
- reportの実列は `photo_date_restore/report.py` の `REPORT_COLUMNS`、statusの実名は `photo_date_restore/models.py` の `Status` が正である。
- `TIMEZONE_REQUIRED_FOR_METADATA` はstatusではなく `message` の理由コード、`SKIP_DESTINATION_EXISTS` は `planned_json_action` の値である。
- 実装は当初案の独立したapplier階層には分割せず、現在の `pipeline.py` を中心とする構成で安全要件を満たしている。構造を当初案へ合わせるための再設計は行わない。
- 複数の Takeout アルバムで検証した。現在の不変性確認は、作業前スナップショットの相対パス、ファイル数、合計バイト数、`mtime_ns`、SHA-256 を基準にする。

v1.0公開前の限定修正により、次の安全上の差異は解消済みである。

- `--timezone`は`zoneinfo.ZoneInfo`で処理開始前に検証し、無効なIANA名はCLIエラーとする。
- 対応名のsidecarが構文破損、読取り不能、必須値不正なら`NO_JSON`ではなく`ERROR`とし、原因をreportへ残してメディア・mtime・JSONを変更しない。
- dry-runで`planned_mtime_action=SET`なら、`new_mtime`へapply時に設定予定のUTC absolute instantを表示する。実ファイルのmtimeは変更しない。

次の差異は今回の対象外として維持する。

- `UNSUPPORTED`と`SKIPPED`はenumに存在するが、現行の通常pipelineでは原則としてstatusに出現しない。非対応メタデータ形式は`message`の`UNSUPPORTED_FORMAT_FOR_METADATA(...)`で示される。

利用者向けの安全原則、コマンド、report/statusの読み方は [`usage.md`](usage.md) を参照すること。

---

## 1. 目的

Google Takeout でエクスポートした Google フォトの写真・動画について、失われた「撮影日時」を **安全に** 復元する Python CLI ツールを提供する。

具体的には、指定フォルダ以下を再帰的に解析し、

1. メディアファイル（写真・動画）を検出する
2. 対応する Google Takeout JSON sidecar を **根拠を伴って** 対応付ける
3. メディア本体の既存メタデータ（EXIF / XMP / QuickTime）を読む
4. 既存メタデータと JSON を **照合** する
5. 「撮影日時」として信頼できる値を決定し、その **採用根拠（source）** を記録する
6. 必要な場合のみメタデータへ撮影日時を書き込む
7. ファイルシステム上の日時（mtime、可能なら birth time）を修正する
8. すべての判断と変更を監査可能なレポートに残す

### 1.1 設計上の最優先原則

```
1. 原本を壊さない
2. 推測で日時を書き換えない
3. EXIF があるなら尊重する
4. JSON で照合する
5. EXIF がなければ JSON から復元する
6. 判断できないものは CONFLICT として残す
7. JSON 原本を削除しない
8. dry-run 可能
9. 全変更を監査可能
10. 再実行可能（idempotent）
```

とりわけ次を **禁止事項** とする。

> 「日時が何か存在するからそれを使う」という実装は禁止。
> その日時が「撮影日時」「Google フォト登録日時」「ファイル編集日時」「Takeout 生成日時」のどれなのかを常に区別すること。

この禁止事項は抽象論ではない。§3 の実データ調査で、**撮影日時に見える偽の日時が実際に存在すること** を確認している（`XMP:MetadataDate`、`creationTime`、`FileModifyDate`）。

---

## 2. 非目的（このツールがやらないこと）

| 非目的 | 理由 |
| --- | --- |
| 元データの移動・削除・リネーム | GooglePhotosTakeoutHelper (以下 GPTH) は既定でファイルを移動するが、本ツールはこの設計を採用しない |
| 日付別フォルダへの再編成（`Photos from 2017/` → `2017/11/` 等） | 別ツール・別タスクの責務。日時復元と混ぜると事故時の切り分けが困難になる |
| 重複ファイルの検出・排除 | 同上。ハッシュ計算は高コストで、誤判定時の損害が大きい |
| アルバム構造の再構築・シンボリックリンク生成 | 将来タスク（リポジトリ名的には視野に入るが、初版スコープ外）。§23 未解決事項に記載 |
| GPS・説明文・人物タグの EXIF 書き戻し | 初版スコープ外。日時のみに絞る（§23-8 に将来提案として記載） |
| ファイル名からの日時推測を既定で行うこと | GPTH #436 で実害が報告されている（誤日付・1970-01-01 の混入）。既定 OFF |
| Takeout ZIP の解凍 | 利用者が事前に解凍済みであることを前提とする |
| Google フォトへの再アップロード | 対象外 |

---

## 3. 実データ調査結果

### 3.1 調査対象と実施方法

対象: `sources/Takeout/` 配下。**読み取り専用でのみ実施**した（`exiftool` の読み取り、`cat`、`os.walk`、`os.stat`）。書き込み挙動の検証は、スクラッチパッドへコピーした複製に対してのみ行っている。

> **注意（要判断・§23-10）**
> 調査中、Claude Code のシェル作業ディレクトリ追跡機能により、
> `sources/Takeout/.claude/.cc-writes/` と `sources/Takeout/Google フォト/.claude/.cc-writes/`
> という **空ディレクトリ 2 組** が自動生成された。中身は空でメディア・JSON には一切影響していないが、
> 「sources 配下を変更しない」原則には反する副産物である。削除を試みたが権限制御により拒否されたため、
> 利用者側での削除判断を仰ぐ（`rmdir` で消せる）。

### 3.2 全体構成

```
sources/Takeout/
└── Google フォト/
    ├── サンプルアルバムA/
    │   ├── IMG_0001.jpg   (+ .supplemental-metadata.json)
    │   ├── IMG_0002.jpg   (+ .supplemental-metadata.json)
    │   ├── IMG_0003.jpg   (+ .supplemental-metadata.json)
    │   ├── IMG_0004.jpg   (+ .supplemental-metadata.json)
    │   └── メタデータ.json          ← アルバムメタデータ（sidecar ではない）
    └── サンプルアルバムB/
        ├── IMG_0101.JPG … IMG_01NN.JPG (N 件) + IMG_0102.PNG (1 件)
        │   （各ファイルに .supplemental-metadata.json）
        └── メタデータ.json          ← アルバムメタデータ（sidecar ではない）
```

| 項目 | 値 |
| --- | --- |
| 総ファイル数 | 複数（作業前後で不変） |
| メディア | 複数 |
| JSON | メディア sidecar とアルバムメタデータ |
| 動画 | 検証対象に含まれない |
| HEIC | 検証対象に含まれない |
| アルバム | 複数 |

### 3.3 JSON sidecar の命名形式

- 検証サンプルでは `<元のファイル名フルネーム>.supplemental-metadata.json` 形式（例: `IMG_0101.JPG.supplemental-metadata.json`）を確認した。
- 拡張子の大文字・小文字は元ファイルと完全一致（`.JPG` は `.JPG`、`.jpg` は `.jpg`、`.PNG` は `.PNG`）。
- 切り詰め、duplicate suffix、Unicode 正規化の境界条件は、実データの有無にかかわらず合成フィクスチャで検証する。
- JSON 内の `"title"` はメディアの basename と照合する（`title == basename(media)`）。
- ファイル名・ディレクトリ名は NFC に正規化して比較する。実データだけでは NFD 問題を検出できない場合がある。

> **結論**: 実データは「素直なケース」しか含まない。truncation・duplicate・NFD・動画・HEIC は
> **合成フィクスチャで別途テストする必要がある**（§21）。

### 3.4 アルバムメタデータファイル

日本語ロケールの Takeout では `metadata.json` ではなく **`メタデータ.json`** という名前になる。

```jsonc
// サンプルアルバムA/メタデータ.json
{ "title": "サンプルアルバムA", "description": "", "access": "protected",
  "date": { "timestamp": "1704067200", "formatted": "2024/01/01 00:00:00 UTC" } }

// サンプルアルバムB/メタデータ.json
{ "title": "サンプルアルバムB" }
```

**重要**: これらは `title` を持つが `photoTakenTime` も `creationTime` も持たない（`date` は別キー）。
→ **「`photoTakenTime` または `creationTime` を持つことを sidecar の必要条件とする」だけで、ロケール名に依存せず確実に除外できる。** この判定規則は実データで検証済み（§5.1）。

### 3.5 `サンプルアルバムA` — EXIF 撮影日時なしのケース

| ファイル | EXIF 日時 | XMP | JSON photoTakenTime (UTC) | JSON creationTime (UTC) |
| --- | --- | --- | --- | --- |
| IMG_0001.jpg | **なし** | `XMP-xmp:MetadataDate = 2024:01:01 16:00:00+09:00` | 2024-01-01 00:00:00 | 2024-01-02 00:00:00 |
| IMG_0002.jpg | **なし** | `XMP-xmp:MetadataDate = 2024:01:01 16:01:00+09:00` | 2024-01-01 00:01:00 | 2024-01-02 00:00:00 |
| IMG_0003.jpg | **なし** | なし | 2024-01-01 02:00:00 | 2024-01-02 00:00:00 |
| IMG_0004.jpg | **なし** | なし | 2024-01-01 02:01:00 | 2024-01-02 00:00:00 |

判明した事実:

1. **`DateTimeOriginal` / `CreateDate` / `ModifyDate` がいずれも存在しない。** `Make` / `Model` もない。
   Adobe 製ソフトウェア（`XMPToolkit: Adobe XMP Core 7.0`）で書き出された際に EXIF が剥がれたと推定される。
   `IMG_0003.jpg` / `IMG_0004.jpg` に至っては **XMP も ICC も無く、日時系メタデータが完全にゼロ**。
2. **`XMP-xmp:MetadataDate` は撮影日時ではない。** サンプルメディアでは `photoTakenTime` と **ちょうど 16 時間** ずれている
   （`2024-01-01 07:00:00 UTC` vs `2024-01-01 00:00:00 UTC`）。これはメタデータ編集時刻の例である。
   これはメタデータ書き込み日時（Adobe 書き出し時刻）であり、**撮影日時候補に採用してはならない**。
   → 「日時が存在するから使う」の典型的な罠。
3. **`creationTime` は 4 ファイルすべてで同一値**（`2024-01-02 00:00:00 UTC`）であり、
   アルバムメタデータ `メタデータ.json` の `date` とも一致する。
   → **`creationTime` は「Google フォトへのアップロード日時」であって撮影日時ではないことの直接的証拠。**
   `photoTakenTime` とは約 1.5 日ずれている。
4. **`FileModifyDate` は 2026-08-26 20:05 前後**（= Takeout の解凍・ダウンロード日時）で、全ファイル無意味。
   これが「Takeout すると全部ダウンロード日になる」問題の実体。

→ このアルバムでは **JSON `photoTakenTime` が唯一の撮影日時ソース**。ツールが日時を「復元」する対象そのもの。

### 3.6 `サンプルアルバムB` — EXIF 撮影日時ありのケース

代表例 `IMG_0101.JPG`（iPhone 6s / iOS 11.1）:

```
IFD0:ModifyDate            2024:01:01 09:00:00     ← ローカル時刻、タイムゾーン情報なし
ExifIFD:DateTimeOriginal   2024:01:01 09:00:00     ← 同上
ExifIFD:CreateDate         2024:01:01 09:00:00     ← 同上
ExifIFD:SubSecTimeOriginal 515
ExifIFD:OffsetTimeOriginal （存在しない）           ← iOS 11 は未記録
GPS:GPSDateTime            2017:11:06 23:40:13Z    ← UTC
JSON photoTakenTime        1704067200 = 2024-01-01 00:00:00 UTC
JSON creationTime          1704153600 = 2024-01-02 00:00:00 UTC
```

**全 17 枚の JPEG について、`DateTimeOriginal` を UTC とみなして `photoTakenTime` を引いた差分は
例外なくちょうど `+09:00 秒 = +9 時間 = JST` だった。**

| 差分 | 件数 |
| --- | --- |
| +09:00 秒（きっかり） | 17 / 17 |
| それ以外 | 0 |

これが意味すること:

- **EXIF `DateTimeOriginal` は「撮影地のローカル時刻」、JSON `photoTakenTime` は「同じ瞬間の UTC」**であり、
  両者は矛盾していない。**同一の絶対時刻を別表現で持っているだけ。**
- したがって **「EXIF と JSON が数時間ずれている」＝ CONFLICT ではない。**
  素朴に差分の絶対値だけで衝突判定すると、正常なファイル 17 枚すべてを誤って CONFLICT にしてしまう。
  この点は本ツールの日時比較アルゴリズムの中核（§6.3）。
- Google は EXIF ローカル時刻 + タイムゾーン推定から `photoTakenTime` を **秒単位まで正確に** 生成している
  （17 枚すべて誤差 0 秒）。**JSON は EXIF と独立した情報源ではなく、EXIF の派生物である**ケースが多い。

さらに:

- **`GPSDateTime` は UTC で記録されており、ローカル EXIF との差分から実際のタイムゾーンオフセットを算出できる。**
  例: `08:40:23`(local) − `23:40:13Z`(11/06) = 9 時間 10 秒 → 15 分丸めで **+09:00**。GPS 測位遅延ぶんの秒差が出るため丸めが必要。
  本アルバムの JPEG 17 枚中 **17 枚に GPS 日時が存在**。→ タイムゾーン自動判定の一次ソースとして使える（§8）。
- `IMG_0102.PNG`（スクリーンショット）には **EXIF が一切ない**が、
  `XMP-photoshop:DateCreated = 2024:01:01 09:01:00` を持ち、これは `photoTakenTime`（`2024-01-01 00:01:00 UTC`）を
  **JST に変換した値と完全一致する**。
  → **`XMP-photoshop:DateCreated` は撮影日時として信頼できる**（`XMP:MetadataDate` とは正反対）。
  XMP のどのタグかによって意味が全く違うため、**タグ単位のホワイトリスト運用が必須**。
- `creationTime` はこのアルバムでも **18 件すべて同一値**（`2024-01-02 00:00:00 UTC`）。§3.5-3 と同じ結論。

### 3.7 書き込み挙動の実測（スクラッチパッド上の複製に対して実施）

| 検証 | 結果 |
| --- | --- |
| EXIF 無し JPEG（Adobe 書き出し）へ `EXIF:DateTimeOriginal` / `CreateDate` / `OffsetTimeOriginal` を追記 | 成功。既存 XMP・ICC・Adobe APP14 は保持。サイズ +105 バイト。画像データ非再エンコード |
| PNG へ `XMP-photoshop:DateCreated` / `XMP-xmp:CreateDate` を書き込み | 成功 |
| PNG へ `EXIF:DateTimeOriginal` を書き込み（eXIf チャンク） | ExifTool 上は成功。ただし PNG の eXIf チャンクは対応ビューアが限られるため既定 OFF 推奨 |
| MP4 へ `-api QuickTimeUTC=1` 付きで `QuickTime:CreateDate=2024:01:01 09:00:00+09:00` | 成功。**ファイル内には UTC の `2017:11:06 23:40:23` が格納される**（＝ `photoTakenTime` そのもの） |
| 同じ MP4 を `-api QuickTimeUTC=1` **なし**で読むと | `2017:11:06 23:40:23` と表示される → **オプションを付け忘れると 9 時間ずれる典型事故** |
| MP4 へ `Keys:CreationDate` | `2024:01:01 09:00:00+09:00` としてオフセット付きで格納される（Apple 系がここを見る） |
| macOS で `os.utime()` により mtime を **過去** に設定 | **birth time も自動的に同じ値まで引き下がる**（APFS の挙動）。`SetFile` 不要 |
| 同じく mtime を **未来** に設定 | birth time は **変わらない**（2017 のまま）。引き下げは効くが引き上げは効かない |
| `exiftool "-FileModifyDate=..." "-FileCreateDate=..."` | mtime / birth time ともに設定成功（macOS） |
| HEIC 書き込み | **未検証**（実データに HEIC がなく、`sips` での HEIC 生成にも失敗した）。実サンプル入手後に検証が必要 |

---

## 4. Google Takeout データ構造

### 4.1 ディレクトリ構造は前提にしない

Takeout の構造は `Takeout/Google フォト/<アルバム名 または "Photos from YYYY">/` が典型だが、
**フォルダ名はロケール依存**（`Google Photos` / `Google フォト` / `Google Fotos` …）であり、
分割 ZIP のマージ方法によっても変わる。

→ **本ツールは `Takeout` や `Google フォト` というフォルダ名に一切依存しない。**
判定基準は「同一ディレクトリ内に Takeout 由来の JSON sidecar が存在するか」のみ。
したがって以下がすべて等価に動作する。

```bash
python -m photo_date_restore sources/Takeout
python -m photo_date_restore "sources/Takeout/Google フォト"
python -m photo_date_restore "sources/Takeout/Google フォト/サンプルアルバムA"
python -m photo_date_restore ~/Desktop/適当なフォルダ     # sidecar があれば処理、なければ NO_JSON
```

### 4.2 メディア sidecar JSON のスキーマ（実データより）

```jsonc
{
  "title": "IMG_0101.JPG",           // 元のファイル名。duplicate 時は (n) を含まないことがある（GPTH #59）
  "description": "",
  "imageViews": "33",
  "creationTime":  { "timestamp": "1704153600", "formatted": "..." },  // Google フォト登録日時（UTC）
  "photoTakenTime":{ "timestamp": "1704067200", "formatted": "..." },  // 撮影日時（UTC）★これが本命
  "geoData":     { "latitude": 35.0000000, "longitude": 139.0000000, "altitude": 23.21, ... },
  "geoDataExif": { ... },            // EXIF 由来の GPS（geoData と同値のことが多い）
  "people": [ { "name": "..." } ],
  "url": "https://photos.google.com/photo/...",
  "googlePhotosOrigin": { "webUpload": { "computerUpload": {} } }
}
```

観測された揺らぎ・注意点:

- `geoData` が全て `0.0` のケースあり（`IMG_0001.jpg`, `IMG_0102.PNG`）→ **`0.0/0.0` は「位置情報なし」として扱う**（Null Island 問題）
- `geoDataExif` は存在しないことがある
- `people` は存在しないことがある
- `timestamp` は **文字列**（`"1704067200"`）。数値ではない
- `formatted` はロケール依存の表示用文字列。**パースに使ってはならない**（`timestamp` のみ使う）
- GPTH #51 で `altitude` に `NaN` 文字列が入る破損 JSON が報告されている → 標準 `json` モジュールは `NaN` を受け付けるが、値検証は行うこと

### 4.3 アルバムメタデータ JSON

`メタデータ.json` / `metadata.json` / `Metadaten.json` …（ロケール依存）。
`title`（= アルバム名）、`description`、`access`、`date` を持ち、`photoTakenTime` / `creationTime` を **持たない**。
→ sidecar 判定の必要条件で自然に除外される（§5.1）。

---

## 5. メディアと JSON の対応付けアルゴリズム

### 5.0 基本方針

> **ファイル名だけの推測で危険な JSON を割り当ててはいけない。**
> 一意に決まらなければ `AMBIGUOUS_JSON` として処理を止める。

GPTH v3 は「メディア名を各種変換して `<変換名>.json` が存在するか試す」という **前方生成** 方式を採る
（`lib/date_extractors/json_extractor.dart`）。これは実績があるが、以下の弱点がある。

- `.supplemental-metadata.json` 系に未対応（未解決 Issue #353 / #448 / #449）
- 最初にヒットした候補を無条件採用する → 曖昧性を検出できない
- `_removeDigit`（`(1)` 除去）は誤マッチしやすく `tryhard` 扱い

本ツールは **逆引き（JSON 側からの索引構築） + 証拠付きスコアリング** を採る。

### 5.1 Phase 0: ディレクトリ単位で JSON を分類

対応付けは **同一ディレクトリ内に限定**する（Takeout の JSON は必ずメディアと同じフォルダに置かれる）。
ディレクトリを跨いだ探索は誤マッチのリスクしかないため行わない。

各 `*.json` を以下で分類する。

```
is_media_sidecar(j) :=
      j は valid JSON object
  AND "title" が非空の文字列
  AND ("photoTakenTime" に timestamp があるか OR "creationTime" に timestamp があるか)
```

- 真 → **メディア sidecar 候補プール**へ
- 偽 → `ALBUM_METADATA` / `UNKNOWN_JSON` として除外し、レポートに記録（**削除も移動もしない**）

この規則は実データで検証済み: `メタデータ.json` 2 件（`title` あり / `photoTakenTime`・`creationTime` なし）を
ロケール名に依存せず正しく除外できる。

### 5.2 Phase 1: JSON ファイル名の構造分解

各 sidecar JSON のファイル名を次の文法で分解する。

```
<json_filename> = <stem> [<sup_suffix>] [<dup_suffix>] ".json"

<sup_suffix> : ".supplemental-metadata" の **前方一致部分文字列**
               （".supplemental-metadata", ".supplemental-metadat", ..., ".supple", ".s"）
               ※ 任意の ".s*" ではなく、literal のプレフィックスであることを厳密に検査する
<dup_suffix> : "(" 数字 ")"    ※ GPTH #59: image(11).jpg ↔ image.jpg(11).json
```

抽出結果として各 JSON は次の 3 つのキーを持つ。

| キー | 内容 | 信頼度 |
| --- | --- | --- |
| `K_title` | JSON 内 `"title"` フィールド | **最高**（Google 自身が記録した元ファイル名） |
| `K_stem` | ファイル名から分解した `<stem>` | 高（ただし切り詰められている可能性） |
| `K_dup` | `<dup_suffix>` の数値（無ければ None） | — |

すべてのキーは **NFC 正規化 + 前後空白除去** して比較する
（macOS は APFS 上のファイル名を NFD で返すことがあり、JSON 内の `title` は NFC。GPTH PR #247 と同じ問題）。
大文字小文字は **既定で区別する**が、一致しない場合の第 2 段として casefold 比較を行う（GPTH #435 対策）。

### 5.3 Phase 2: メディア側の候補キー生成

各メディア `M` について、以下を順に生成する（上ほど高信頼）。

| # | 変換 | 例 | 備考 |
| --- | --- | --- | --- |
| a | そのまま | `IMG_0101.JPG` | |
| b | 編集版サフィックス除去 | `IMG_1(1)-編集済み.jpg` → `IMG_1(1).jpg` | `-edited` / `-編集済み` / `-bearbeitet` / `-bewerkt` / `-edytowane` / `-modificato` / `-modifié` / `-ha editado` / `-editat` / `-effects` / `-smile` / `-mix`（GPTH `extras.dart` 準拠、NFC 後に判定） |
| c | duplicate 位置スワップ | `image(11).jpg` → stem=`image.jpg`, dup=11 | GPTH `_bracketSwap` |
| d | 拡張子除去 | `20030616.jpg` → `20030616` | 拡張子なしでアップロードされたもの |
| e | 切り詰め | `<basename>` の先頭 46 文字 | Google は `<stem>.json` 全体が **51 文字** を超えると stem を切る（GPTH `_shortenName`、Issue #8）。`.supplemental-metadata` 付きの場合は suffix 側から先に削れる |
| f | `(n)` 除去 | `IMG_4081(1).jpg` → `IMG_4081.jpg` | **低信頼**。既定では単独根拠として採用しない |

### 5.4 Phase 3: マッチングとスコアリング

各 (M, J) ペアに対して信頼度 tier を付ける。

| Tier | 条件 | 採用 |
| --- | --- | --- |
| **T1 EXACT_TITLE** | `NFC(J.K_title) == NFC(basename(M))` | 採用 |
| **T2 EXACT_NAME** | `J.K_stem == basename(M)` かつ `J.K_dup` が M の `(n)` と整合 | 採用 |
| **T3 DERIVED_VERIFIED** | b〜f の変換で一致し、**かつ** `J.K_title` が M の basename（または `(n)` を除いた形）と整合 | 採用 |
| **T4 TRUNCATED_PREFIX** | `J.K_stem` が `basename(M)` の **前方一致部分文字列** であり、`len(J.K_stem) >= 46`（切り詰め閾値近傍）であり、**かつ** `J.K_title == basename(M)` | 採用 |
| **T5 DERIVED_WEAK** | 変換で一致したが `title` による裏付けがない | **既定で不採用**（`--allow-weak-match` で有効化） |

判定規則:

1. M に対して **最上位 tier のマッチが 1 件だけ** → 採用（`json_match_tier` をレポートに記録）
2. 最上位 tier が **同点で複数** → `AMBIGUOUS_JSON`。**日時書き込みを行わない**
3. マッチ 0 件 → `NO_JSON`
4. **1 つの JSON は 1 つのメディアにしか割り当てない（1:1 制約）。** 割り当て確定後、
   同じ JSON が別メディアの最上位候補でもあった場合は **両方を `AMBIGUOUS_JSON` に戻す**
5. T5 のみが存在する場合は `NO_JSON` 扱い（レポートには「弱候補あり」を記録して利用者が判断できるようにする）

### 5.5 なぜ `title` を軸にするか

実データでは 22/22 件で `title == basename(media)` が成立する。
`title` は Google が記録した「元のファイル名」であり、
ファイル名の切り詰め・`(n)` の位置ずれ・大文字小文字の揺れ・supplemental サフィックスの
**すべての破損から独立している**。ファイル名変換ルールを推測で増やすより、`title` を裏付けに使うほうが安全。

ただし GPTH #59 のとおり、duplicate 時は `title` が `(n)` を含まない（`IMG_4081(1).jpg` に対して `title = "IMG_4081.JPG"`）。
このため `title` 単独では duplicate を区別できず、必ず `K_dup` と併用する。

---

## 6. 日時決定アルゴリズム

### 6.1 日時ソースの分類（ホワイトリスト方式）

**明示的に列挙したタグ以外は絶対に撮影日時候補にしない。**

#### 採用可（撮影日時を意味するもの）

| 優先 | ソース | 種別 | タイムゾーン | 備考 |
| --- | --- | --- | --- | --- |
| 1 | `EXIF:DateTimeOriginal` (+`SubSecTimeOriginal`, `OffsetTimeOriginal`) | 撮影日時 | ローカル（オフセットは別タグ） | 最優先 |
| 2 | `EXIF:CreateDate` (= DateTimeDigitized) | デジタル化日時 | ローカル | 1 が無い場合 |
| 3 | `QuickTime:Keys:CreationDate` | 撮影日時（動画） | **オフセット付き** | Apple 系動画で最も信頼できる |
| 4 | `QuickTime:CreateDate` | 撮影日時（動画） | **UTC 格納** | 読み書き時に `-api QuickTimeUTC=1` 必須 |
| 5 | `XMP-photoshop:DateCreated` / `XMP-exif:DateTimeOriginal` | 撮影日時 | ローカル or オフセット付き | 実データで `photoTakenTime` と一致を確認 |
| 6 | **JSON `photoTakenTime.timestamp`** | 撮影日時 | **UTC** | EXIF が無い場合の本命 |
| 7 | `EXIF:ModifyDate` (IFD0) | ファイル更新日時 | ローカル | **低信頼**。1・2 が無く 6 も無いときのみ。既定で参照するが必ず `datetime_source` に明示 |
| 8 | JSON `creationTime.timestamp` | **Google フォト登録日時** | UTC | **既定 OFF**。`--json-fallback creation-time` で opt-in |
| 9 | ファイル名埋め込み日時 | 推測 | 不明 | **既定 OFF**。`--filename-date` で opt-in |

#### 採用不可（撮影日時ではない — ブラックリスト）

| ソース | 実際の意味 | 実データでの確認 |
| --- | --- | --- |
| `XMP-xmp:MetadataDate` | メタデータ最終更新日時 | `photoTakenTime` と 16 時間ずれ（§3.5） |
| `XMP-xmp:ModifyDate` | 同上 | |
| `ICC-header:ProfileDateTime` | ICC プロファイルの作成日時（`1998:02:09` 等の定数） | §3.5 で観測 |
| `File:FileModifyDate` / `FileAccessDate` / `FileInodeChangeDate` | Takeout 解凍日時 | 全件 2026-08-26（§3.5-4） |
| アルバム `メタデータ.json` の `date` | アルバム作成日時 | `creationTime` と同値（§3.5-3） |
| `QuickTime:MediaModifyDate` 単独 | エンコード日時 | — |

### 6.2 決定フロー

```
                      ┌───────────────────────────┐
                      │ メディア 1 件              │
                      └────────────┬──────────────┘
                                   ↓
              ┌────────────────────────────────────────┐
              │ 拡張子が対応形式か？                    │
              └──── NO ──→ UNSUPPORTED（レポートのみ） │
                    │ YES
                    ↓
              sidecar JSON 対応付け（§5）
                    │
        ┌───────────┼────────────┬─────────────────┐
   AMBIGUOUS     NO_JSON      1件確定
        │           │              │
        ↓           │              ↓
   書き込み中止 ←───┘         JSON 日時を抽出
   (AMBIGUOUS_JSON)           photoTakenTime → (opt) creationTime
                    │              │
                    └──────┬───────┘
                           ↓
              メディア本体の日時候補を抽出（§6.1 の 1〜5, 7）
                           ↓
              ┌────────────────────────────┐
              │ 本体に撮影日時候補があるか？ │
              └──────┬─────────────┬───────┘
                 YES │             │ NO
                     ↓             ↓
          ┌──────────────────┐   ┌──────────────────────────┐
          │ JSON もあるか？   │   │ JSON photoTakenTime あり？ │
          └──┬────────────┬──┘   └────┬───────────────┬─────┘
        YES  │         NO │       YES │            NO │
             ↓            ↓           ↓               ↓
      ┌──────────────┐  OK_EXIF   TZ確定？（§8）  v1.0: creationTime は
      │ 照合（§6.3） │  （本体    ├YES→JSON_TIME_ 使わない（§7.1 追補）
      └──┬────────┬──┘   採用）  │     USED（書込） → NO_DATE
     一致 │    不一致│            └NO →JSON_TIME_
         ↓         ↓                  MTIME_ONLY（mtimeのみ）
   EXIF_JSON_MATCH  EXIF_JSON_CONFLICT
   （本体を採用）    （書き込みしない・要人手）
                           ↓
                    確定日時 + datetime_source + confidence
                           ↓
                    現状と比較 → 変更不要なら NO_CHANGE（§17）
                           ↓
              dry-run → レポートのみ / apply → copy or in-place
                           ↓
                    EXIF 書き込み（§9）→ 読み戻し検証（§9.4）
                           ↓
                    ファイルシステム日時（§10）
                           ↓
                          監査ログ
```

### 6.3 EXIF と JSON の照合 — 一致判定の設計

**これが本ツールで最も間違えやすい部分。** §3.6 のとおり、正常なファイルでも EXIF と JSON は 9 時間ずれる。

比較は必ず **絶対時刻（UTC の瞬間）ドメイン**で行い、差分 `Δ = exif_instant − json_photo_taken_time`（秒）を求める。
EXIF 側の絶対時刻の求め方は、オフセット情報の有無で 3 通り。

| ケース | 絶対時刻の求め方 | `tz_source` |
| --- | --- | --- |
| `OffsetTimeOriginal` あり | そのまま確定 | `EXIF_OFFSET` |
| `GPSDateTime` あり | `offset = round_to_15min(DTO_naive − GPSDateTime)`（\|offset\| ≤ 14h を検査）→ 確定 | `GPS` |
| どちらも無し | 絶対時刻は確定できない。代わりに **「JSON が正しいと仮定したときに必要なオフセット」** を求める: `implied_offset = DTO_naive(UTC とみなす) − photoTakenTime` | `IMPLIED` |

**（2026-08-27 追補）`MATCH_TZ` は単一の status ではなく、オフセットの根拠に応じて 4 段階に分ける。**
実データで確認された通り、「15 分刻み・14 時間以内」という形だけでは、真のタイムゾーン差と
「たまたま 15 分刻みに近い偶然の食い違い」を区別できない。根拠の強さを status 自体に埋め込む。

判定表:

| 判定 | 条件 | status | 動作 |
| --- | --- | --- | --- |
| `MATCH_EXACT` | \|Δ\| ≤ 2 秒 | `EXIF_JSON_MATCH` | EXIF 採用 |
| `MATCH_NEAR` | 2 < \|Δ\| ≤ 60 秒 | `EXIF_JSON_MATCH` | EXIF 採用（レポートに `difference_seconds` 記録） |
| `MATCH_TZ_EXPLICIT` | `implied_offset` が 900 秒の倍数 ±90 秒以内 **かつ** `OffsetTimeOriginal`（または `Keys:CreationDate` 等の明示オフセットタグ）が同じオフセットを示す、**または** `--timezone` 明示指定のオフセットと一致 | `EXIF_JSON_MATCH_TZ_EXPLICIT` | EXIF 採用。信頼度 HIGH |
| `MATCH_TZ_GPS` | 同上の範囲 **かつ** `GPSDateTime` から独立に算出したオフセットと一致（明示オフセットタグは無し） | `EXIF_JSON_MATCH_TZ_GPS` | EXIF 採用。信頼度 HIGH |
| `MATCH_TZ_INFERRED` | 同上の範囲 **かつ** 明示タグ・GPS は無いが、同一ディレクトリ内の他ファイル（既定 3 件以上）で同じオフセットが `EXPLICIT` または `GPS` 根拠により確認されている | `EXIF_JSON_MATCH_TZ_INFERRED` | EXIF 採用。信頼度 MEDIUM |
| `POSSIBLE_TZ` | 同上の範囲だが、上記いずれの裏付けも無い（**単一ファイルの `implied_offset` のみ**） | `EXIF_JSON_POSSIBLE_TZ` | EXIF 採用（EXIF は書き換えないため実害はない）。ただし信頼度 LOW とし、`--add-offset` の対象から除外し、レポートで要確認として明示する |
| `CONFLICT_TZ_UNCLEAR` | \|Δ\| ≤ 14 時間 だがオフセットとして説明できない（15 分刻みに乗らない） | `EXIF_JSON_CONFLICT` | **書き込みしない**（`--on-conflict` で変更可） |
| `CONFLICT_MAJOR` | \|Δ\| > 14 時間（＝ 日付そのものが違う） | `EXIF_JSON_CONFLICT` | **書き込みしない** |

判定順序（同一ファイルに対して上から検査し、最初に該当した tier を採用）:

```
EXPLICIT（本体の明示オフセットタグ、または --timezone 一致）
  → GPS（本体の GPSDateTime 由来）
  → INFERRED（同一ディレクトリの兄弟ファイルで裏付け、既定 3 件以上）
  → POSSIBLE（それ以外。単発の偶然一致の可能性を排除できない）
```

- 900 秒（15 分）の閾値は、実在する全 UTC オフセット（+05:45 の Nepal、+08:45 の Eucla を含む）を
  カバーする最小粒度。±90 秒の許容は GPS 測位遅延・カメラ時計誤差を吸収するため（実測では最大 10 秒）。
- **`MATCH_TZ_*` と `CONFLICT` の分離が要求仕様「タイムゾーン差による数時間の差と、日付そのものが違う場合を区別」の実装。**
  14 時間を境界にすることで、「+14:00（Kiribati）」までは タイムゾーン差、それを超えるものは別日と判定できる。
- **`MATCH_TZ_*` の 4 分割が「単純な 15 分刻み・14 時間以内だけで一致断定しない」の実装。**
  根拠が弱い（`POSSIBLE_TZ`）場合でも EXIF は変更しない（ケース【A】は既存 EXIF を上書きしないため）ので安全だが、
  「このオフセットを信頼して他の判断（`--add-offset` によるタグ追記や、他形式への横展開）に使ってよいか」を
  status で区別できるようにする。
- 本データの `サンプルアルバムB` JPEG 17 枚は `implied_offset = +09:00`（= 900 × 36、誤差 0）で、
  かつ全 17 枚に `GPSDateTime` があり独立に +09:00 を導ける（`OffsetTimeOriginal` は iOS 11 のため記録なし）。
  → **全 17 枚が `EXIF_JSON_MATCH_TZ_GPS`**（`EXPLICIT` ではない。実測データにオフセットタグは存在しないため）。

### 6.4 なぜ EXIF を優先するか

- EXIF `DateTimeOriginal` は **撮影機器が撮影の瞬間に書いた一次情報**。
- JSON `photoTakenTime` は **Google が EXIF から推定・変換した二次情報**（§3.6 で実証）。
  ユーザーが Google フォト UI 上で日時を手動修正した場合のみ、JSON のほうが正しいことがある。
- したがって既定は **EXIF 優先 + JSON は検証専用**。
  Google フォト上で日時を直した記憶がある利用者向けに `--prefer-json` を用意するが、既定では使わない。

---

## 7. EXIF と JSON の優先順位（まとめ）

```
【A】本体に撮影日時がある場合
     EXIF/XMP/QuickTime の撮影日時を第一候補とする
       └─ JSON があれば必ず照合（§6.3）
            ├─ MATCH / MATCH_TZ → EXIF を採用（EXIF は書き換えない）
            │                      ただし OffsetTimeOriginal が欠けていて
            │                      オフセットを導出できた場合は「追記」を提案（既定 OFF）
            └─ CONFLICT          → 書き込みせず CONFLICT として記録
       └─ JSON が無ければ EXIF をそのまま信頼（status: OK_EXIF、通常は NO_CHANGE）

【B】本体に撮影日時が無く JSON photoTakenTime がある場合
     photoTakenTime（UTC の絶対時刻）を採用
       └─ mtime（+ birth time）は **タイムゾーンに関係なく常に設定できる**
          （UTC 絶対時刻はそのまま `os.utime` に渡せるため）
       └─ §8 のラダーでタイムゾーンが確定できるか判定
            ├─ 確定できた（EXPLICIT / GPS / INFERRED / CLI）
            │     └─ ローカル時刻へ変換し、EXIF DateTimeOriginal / CreateDate /
            │        OffsetTimeOriginal を **追記**（既存タグは破壊しない）
            │        status: JSON_TIME_USED / datetime_source: PHOTO_TAKEN_TIME
            └─ 確定できなかった
                  └─ **ローカル日時メタデータの書き込みは SKIP**（推測で書かない）
                     mtime のみ JSON timestamp から修復する
                     status: JSON_TIME_MTIME_ONLY
                     message: TIMEZONE_REQUIRED_FOR_METADATA
                     （mtime も既に正しく変更不要なら status は NO_CHANGE とし、
                       message に TIMEZONE_REQUIRED_FOR_METADATA を残してメタデータ未確定を明示する）

【C】photoTakenTime が無く creationTime のみある場合
     既定: 採用しない（status: NO_DATE、理由を記録）
     `--json-fallback creation-time` 指定時のみ採用
       └─ status: JSON_CREATION_FALLBACK / datetime_source: CREATION_TIME_FALLBACK
       └─ **EXIF DateTimeOriginal には書かない**（撮影日時ではないため）
          mtime のみ設定する、を既定挙動として提案（§23-2 で要判断）

【D】いずれも無い場合
     NO_DATE。一切変更しない
```

### 7.1 creationTime fallback を既定 OFF にする根拠

実データで `creationTime` はアルバム内 **全ファイル同一値**（= 一括アップロード時刻）だった（§3.5-3, §3.6）。
これを撮影日時として書き込むと、**アルバム内の全写真が同じ日時になり、撮影順が失われる**。
しかも Takeout 直後の mtime（ダウンロード日時）よりは「それらしく見える」ため、誤りに気づきにくい。
GPTH の Issue #436 / #450 で報告されている「日付がおかしい」の一因もここにあると考えられる。

→ **fallback は opt-in、かつ `datetime_source` を必ずログに明示**（要求仕様どおり `CREATION_TIME_FALLBACK` を使う）。

**（2026-08-27 追補・v1.0 スコープ確定）** `creationTime` は v1.0 では **撮影日時復元の入力として一切使用しない**。
`--json-fallback creation-time` は本追補時点で **実装しない**（CLI に追加しない）。読み取り・レポート表示・監査情報
としては引き続き JSON から読み取り `json_creation_time` 列に出力してよいが、`selected_datetime` の算出には使わない。
将来機能候補として本節の設計は残すが、実装は Phase 4 以降の判断とする（§24）。

---

## 8. timezone 処理

### 8.1 問題の定義

- JSON `photoTakenTime.timestamp` は **Unix time = UTC の絶対時刻**
- EXIF `DateTimeOriginal` は **撮影地のローカル壁時計時刻**（タイムゾーン情報を含まない）
- 素朴に `datetime.utcfromtimestamp(ts).strftime("%Y:%m:%d %H:%M:%S")` を EXIF に書くと、
  **JST の写真なら 9 時間巻き戻る**。これが最も起こりやすい事故。

### 8.2 オフセット解決ラダー（上から順に試す）

**（2026-08-27 追補）システムローカルタイムゾーンを既定値として使う設計は撤回する。**
撮影地は実行環境（このツールを動かしている PC）のタイムゾーンと一致するとは限らない
（旅行中の写真、他人から譲り受けた写真、実行環境が別の国のマシンである場合など）。
したがって「実行マシンのタイムゾーン」は **候補にすら入れない**。下記ラダーのいずれでも
確定できない場合は、**推測せずに未確定のまま扱う**（§8.1, §7 ケース【B】）。

信頼度順（上から順に判定し、最初に成立したものを採用する）:

| 優先 | 手段 | `tz_source` | 条件 |
| --- | --- | --- | --- |
| 1 | メディア本体の `OffsetTimeOriginal` / `Keys:CreationDate` のオフセット | `EXPLICIT` | 存在すれば常に最優先（ファイル自身が明示的に記録した一次情報のため） |
| 2 | 本体の `GPSDateTime` と `DateTimeOriginal` の差 → 15 分丸め（§6.3） | `GPS` | 両方存在すれば。実データ 17/18 件で利用可 |
| 3 | **同一ディレクトリ内の兄弟ファイル**で、上記 1・2 いずれかにより確定したオフセットが
      **既定 3 件以上、矛盾なく一致**する場合、その値 | `INFERRED` | `--no-tz-from-siblings` で無効化可（既定 ON）。JSON `geoData` の緯度経度からの推定
      （`timezonefinder`、`--tz-from-geo` で opt-in）も本 tier の追加根拠として扱う。実データでは
      `IMG_0102.PNG`（EXIF なし）に対し、同一アルバムの JPEG 17 枚（tier GPS で確定済み）から +09:00 を導ける |
| 4 | `--timezone <IANA名>` の明示指定 | `CLI` | 利用者が明示した場合。**1〜3 の実測的根拠より優先度を下げる**：
      ファイル自身や兄弟ファイルの物理的証拠がある場合はそちらを信頼し、`--timezone` は
      「証拠が無いファイルを救済する既定値」として使う（旅行中に撮った 1 枚だけ違うタイムゾーンだった、
      という実測結果を上書きしないため） |
| 5 | 上記いずれでも確定できない | `NONE` | **推測しない。** ローカル日時メタデータは書かない。
      JSON `photoTakenTime` は UTC 絶対時刻として mtime 修復にのみ使う（`JSON_TIME_MTIME_ONLY` /
      `TIMEZONE_REQUIRED_FOR_METADATA`。§7 ケース【B】） |

`--timezone` が指定されており、かつ §6.3 の `implied_offset` と一致する場合、その `MATCH_TZ` 判定は
`EXIF_JSON_MATCH_TZ_EXPLICIT` として扱う（利用者の明示指定も「明示的な確定」の一種とみなす）。

### 8.3 書き込み時の原則

> **JSON から復元する場合は、必ず `OffsetTimeOriginal` / `OffsetTimeDigitized` を同時に書く。**

理由: ローカル時刻 + オフセットを両方書けば、**どのタイムゾーンを選んだとしても絶対時刻は保存される**。
仮にオフセットの推定が外れても、失われるのは「壁時計の見え方」だけで、
オフセットを解釈できるビューアなら正しい瞬間を表示できる。オフセットを書かない場合、推定ミスは復旧不能な情報損失になる。

動画では `Keys:CreationDate`（オフセット付き）と `QuickTime:*Date`（UTC）を
`-api QuickTimeUTC=1` 経由で書くことで同じ性質が得られる（§3.7 で実測）。

### 8.4 代替モード

- `--utc`: ローカル変換を一切行わず、`DateTimeOriginal` に UTC 壁時計時刻、`OffsetTimeOriginal=+00:00` を書く。
  絶対時刻は完全に保存されるが、Finder 上の見え方が撮影時の記憶と 9 時間ずれるため既定にはしない。
- `--no-write-offset`: オフセットタグを書かない（古いビューア互換性のため）。**非推奨**として警告を出す。

---

## 9. EXIF 書き込み方式

### 9.1 ExifTool と Python ライブラリの比較

| 観点 | ExifTool（外部プロセス） | piexif | Pillow | pillow-heif / pymediainfo 等 |
| --- | --- | --- | --- | --- |
| JPEG EXIF 書き込み | ◎ | ○ | △（`save()` で **再エンコード** → 画質劣化） | — |
| TIFF | ◎ | △ | △ | — |
| PNG（XMP / `tEXt` / eXIf） | ◎ | × | × | × |
| HEIC | ○（要検証） | × | △（heif プラグイン依存・書き込み弱い） | △ |
| MP4 / MOV | ◎（`-api QuickTimeUTC`） | × | × | ×（読み取り専用） |
| MakerNote 保持 | ◎（非破壊書き込み） | △（EXIF ブロックを再構築するため破損リスク） | × | — |
| タイムゾーン（`OffsetTime*`, `Keys:CreationDate`） | ◎ | △ | × | × |
| 書き込み前バックアップ | ◎（`*_original` を自動生成） | 自前実装 | 自前実装 | — |
| 読み戻し検証 | ◎（同一ツールで完結 = 表現の食い違いが起きない） | △ | △ | — |
| 依存 | 外部バイナリ（Homebrew: `brew install exiftool`） | pip のみ | pip のみ | pip + ライブラリ |
| 性能 | プロセス起動が重い → `-stay_open` 常駐で解決 | 高速 | 中 | 中 |

**結論: ExifTool を採用する。**

決め手:

1. **PNG / HEIC / MP4 / MOV を扱えるのが実質 ExifTool だけ。** 本データにも PNG が含まれる。
2. **Pillow は画像を再エンコードする**（`Image.open().save()`）。31MB の JPEG に対してこれを行うのは
   「原本を壊さない」原則の明確な違反。
3. **piexif は EXIF セグメントを丸ごと再構築する**ため、Apple MakerNote（本データの `IMG_0101.JPG` は
   `Apple:RunTimeValue` 等を持つ）を壊すリスクがある。§1 の「カメラ固有の既存メタデータを不必要に破壊してはいけない」に反する。
4. QuickTime の UTC 変換（`-api QuickTimeUTC=1`）は Python 側で自前実装すると事故率が高い（§3.7 で実測済み）。

**トレードオフの受け入れ**: 外部依存が増える。対策として、

- 起動時に `exiftool -ver` を確認し、**バージョンと存在をレポートヘッダに記録**する
- 未インストール時は **解析・dry-run は続行**（EXIF 読み取りは piexif/Pillow で JPEG のみフォールバック）、
  **書き込み系はエラーで停止**し、`brew install exiftool` を案内する
- 大量処理は `exiftool -stay_open True -@ <argfile>` の常駐セッション（または `PyExifTool`）で 1 プロセスに集約

### 9.2 静止画への書き込みタグ

**（2026-08-27 追補）内部設計を JPEG 前提にしない。** `write_exif_datetime()` のような JPEG 専用の
関数名・API は採用せず、概念として **`write_media_datetime(media_type, path, candidate) -> WriteResult`**
という形式非依存のディスパッチ関数を置き、内部で形式ごとの実装（`_write_jpeg_tiff_datetime` /
`_write_png_datetime` / 将来の `_write_heic_datetime` / `_write_video_datetime`）へ振り分ける（§20）。
呼び出し側（`decide` / `applier`）は媒体の形式を意識しない。

v1.0 で実際に書き込みへ対応するのは **JPEG/TIFF/PNG** である。
JPEG/TIFF は、`photoTakenTime` が一意に対応し timezone 根拠が確定した場合、既存 EXIF の有無にかかわらず
`DateTimeOriginal` / `CreateDate` を書き得る。元々 EXIF がない JPEG/TIFF では ExifTool が新しい EXIF metadata block を作成する場合がある。
PNG は §3.7 で書き込み実測済み（XMP 経由、非破壊）のため、`XMP-photoshop:DateCreated` / `XMP-xmp:CreateDate` のみを使う。
HEIC / HEIF と動画は現行版ではメタデータ書き込み未対応である。

**方針: 既存タグを破壊せず、欠けているものだけ追記する。**

| 形式 | 書き込むタグ | 補足 |
| --- | --- | --- |
| JPEG / TIFF | `EXIF:DateTimeOriginal`, `EXIF:CreateDate`, `EXIF:OffsetTimeOriginal`, `EXIF:OffsetTimeDigitized` | `IFD0:ModifyDate` は **書かない**（意味が「ファイル更新日時」であり撮影日時ではないため）。現行 CLI に `--write-modifydate` はない |
| PNG | `XMP-photoshop:DateCreated`, `XMP-xmp:CreateDate` | `EXIF:DateTimeOriginal`（eXIf チャンク）は現行版では書かない |
| HEIC / HEIF / 動画 | なし | 現行版ではメタデータ書き込み未対応 |

既存タグの上書きポリシー:

- ケース【B】（本体に撮影日時が無い）では、対象タグは定義上 **存在しない** → 追記のみ
- ケース【A】（本体に撮影日時がある）では **既定で一切書き込まない**
- 例外的に `OffsetTimeOriginal` のみ、値が欠けていて §8 でオフセットを確定できた場合に追記する
  → `--add-offset`（**既定 OFF**、§23-11 で要判断）

### 9.3 動画への書き込み

動画のメタデータ書き込みは現行版では未対応である。QuickTime タグへの書き込みは将来案であり、`--enable-video` を含む opt-in は現行 CLI に存在しない。

### 9.4 書き込み後の読み戻し検証（必須）

「書いたつもり」ではなく「期待した日時が実際に書き込まれた」ことを毎回確認する。

```
1. 書き込み対象ファイルを exiftool で再読込（-api QuickTimeUTC=1 付き）
2. 期待値と照合:
   - DateTimeOriginal（または Keys:CreationDate）が期待値と秒単位で一致
   - OffsetTimeOriginal が期待値と一致（書いた場合）
   - FileType / MIMEType が書き込み前と同一
   - ImageWidth / ImageHeight が書き込み前と同一（画像破損の簡易検知）
   - ファイルサイズ > 0
3. 不一致 → status = VERIFY_FAILED
   - in-place: ExifTool が残した `<file>_original` から復元する
   - copy   : 出力ファイルを削除する（原本は無傷）
4. 一致 → in-place の `<file>_original` を削除
```

**in-place では `-overwrite_original` を使わない。** ExifTool の既定動作（`<file>_original` を残す）を
そのまま利用し、**検証成功後に自分で削除する**。これによりロールバック経路が常に存在する。

なお ExifTool には `-overwrite_original_in_place` もあり、inode と拡張属性（macOS の xattr、
Finder タグ、Google Drive の同期メタデータ）を保持できる。`_original` 方式と併用できないため、
`--preserve-xattr` オプションで切り替え可能にする（既定は `_original` 方式 = 安全側）。

---

## 10. ファイルシステム日時

### 10.1 macOS における 3 つの日時

| 名称 | 意味 | Python からの操作 |
| --- | --- | --- |
| `mtime` (modification time) | 内容の最終更新日時 | `os.utime(path, (atime, mtime))` で自由に設定可 |
| `birthtime` (creation time) | ファイル作成日時。`stat.st_birthtime` | **直接設定する標準 API はない** |
| `ctime` (inode change time) | inode メタデータの最終変更日時 | **設定不可**（カーネル管理） |

### 10.2 実測で判明した APFS の挙動（重要）

```
初期状態:  mtime=2026-08-27 17:48:53  btime=2026-08-27 17:48:53
os.utime で mtime=2024-01-01 09:00:00 に設定
    →     mtime=2024-01-01 09:00:00  btime=2024-01-01 09:00:00   ← btime も追随して下がる

続けて os.utime で mtime=2030-01-01 に設定
    →     mtime=2030-01-01 00:00:00  btime=2024-01-01 09:00:00   ← btime は上がらない
```

つまり macOS では **`os.utime()` で mtime を過去へ設定すると birth time も自動的に引き下がる**
（`birthtime = min(birthtime, mtime)`）。Takeout 復元は常に「現在 → 過去」方向なので、
**追加のツールなしに birth time も正しくなる。**

### 10.3 設計

| 項目 | 方針 |
| --- | --- |
| `mtime` | **必ず撮影日時に設定する**（`--no-set-mtime` で無効化可）。`os.utime()` を使用 |
| `atime` | mtime と同じ値を設定する（`os.utime` は両方必須。実質意味を持たない） |
| `birthtime` | **明示的な操作は行わない。** §10.2 の副作用で自動的に正しくなる。副作用が働かない場合（既に btime < mtime、または将来日時のケース）は `--force-birthtime` 指定時のみ `SetFile -d`（`/usr/bin/SetFile`、実機に存在を確認済み）で設定する。既定 OFF |
| `ctime` | **一切触らない。** 要求仕様どおり、撮影日時に無理やり変更する設計にはしない |

移植性:

- Linux: `birthtime` は取得も設定も一般に不可 → `mtime` のみ。警告を出す
- Windows: `os.utime` では creation time は変わらない。`--force-birthtime` 相当は将来課題

`exiftool "-FileModifyDate="` でも設定できる（§3.7 で実測）が、
**Python 側の `os.utime()` を正とする**（ExifTool 呼び出し回数を減らし、失敗点を分離するため）。

---

## 11. copy mode（既定・推奨）

```bash
python -m photo_date_restore INPUT --output OUTPUT
```

| 項目 | 仕様 |
| --- | --- |
| 原本 | **一切変更しない**（読み取りのみ） |
| 出力構造 | INPUT からの **相対パスを完全に維持** して OUTPUT 配下に再現 |
| 出力対象 | **メディアファイルのみ**（既定） |
| JSON sidecar | 出力しない（既定）。`--copy-json` で出力可 |
| アルバムメタデータ JSON | 出力しない（既定）。`--copy-album-metadata` で出力可 |
| `.DS_Store` / `._*`（AppleDouble）/ `Thumbs.db` | 常に無視 |
| 処理不能ファイル（`UNSUPPORTED` / `NO_DATE` / `CONFLICT` / `AMBIGUOUS_JSON`） | **日時を変更せずにコピーする**（既定）。`--skip-unresolved` で除外可 |
| 出力先に同名ファイルが既存 | 既定 `SKIP`（`OUTPUT_EXISTS`）。`--overwrite-output` で上書き。`--resume` で内容が既に正しければ `NO_CHANGE` |
| 空き容量 | 実行前に INPUT のメディア合計サイズと OUTPUT の空き容量を比較し、不足なら開始前に中止 |

例:

```
OUTPUT/
├── Google フォト/
│   ├── サンプルアルバムA/
│   │   ├── IMG_0001.jpg
│   │   ├── IMG_0002.jpg
│   │   ├── IMG_0003.jpg
│   │   └── IMG_0004.jpg
│   └── サンプルアルバムB/
│       ├── IMG_0101.JPG
│       ├── IMG_0102.PNG
│       └── ...
└── _report/
    └── report.csv
```

コピー手順（1 ファイルあたり）:

```
1. 出力先ディレクトリを作成
2. shutil.copyfile で内容をコピー（メタデータは持ち込まない）
3. サイズを照合（コピー破損の簡易検知）
4. exiftool で EXIF 書き込み（必要な場合のみ）
5. 読み戻し検証（§9.4）
6. os.utime で mtime/atime を設定
7. 検証失敗時は出力ファイルを削除して ERROR 記録（原本は無傷）
```

### 11.1 出力先に JSON を置かない方針の妥当性検討（利用者からの問い）

> 「別出力モードの場合には、元 Takeout の JSON はそのまま残し、出力先には原則として写真・動画だけを配置する設計がよいと考えている。この方針について問題がないか」

**結論: 問題なし。推奨する。** ただし 2 点の副作用を明記する。

**支持する理由**

1. 復元後のフォルダを Google フォト / iCloud / NAS へ再アップロードする際、JSON が写真として取り込まれたり
   不要ファイルとして残ったりする事故を構造的に防げる
2. 復元済みメディアには撮影日時が EXIF に埋め込まれているため、JSON は **もはや必要ない**
3. 原本 Takeout がそのまま残るので、JSON 原本は失われない（原則 7「JSON 原本を削除しない」を満たす）

**副作用と対策**

| 副作用 | 対策 |
| --- | --- |
| アルバム名以外のアルバム情報（`description`, `access`, アルバム作成日時）が出力側から失われる | 監査レポートに `album_name` 列を持たせ、加えて `OUTPUT/_report/albums.csv` にアルバムメタデータの内容を出力する（`--copy-album-metadata` でファイル自体のコピーも可） |
| `people`（人物タグ）・`description`・GPS など日時以外の JSON 情報も出力側から失われる | 初版スコープ外。ただし **原本には残っている**ので後から再処理できる。将来 `--write-gps` / `--write-description` を追加可能（§23-8） |
| `-編集済み` 版と原版が両方コピーされ、出力が重複する | 既定はそのまま両方出す（削除判断はツールが勝手にすべきでない）。`--edited-policy keep\|skip-edited\|prefer-edited` を用意 |

---

## 12. in-place mode

```bash
python -m photo_date_restore INPUT --in-place --apply
```

| 項目 | 仕様 |
| --- | --- |
| 有効化 | `--in-place` を **明示指定した場合のみ**。省略時は絶対に上書きしない |
| `--output` との併用 | エラー（相互排他） |
| 実行確認 | 対話 TTY では処理件数を表示して `yes` 入力を要求（`--yes` で省略可） |
| バックアップ | ExifTool の `<file>_original` を利用し、検証成功後に削除（§9.4） |
| 書き込み方式 | 既定は `_original` 残置方式。`--preserve-xattr` 指定時は `-overwrite_original_in_place` |
| 未解決ファイル | 一切変更しない |
| JSON sidecar | 既定ではそのまま残す。`--move-json DIR` 指定時のみ退避（§13） |
| クラウド同期フォルダ検知 | パスに `Google Drive` / `マイドライブ` / `Dropbox` / `iCloud Drive` / `OneDrive` を含む場合、**警告を表示**して確認を求める（同期中の書き換えは競合の原因になる） |

**リスク**: in-place は原本を書き換えるため、`--dry-run` での事前確認と別媒体へのバックアップを
README・実行時警告の両方で強く案内する。

---

## 13. JSON 退避方式

```bash
python -m photo_date_restore INPUT --in-place --apply --move-json JSON_BACKUP
```

### 13.1 要件と対応

| 要件 | 実装方針 |
| --- | --- |
| JSON は Google Takeout の原メタデータなので **削除してはいけない** | 削除機能を実装しない。`move` のみ |
| JSON 退避はユーザーが明示的に選択できる | `--move-json DIR` 指定時のみ動作。`--in-place` 専用オプション |
| 写真と JSON の対応関係を後から追跡できる | `JSON_BACKUP/_sidecar_index.csv` を出力（後述） |
| 同名ファイル衝突を防ぐ | 相対パス構造を維持する。それでも衝突した場合は安全に SKIP または ERROR として監査レポートへ記録し、**上書きも衝突回避renameも行わない** |
| 元の相対パスを保持する | `JSON_BACKUP/<INPUT からの相対パス>` にそのまま配置 |

### 13.2 退避後の構造

```
INPUT/Google フォト/サンプルアルバムA/
├── IMG_0001.jpg                                     ← 修復済み（EXIF + mtime）
└── (IMG_0001.jpg.supplemental-metadata.json は移動済み)

JSON_BACKUP/
├── Google フォト/
│   ├── サンプルアルバムA/
│   │   ├── IMG_0001.jpg.supplemental-metadata.json
│   │   ├── ...
│   │   └── メタデータ.json          ← --move-album-metadata 指定時のみ
│   └── サンプルアルバムB/
│       └── ...
└── _sidecar_index.csv
```

### 13.3 `_sidecar_index.csv` の列

| 列 | 内容 |
| --- | --- |
| `media_relative_path` | INPUT からの相対パス（メディア） |
| `original_sidecar_relative_path` | INPUT からの相対パス（退避前の JSON） |
| `moved_sidecar_relative_path` | JSON_BACKUP 内の相対パス（実際の配置） |
| `status` | 実移動に成功したことを示す `MOVED` |

CSV は UTF-8（BOM なし）とする。既存の列・行は破壊せず、同一の 3 パス列を持つ対応は
再実行しても重複追記しない。

### 13.4 退避の安全規則

1. 退避対象は **対応付けに成功し、かつ日時の適用に成功した（`OK_*` / `NO_CHANGE`）JSON のみ**。
   `AMBIGUOUS_JSON` / `CONFLICT` / `ERROR` / `VERIFY_FAILED` の JSON は **その場に残す**
   （後で人手で再処理する必要があるため）
2. アルバムメタデータ（`メタデータ.json` 等）は **既定で移動しない**（`--move-album-metadata` で opt-in）。
   sidecar ではない JSON を勝手に動かさない
3. 移動は同一ファイルシステムなら `os.replace`、跨る場合は **copy → サイズ照合 → unlink** の順
   （unlink 前に必ずコピー成功を確認する）
4. `--dry-run` では移動せず、`_sidecar_index.csv` も作成しない。移動予定は監査レポートに出力する
5. 退避先ディレクトリが INPUT の内部にある場合はエラー（再帰走査との干渉を防ぐ）
6. `sources/` 配下を退避先に指定してはならず、index も作成しない

退避後に元の INPUT を再走査すると sidecar は存在しないため、対象メディアの対応付け結果は
`NO_JSON` となる。既存の本体メタデータは引き続き保持する。

---

## 14. dry-run

**提案: 既定を dry-run にし、`--apply` を明示した場合のみ実際に書き込む。**

利用者の叩き台は「`--dry-run` を必須レベルの機能として」だったが、
**安全側の既定（fail-safe default）** にすることで「うっかり本実行」を構造的に防げる。
`--dry-run` フラグも後方互換のため受け付ける（no-op として扱う）。

| モード | 指定 | 挙動 |
| --- | --- | --- |
| dry-run（既定） | 何も指定しない、または `--dry-run` | 解析とレポート出力のみ |
| 実行 | `--apply` | 実際に書き込む |

dry-run で **行わないこと**（要求仕様どおり）:

```
ファイル変更 / EXIF 書き込み / mtime 変更 / ファイルコピー / JSON 移動 / ディレクトリ作成
```

dry-run で **行うこと**:

- 全ファイルの走査・JSON 対応付け・メタデータ読み取り・日時決定・照合
- 「何をする予定か」を `action` 列として出力（例: `COPY+WRITE_EXIF+SET_MTIME`）
- 出力先の空き容量チェック、出力先の既存ファイル検出
- 集計サマリ（status 別件数、CONFLICT / AMBIGUOUS の一覧）

実装上の担保: 書き込みを行う関数はすべて `Applier` インターフェース経由とし、
dry-run では `NoOpApplier` を注入する。**個々のロジックに `if dry_run:` を散らさない**
（散らすと必ずどこかで漏れる）。

---

## 15. ログ / 監査レポート

### 15.1 形式

- `--report PATH`（拡張子 `.csv` / `.jsonl` で自動判定、`--report-format` で明示指定可）
- 未指定時は `OUTPUT/_report/report-YYYYMMDD-HHMMSS.csv`（copy mode）または
  カレントディレクトリ（in-place mode）
- CSV は **UTF-8 BOM 付き**で出力する（Excel で日本語ファイル名が文字化けしないため。
  `CLAUDE.md` の BOM 規定は Markdown に対するものであり、CSV には適用されないが、
  ここでは可読性のために BOM を付ける。`--csv-no-bom` で無効化可）
- JSONL は UTF-8 BOM なし（機械処理用）

### 15.2 列（要求仕様の項目を全て含む）

**（2026-08-27 追補）** 要求仕様側の列名（`relative_path` / `existing_datetime` /
`existing_datetime_source` / `timezone_source` / `timezone_offset` / `selected_datetime_source` /
`planned_metadata_action` / `planned_mtime_action` / `message`）に列名を合わせつつ、
従来設計の追加列（曖昧性調査用の `json_candidates`、監査用の `confidence` 等）は残す。

| 列 | 説明 |
| --- | --- |
| `file` | INPUT からの絶対パスまたは指定パス基準の表示用パス |
| `relative_path` | INPUT からの相対パス（要求仕様の必須列） |
| `album_name` | 直上のディレクトリ名（アルバム名相当） |
| `media_type` | `image` / `video` |
| `file_type` | `JPEG` / `PNG` / `HEIC` / `MP4` … |
| `json_sidecar` | 対応付いた JSON のファイル名（無ければ空） |
| `json_match_tier` | `T1_EXACT_TITLE` / `T2_EXACT_NAME` / `T3_DERIVED_VERIFIED` / `T4_TRUNCATED_PREFIX` / `NONE` |
| `json_candidates` | 候補として検出された JSON 数（曖昧性の調査用） |
| `existing_datetime` | 本体から読めた既存の撮影日時（ローカル壁時計、ISO8601。旧 `exif_datetime`） |
| `existing_datetime_source` | それがどのタグ由来か（`EXIF:DateTimeOriginal` 等。旧 `exif_datetime_tag`） |
| `exif_offset` | `OffsetTimeOriginal` の値（無ければ空） |
| `gps_datetime` | `GPSDateTime`（UTC、あれば） |
| `json_photo_taken_time` | ISO8601（UTC） |
| `json_creation_time` | ISO8601（UTC）。**v1.0 では読み取り・表示のみ**（§7.1 追補） |
| `difference_seconds` | 既存日時の絶対時刻 − `photoTakenTime`（§6.3 の Δ） |
| `implied_offset_seconds` | §6.3 で導いた implied offset |
| `selected_datetime` | 採用した日時（オフセット付き ISO8601。タイムゾーン未確定で mtime のみの場合は UTC 表記） |
| `selected_datetime_source` | `EXIF_DATETIME_ORIGINAL` / `EXIF_CREATE_DATE` / `XMP_DATE_CREATED` / `QUICKTIME_CREATION_DATE` / `PHOTO_TAKEN_TIME` / `EXIF_MODIFY_DATE` / `NONE`（旧 `datetime_source`。`CREATION_TIME_FALLBACK` / `FILENAME` は v1.0 未実装のため出現しない） |
| `timezone_source` | `EXPLICIT` / `GPS` / `INFERRED` / `CLI` / `NONE`（旧 `tz_source`。§8.2 追補で `SYSTEM_LOCAL` を廃止） |
| `timezone_offset` | 適用したオフセット（`+09:00`）。未確定なら空（旧 `tz_offset`） |
| `confidence` | `HIGH` / `MEDIUM` / `LOW` |
| `planned_metadata_action` | `NONE` / `WRITE` / `SKIP_TIMEZONE_REQUIRED` / `SKIP_EXISTING` の組み合わせ |
| `planned_mtime_action` | `NONE` / `SET` |
| `status` | 下表参照 |
| `old_mtime` / `new_mtime` | ISO8601 |
| `error` | 例外メッセージ（あれば） |
| `message` | 補足（`XMP:MetadataDate を無視した` `TIMEZONE_REQUIRED_FOR_METADATA` 等の判断根拠。旧 `notes`） |

### 15.3 status 値

要求仕様の値をすべて採用し、必要な区別を追加する。

| status | 意味 |
| --- | --- |
| `NO_CHANGE` | 既に正しい（再実行時の主要ステータス。§17） |
| `OK_EXIF` | 本体の撮影日時を採用（JSON なし） |
| `EXIF_JSON_MATCH` | 本体と JSON が一致（±60 秒以内） |
| `EXIF_JSON_MATCH_TZ_EXPLICIT` | 差分が明示オフセットタグ（`OffsetTimeOriginal` 等）または `--timezone` 指定で確定した tz 差として説明できる（**2026-08-27 追補**。§6.3） |
| `EXIF_JSON_MATCH_TZ_GPS` | 差分が `GPSDateTime` から独立に算出した tz 差として説明できる（**追補**） |
| `EXIF_JSON_MATCH_TZ_INFERRED` | 差分が同一ディレクトリ内の兄弟ファイル（3 件以上）から一貫して確認された tz 差として説明できる（**追補**） |
| `EXIF_JSON_POSSIBLE_TZ` | 15 分刻み・14 時間以内で tz 差の可能性はあるが、単一ファイルの差分のみで根拠が弱い（**追補**。書き込みは行うが要確認扱い） |
| `EXIF_JSON_CONFLICT` | 説明できない食い違い。書き込みしない |
| `JSON_TIME_USED` | JSON `photoTakenTime` からタイムゾーン確定のうえで撮影日時メタデータと mtime の両方を復元（旧 `OK_JSON`。**追補**で名称変更） |
| `JSON_TIME_MTIME_ONLY` | JSON `photoTakenTime`（UTC 絶対時刻）から **mtime のみ** 復元。タイムゾーン未確定のためローカル日時メタデータは書かない（**追補**。§7 ケース【B】） |
| `TIMEZONE_REQUIRED_FOR_METADATA` | `JSON_TIME_MTIME_ONLY` / `NO_CHANGE` の `message` に付与する理由コード。メタデータ書き込みにはタイムゾーン確定が必要である旨を示す（**追補**） |
| `NO_JSON` | sidecar が見つからない |
| `NO_DATE` | どこにも撮影日時がない |
| `AMBIGUOUS_JSON` | JSON 候補が一意に決まらない。書き込みしない |
| `UNSUPPORTED` | 未対応形式 |
| `VERIFY_FAILED` | 書き込み後の読み戻し検証に失敗 |
| `OUTPUT_EXISTS` | 出力先に既存ファイルがありスキップ |
| `SKIPPED` | 利用者指定のフィルタにより除外 |
| `ERROR` | 例外 |

> `JSON_CREATION_FALLBACK` は v1.0 では未実装（§7.1 追補）。将来 `--json-fallback creation-time` を
> 実装する際に復活させる想定で、名称のみ設計に残す。

### 15.4 コンソール出力

- 既定: プログレス表示 + 終了時サマリ（status 別件数）
- `CONFLICT` / `AMBIGUOUS_JSON` / `VERIFY_FAILED` / `ERROR` は **終了時に必ず一覧表示**する
  （レポートを開かなくても気づけるように）
- 終了コード: `0` = 全件解決、`1` = 要確認あり（CONFLICT / AMBIGUOUS / NO_DATE）、`2` = ERROR あり、`3` = 致命的エラー

---

## 16. エラー処理

| 事象 | 扱い |
| --- | --- |
| JSON が壊れている（`JSONDecodeError`） | `ERROR`。ファイルは変更しない。処理は継続 |
| JSON が UTF-8 でない | `errors="replace"` では読まず、UTF-8 / UTF-8-SIG / CP932 の順で試行。全滅なら `ERROR`（GPTH #143 相当） |
| `timestamp` が数値化できない / 負 / 極端な値（< 1970-01-01 または > 現在 + 1 日） | `ERROR` として記録し採用しない（GPTH #436 の 1970 問題対策） |
| `photoTakenTime` が存在するが `timestamp` キーがない | `NO_DATE` 相当として扱い、`notes` に記録 |
| ExifTool が非ゼロ終了 | 当該ファイルを `ERROR`。全体は継続。ExifTool の stderr を `error` 列へ |
| ExifTool 未インストール | 解析のみ続行、書き込み系オプション指定時は起動時に致命的エラー |
| ファイルが読めない / 権限なし | `ERROR` |
| ファイルサイズ 0 | `ERROR`（書き込まない） |
| シンボリックリンク | 既定でスキップ（`--follow-symlinks` で追従。ループ検出必須） |
| 出力先の容量不足 | 実行前チェックで中止。処理中に発生したら即座に中断し、レポートを flush |
| 書き込み中の中断（Ctrl-C） | シグナルハンドラで現在ファイルの `_original` を復元してからレポートを flush して終了 |
| EXIF の `24:00:00` 表記 | 翌日 `00:00:00` に正規化（GPTH #14） |
| EXIF が `0000:00:00 00:00:00` | 「日時なし」として扱う（実データの MP4 初期値でも観測） |

**共通原則**: 1 ファイルの失敗で全体を止めない。ただし **失敗したファイルは絶対に変更を残さない**。

---

## 17. 再実行安全性（idempotency）

### 17.1 NO_CHANGE 判定

書き込み前に、対象ファイルの現在値と期待値を比較する。

```
skip_exif_write := 期待するタグがすべて存在し、値が期待値と秒単位で一致
                   （オフセットを書く設定の場合はオフセットも一致）
skip_mtime      := |現在の mtime − 期待値| < 1 秒
両方成立         → status = NO_CHANGE、ExifTool を呼ばない
```

- mtime 比較に 1 秒の許容を持たせるのは、ファイルシステム間で秒未満の精度が異なるため
- copy mode では **出力先ファイル** に対して同じ判定を行う。既に正しければ再コピーもしない（`--resume` 相当）

### 17.2 保証したい性質

| 性質 | 担保方法 |
| --- | --- |
| 2 回目の実行で全件 `NO_CHANGE` になる | §17.1。受入テストで検証（§22） |
| 2 回目でファイルのバイト列が変わらない | 書き込みをスキップするため。受入テストで sha256 比較 |
| in-place を 2 回実行してもメタデータが増殖しない | 追記対象タグは固定。ExifTool は同名タグを重複させない |
| JSON 退避後の再実行 | JSON が無くなるので `NO_JSON` になるが、**本体に EXIF が書かれているので `OK_EXIF` / `NO_CHANGE`** に落ち着く。これが JSON 退避を「処理成功後のみ」に限定する理由（§13.4-1） |
| 中断後の再開 | `--resume` で前回レポート（CSV/JSONL）を読み込み、`NO_CHANGE` / `OK_*` 済みをスキップ |

---

## 18. 対応ファイル形式

### 18.1 検出対象（拡張子・大文字小文字を区別しない）

| 種別 | 拡張子 |
| --- | --- |
| 静止画 | `.jpg` `.jpeg` `.png` `.heic` `.heif` `.tif` `.tiff` `.gif` `.webp` `.dng` |
| 動画 | `.mp4` `.mov` `.m4v` `.3gp` `.avi` `.mkv` `.mpg` `.mts` |

拡張子は「候補の絞り込み」にのみ使い、**実際の形式判定は ExifTool の `FileType` / `MIMEType` で行う**
（Google フォトは拡張子と中身が食い違うファイルを出力することがある）。

### 18.2 初版の対応範囲（段階的解禁を提案）

| 形式 | 解析 | mtime 設定 | メタデータ書き込み | 根拠 |
| --- | --- | --- | --- | --- |
| **JPEG** | ○ | ○ | **○（既定 ON）** | 実データ 21 件で読み書きを検証済み。最も枯れている |
| **TIFF** | ○ | ○ | **○（既定 ON）** | JPEG と同じ EXIF 構造 |
| **PNG** | ○ | ○ | **○（既定 ON、XMP のみ）** | 実データ 1 件で読み書きを検証済み。EXIF eXIf チャンクは現行版では書かない |
| HEIC / HEIF | ○ | ○ | × | **現行版では未対応**。実サンプルが無く未検証 |
| MP4 / MOV / M4V | ○ | ○ | × | **現行版では未対応**。実 Takeout 動画のサンプルが無い |
| GIF / WebP / DNG / その他 | ○ | ○ | × | 日時タグの規格が形式ごとにばらつく。mtime のみ復元 |
| 上記以外 | — | — | — | `UNSUPPORTED` |

**「初期バージョンで対応範囲を限定するほうが安全か」への回答: はい。**
上表のとおり、**メタデータ書き込みは JPEG / TIFF / PNG に限定し、HEIC・動画は現行版では未対応**である。
mtime の復元だけは全形式で行えるため、メタデータ書き込みに対応していなくても「Finder で撮影日順に並ぶ」という
主要な利用価値は全ファイルで得られる。

### 18.3 Live Photo / Motion Photo

Google フォトは `IMG_1234.HEIC` + `IMG_1234.MOV` のペアや、`.MP` / `.MVIMG` を出力することがある
（GPTH #180 / #224 / #384）。**初版では特別扱いしない**（それぞれ独立したメディアとして処理する）。
JSON が片方にしか無い場合、もう一方は `NO_JSON` になる。
将来的に「同一 stem のペアで日時を共有する」拡張が可能（§23-12）。

---

## 19. CLI 案

### 19.1 基本形

```
photo-date-restore INPUT (--output DIR | --in-place) [options]
```

Python パッケージとして `python -m photo_date_restore` でも、
コンソールスクリプト `photo-date-restore` でも起動できるようにする。
利用者の叩き台にある単一ファイル `photo_date_restore.py` としての実行も維持する（`__main__` ガード）。

### 19.2 オプション一覧

```
位置引数
  INPUT                        解析対象のフォルダ（再帰）

出力モード（いずれか必須）
  -o, --output DIR             別フォルダへ出力（推奨・既定的な使い方）
      --in-place               その場で上書き（明示指定必須）

実行制御
      --dry-run                解析のみ（既定。後方互換のため受け付ける）
      --apply                  実際に書き込む
  -y, --yes                    in-place の確認プロンプトを省略
      --limit N                先頭 N 件だけ処理（試験用）
      --jobs N                 並列数（既定 1。ExifTool 常駐セッションを N 個持つ）
      --resume REPORT          前回レポートを読み、処理済みをスキップ

レポート
      --report PATH            監査レポート出力先（.csv / .jsonl）
      --report-format {csv,jsonl}
      --csv-no-bom
  -v, --verbose / -q, --quiet

日時決定
      --json-fallback {none,creation-time}   既定 none。
                                ★v1.0 では未実装（§7.1 追補）。将来 Phase での opt-in 用に名前のみ予約
      --prefer-json            EXIF より JSON を優先（非推奨・明示時のみ）
      --filename-date          ファイル名からの日時抽出を許可（既定 OFF）
      --conflict-seconds N     一致とみなす許容差（既定 60）
      --tz-tolerance N         オフセット判定の許容誤差秒（既定 90）
      --on-conflict {skip,report-only,use-exif,use-json}   既定 skip

タイムゾーン
      --timezone TZ            IANA タイムゾーン名（例 Asia/Tokyo）
      --utc                    ローカル変換せず UTC + +00:00 で書く
      --tz-from-geo            JSON geoData から推定（要 timezonefinder）
      --no-tz-from-siblings    兄弟ファイルからの推定を無効化（既定は有効）
      --no-write-offset        OffsetTime* を書かない（非推奨）

書き込み対象
      --no-write-exif          メタデータ書き込みを行わない（mtime のみ）
      --no-set-mtime           mtime を変更しない
      --force-birthtime        birth time を SetFile で明示設定（macOS）
      --add-offset             EXIF はあるがオフセットが無い場合にオフセットのみ追記（既定 OFF）
      --write-modifydate       IFD0:ModifyDate も書く（既定 OFF）
      --png-exif               PNG に eXIf チャンクを書く（既定 OFF）
      # `--enable-heic` / `--enable-video` は将来案であり、現行 CLI には存在しない
      --preserve-xattr         -overwrite_original_in_place を使う（xattr 保持・ロールバック不可）

対象の絞り込み
      --include-ext LIST       例 jpg,jpeg,png
      --exclude-ext LIST
      --edited-policy {keep,skip-edited,prefer-edited}   既定 keep
      --follow-symlinks
      --allow-weak-match       T5 の弱マッチを許可（既定 OFF）

出力・JSON の扱い
      --copy-json              copy mode で JSON も出力先へコピー
      --copy-album-metadata    アルバムメタデータ JSON も出力
      --overwrite-output       出力先の既存ファイルを上書き
      --skip-unresolved        解決できなかったファイルを出力しない
      --move-json DIR          in-place 専用。処理済み JSON を退避
      --move-album-metadata    アルバムメタデータも退避対象に含める
      --hash                   退避 index に sha256 を記録

その他
      --exiftool PATH          ExifTool のパス
      --version
```

### 19.3 使用例

```bash
# 1. まず何が起きるか確認（既定 dry-run）
photo-date-restore sources/Takeout --output out --report report.csv

# 2. 問題なければ実行
photo-date-restore sources/Takeout --output out --apply --report report.csv

# 3. 特定アルバムだけ
photo-date-restore "sources/Takeout/Google フォト/サンプルアルバムA" --output out --apply

# 4. タイムゾーンを明示（推奨）
photo-date-restore sources/Takeout --output out --apply --timezone Asia/Tokyo

# 5. 上書き（バックアップ済み前提）
photo-date-restore ~/Photos/Takeout --in-place --apply --timezone Asia/Tokyo

# 6. 上書き + JSON 退避
photo-date-restore ~/Photos/Takeout --in-place --apply \
    --move-json ~/Photos/json-sidecars --timezone Asia/Tokyo

# 7. 監査のみ（何も書かない）
photo-date-restore sources/Takeout --output /dev/null --dry-run --report audit.jsonl
```

### 19.4 利用者の叩き台からの変更点

| 変更 | 理由 |
| --- | --- |
| `--dry-run` を既定にし `--apply` を追加 | fail-safe default。うっかり本実行を構造的に防ぐ |
| `--output` / `--in-place` のどちらかを必須に | 「何もしないつもりが上書きしていた」を防ぐ |
| `--timezone` を明示可能に | UTC → ローカル変換の事故防止（§8）。本ツール最大のリスク箇所 |
| `--json-fallback` で `creationTime` を opt-in 化 | `creationTime` は撮影日時ではないため（§7.1） |
| HEIC / 動画のメタデータ書き込みを現行版では未対応とする | 実サンプルでの検証が済んでいないため（§18.2） |
| `--resume` を追加 | 数万件規模での中断・再開のため |

---

## 20. モジュール構成案

```
takeout-album-exporter/
├── photo_date_restore/
│   ├── __init__.py
│   ├── __main__.py          # python -m photo_date_restore
│   ├── cli.py               # argparse、オプション検証、終了コード
│   ├── config.py            # Options dataclass（全設定を 1 つの immutable オブジェクトに）
│   ├── models.py            # MediaFile / SidecarJson / DateCandidate / Decision / RecordRow
│   ├── scan.py              # 再帰走査、無視リスト、ディレクトリ単位のグルーピング
│   ├── sidecar.py           # ★JSON 分類・索引構築・マッチング（純関数）
│   ├── jsonmeta.py          # Takeout JSON パース・バリデーション
│   ├── exiftool.py          # ExifToolSession（-stay_open 常駐）、read/write/verify
│   ├── metaread.py          # 生タグ → DateCandidate 群（ホワイトリスト適用）
│   ├── tz.py                # ★オフセット解決ラダー（純関数。§8.2）
│   ├── decide.py            # ★日時決定エンジン（純関数）
│   ├── mediawrite.py        # write_media_datetime() ディスパッチ + 形式別実装（§9.2, 2026-08-27 追補）
│   ├── fsdates.py           # mtime / birthtime
│   ├── applier.py           # Applier 抽象 / NoOpApplier / CopyApplier / InPlaceApplier
│   ├── jsonvault.py         # JSON 退避 + _sidecar_index.csv
│   ├── report.py            # CSV / JSONL ライタ、サマリ
│   └── errors.py
├── tests/
│   ├── unit/
│   │   ├── test_sidecar_matching.py
│   │   ├── test_decide.py
│   │   ├── test_tz.py
│   │   └── test_jsonmeta.py
│   ├── integration/
│   │   ├── test_copy_mode.py
│   │   ├── test_inplace_mode.py
│   │   ├── test_jsonvault.py
│   │   └── test_idempotency.py
│   ├── acceptance/
│   │   ├── test_real_takeout.py
│   │   └── assert_sources_untouched.py
│   └── fixtures/
│       └── build_fixtures.py     # 合成 Takeout ツリー生成
├── docs/
│   └── design.md
├── README.md / README-ja.md
├── CHANGELOG.md
└── pyproject.toml
```

### 20.1 設計上の要点

- **★印のモジュール（`sidecar` / `tz` / `decide`）は副作用ゼロの純関数**にする。
  ファイル I/O も ExifTool 呼び出しも含まない。入力は dataclass、出力は dataclass。
  → 本ツールの正しさの中核はここに集中し、**実ファイルなしで網羅的にテストできる**。
- **すべての書き込みは `Applier` 経由**。dry-run は `NoOpApplier` の注入で実現し、
  ロジック側に `if dry_run:` を書かない（§14）。
- `ExifToolSession` は context manager とし、`-stay_open True -@ -` で 1 プロセスを再利用。
  `__exit__` で確実に終了させる。
- Python バージョン: 実機の `python3` は 3.9.6（`/usr/bin/python3`）。
  **3.9 互換で書く**（`X | Y` 型記法や `zoneinfo` の一部挙動に注意。`zoneinfo` は 3.9 から利用可能だが
  `tzdata` パッケージが必要な環境がある）。`pyproject.toml` で `requires-python = ">=3.9"`。
- 依存: 標準ライブラリのみを基本とし、`timezonefinder` は extras（`pip install .[geo]`）。
  ExifTool は外部バイナリ依存として README に明記。

---

## 21. テスト戦略

### 21.1 レイヤ構成

| レイヤ | 対象 | 実ファイル | 目的 |
| --- | --- | --- | --- |
| Unit | `sidecar` / `decide` / `tz` / `jsonmeta` | 不要 | 判断ロジックの網羅。**最重要** |
| Integration | `applier` / `exiftool` / `fsdates` / `jsonvault` | 合成フィクスチャ | 実際に書けるか・壊れないか |
| Acceptance | CLI 全体 | `sources/Takeout`（**読み取り専用**） | 実データでの回帰 |

### 21.2 Unit テストで必ずカバーするケース

**JSON マッチング（`sidecar`）**

| # | ケース | 期待 |
| --- | --- | --- |
| 1 | `IMG.JPG` + `IMG.JPG.json` | T2 |
| 2 | `IMG.JPG` + `IMG.JPG.supplemental-metadata.json` | T1/T2 |
| 3 | truncated suffix `.supplemental-metada.json` / `.supplemental-me.json` / `.suppl.json` / `.s.json` | T2 |
| 4 | `.supplement` に似た別文字列（`.sup-plemental.json`）| マッチしない |
| 5 | stem 切り詰め: 51 文字ルール（`Urlaub ... (38).JPG` + `Urlaub ... (38).JP.json`、GPTH #8） | T4（`title` の裏付けあり） |
| 6 | duplicate: `IMG_4081(1).jpg` + `IMG_4081.JPG(1).json`（`title = "IMG_4081.JPG"`、GPTH #59） | T3 |
| 7 | `IMG_4081.jpg` と `IMG_4081(1).jpg` が同一フォルダに共存 | それぞれ正しい JSON に 1:1 で割り当てられる |
| 8 | `-編集済み` / `-edited` / `-bearbeitet` 付き | T3 |
| 9 | NFD ファイル名 vs NFC `title`（`が`, `ダ`, `é`） | マッチする |
| 10 | 拡張子の大小違い（`img.jpg` vs `title = "IMG.JPG"`） | 第 2 段の casefold でマッチ、tier を 1 段下げる |
| 11 | 同じ JSON に 2 つのメディアがマッチ | 両方 `AMBIGUOUS_JSON` |
| 12 | 1 メディアに同 tier の JSON が 2 件 | `AMBIGUOUS_JSON` |
| 13 | `メタデータ.json` / `metadata.json` / `Metadaten.json` | sidecar から除外 |
| 14 | `photoTakenTime` も `creationTime` も無い JSON | sidecar から除外 |
| 15 | JSON が 0 件 | `NO_JSON` |
| 16 | 拡張子なしメディア（`20030616` + `20030616.json`） | T2 |

**日時決定（`decide`）**

| # | ケース | 期待 status / source |
| --- | --- | --- |
| 1 | EXIF あり・JSON あり・Δ=0 | `EXIF_JSON_MATCH` / `EXIF_DATETIME_ORIGINAL` |
| 2 | EXIF あり・JSON あり・Δ=+09:00・`OffsetTimeOriginal=+09:00` 明示 | `EXIF_JSON_MATCH_TZ_EXPLICIT`、offset `+09:00` |
| 2b | 同上・`GPSDateTime` から +09:00 のみ導出（明示タグなし） | `EXIF_JSON_MATCH_TZ_GPS`、offset `+09:00` |
| 2c | 同上・兄弟 3 件以上が GPS 等で +09:00 確定済み（対象ファイル自身は明示タグ・GPS 無し） | `EXIF_JSON_MATCH_TZ_INFERRED`、offset `+09:00` |
| 2d | 同上・裏付けとなる明示タグ/GPS/兄弟が一切無い（単発） | `EXIF_JSON_POSSIBLE_TZ`、offset `+09:00`（要確認） |
| 3 | Δ=-+09:00（西側）・GPS 裏付けあり | `EXIF_JSON_MATCH_TZ_GPS`、offset `-09:00` |
| 4 | Δ=20700（+05:45 Nepal）・GPS 裏付けあり | `EXIF_JSON_MATCH_TZ_GPS` |
| 5 | Δ=31500（+08:45 Eucla）・GPS 裏付けあり | `EXIF_JSON_MATCH_TZ_GPS` |
| 6 | Δ=7200+37（15 分の倍数でない） | `EXIF_JSON_CONFLICT` |
| 7 | Δ=86400（1 日違い） | `EXIF_JSON_CONFLICT` |
| 8 | Δ=50400（14 時間ちょうど）・GPS 裏付けあり | `EXIF_JSON_MATCH_TZ_GPS`（境界） |
| 9 | Δ=50401 | `EXIF_JSON_CONFLICT`（境界） |
| 10 | EXIF なし・`photoTakenTime` あり・タイムゾーン確定可（`--timezone` 等） | `JSON_TIME_USED` / `PHOTO_TAKEN_TIME` |
| 10b | 同上・タイムゾーン確定不可 | `JSON_TIME_MTIME_ONLY`（`message` に `TIMEZONE_REQUIRED_FOR_METADATA`） |
| 11 | EXIF なし・`photoTakenTime` なし・`creationTime` あり | `NO_DATE`（v1.0 では fallback 自体が未実装。§7.1 追補） |
| 12 | （v1.0 では未実装のため対象外。§7.1 追補で将来ケースとして凍結） | — |
| 13 | `XMP:MetadataDate` のみ存在 | **候補にしない** → `NO_DATE` または JSON 採用 |
| 14 | `XMP-photoshop:DateCreated` のみ存在 | 候補にする |
| 15 | `FileModifyDate` のみ | **候補にしない** |
| 16 | EXIF `24:00:00` | 翌日 `00:00:00` に正規化 |
| 17 | EXIF `0000:00:00 00:00:00` | 日時なしとして扱う |
| 18 | `timestamp = "0"` / 負値 / 未来 | `ERROR`、採用しない |

**タイムゾーン（`tz`）**

- `OffsetTimeOriginal` あり → `EXIF_OFFSET`
- `GPSDateTime` から +09:00 を導出（10 秒の測位遅延を含む実データ相当値）
- 兄弟推定（全一致 / 不一致混在で結果が変わること）
- `geoData = 0.0/0.0` を「位置情報なし」として扱うこと

### 21.3 合成フィクスチャ

`tests/fixtures/build_fixtures.py` で、**実データを一切使わずに** Takeout 風ツリーを生成する。

- 画像は Pillow で 8×8 の極小 JPEG / PNG を生成（リポジトリにバイナリを置かない）
- EXIF は ExifTool で後から付与（あり / なし / オフセットあり / GPS あり の 4 種）
- 動画は ffmpeg で 1 秒の極小 MP4 を生成（ffmpeg が無い環境では該当テストを skip）
- JSON は §21.2 の全ケースを網羅するよう生成
- macOS 以外でも動くよう、NFD ケースは **バイト列を明示して生成**する

### 21.4 実データ保護テスト（必須）

`tests/acceptance/assert_sources_untouched.py`

```
実行前: sources/ 配下の全ファイルについて (相対パス, サイズ, mtime_ns, sha256) を記録
テスト実行
実行後: 同じスナップショットを取り、完全一致を assert
        ファイルの増減（新規ディレクトリ含む）も検出する
```

- acceptance テストは **常に `--output <tmpdir>`** で実行する
- CI では `sources/` を読み取り専用でマウント、またはテスト開始時に `chmod -R a-w sources` を実施
- `--in-place` の acceptance テストは **`sources/` のコピーに対してのみ**実行する

---

## 22. 実データを使った受入テスト

複数の Takeout アルバムを、個人情報を含まない合成・一般化サンプルとして検証する。

- sidecar は一意に T1 で対応付け、既存の信頼できる EXIF/XMP は書き換えない。
- GPS または同一ディレクトリの根拠で timezone を確定できる場合は、既存日時と JSON の差を timezone 表現として扱う。
- timezone が確定できない場合は `JSON_TIME_MTIME_ONLY` とし、撮影日時メタデータは書かない。
- `creationTime` と `XMP:MetadataDate` は撮影日時に採用しない。
- copy mode の出力はメディアのみとし、2 回目の適用で不要な ExifTool 書込みを行わず `NO_CHANGE` となる。
- protected input はパス、数、サイズ、`mtime_ns`、SHA-256 が作業前後で不変である。
- in-place と JSON 退避の検証は必ず一時コピーに対して行う。

## 23. 未解決事項（実装前に人間が判断すべきこと）

| # | 事項 | 選択肢 | 推奨 |
| --- | --- | --- | --- |
| 1 | **タイムゾーンの既定値** | (a) `--timezone` を必須にする / (b) システムローカルを既定にし警告を出す / (c) `--utc` を既定にする / (d) システムローカルは候補にせず、根拠（EXPLICIT/GPS/INFERRED/CLI）が無ければメタデータ書き込みを SKIP し mtime のみ復元する | **(d) に確定（2026-08-27 追補）**。撮影地は実行環境のタイムゾーンと一致するとは限らないため、(b) は撤回した。§8.2 / §7 ケース【B】を参照 |
| 2 | **`creationTime` fallback の既定** | 既定 OFF / 既定 ON | **既定 OFF**。実データでアルバム内全件同一値であることを確認済み（§7.1） |
| 3 | **`creationTime` 採用時に EXIF へ書くか** | mtime のみ / EXIF にも書く | **mtime のみ**。撮影日時ではない値を `DateTimeOriginal` に書くのは避けたい |
| 4 | **birth time の扱い** | 何もしない（副作用に任せる）/ `SetFile` で明示設定 | **何もしない**。§10.2 の実測で mtime を過去に設定すれば btime も追随する |
| 5 | **`-編集済み` 版の扱い** | 両方出す / 原版のみ / 編集版のみ | **両方出す（既定）**。`--edited-policy` で選択可能に |
| 6 | **アルバム情報の保存方法** | レポートのみ / `albums.csv` / JSON もコピー / アルバム別フォルダ構造の維持のみ | **レポート + `albums.csv`**。ただしリポジトリ名が `takeout-album-exporter` である以上、将来アルバム出力機能と統合する可能性がある。設計の整合を先に決めておきたい |
| 7 | **HEIC / 動画を初版に含めるか** | opt-in / 既定 ON / 初版では非対応 | **初版では非対応**。実サンプルが無いため既定 ON にする根拠がない。将来対応には実 Takeout の HEIC / MP4 / MOV サンプルが必要 |
| 8 | **GPS・説明文・人物タグの書き戻し** | 初版に含める / 将来 | **将来**（GPTH #195 / #273 で要望が多い機能。日時と混ぜると検証が複雑化する） |
| 9 | **Google Drive 同期フォルダ上での in-place 実行** | 警告のみ / 禁止 | **警告のみ**。今回の作業ディレクトリ自体が Google Drive 上にあるため、現実的に発生しうる |
| 10 | **`sources/Takeout` 配下に生成された空の `.claude` ディレクトリ** | 削除する / 放置する | **削除を推奨**（`rmdir sources/Takeout/.claude/.cc-writes` 等）。ツールの走査対象にはならない（隠しディレクトリ除外）が、原データを汚したままにしたくない |
| 11 | **既存 EXIF に `OffsetTimeOriginal` を追記するか** | 既定 OFF / 既定 ON | **既定 OFF**（`--add-offset`）。「EXIF があるものは触らない」原則を厳守したいが、オフセットを補うと将来の可搬性が上がるという利点もある |
| 12 | **Live Photo / Motion Photo のペア処理** | 初版に含める / 将来 | **将来** |
| 13 | **並列処理を初版に入れるか** | 入れる / 逐次のみ | **逐次のみ（`--jobs 1` 固定）で初版を出す**。並列化は検証コストが高く、書き込み系との相性が悪い。数万件規模の実測後に判断 |
| 14 | **レポート CSV の BOM** | BOM 付き / なし | **BOM 付き**（Excel での日本語表示のため）。`CLAUDE.md` の BOM 規定は Markdown 向けなので抵触しないが、方針として明記しておきたい |

---

## 24. 実装フェーズ案

Codex CLI への引き継ぎ単位として、以下のフェーズに分割する。各フェーズ末で Claude がレビューを行う。

### Phase 0: 解析エンジン（書き込みなし）

- `scan` / `jsonmeta` / `sidecar` / `metaread` / `exiftool`（読み取りのみ）/ `tz` / `decide` / `report`
- CLI は `--dry-run` のみ実装。`--apply` は「未実装」エラー
- Unit テスト（§21.2 全ケース）+ 合成フィクスチャ生成
- **完了条件**: `sources/Takeout` に対する dry-run レポートが §22.1〜22.3 の期待値と一致する
- この時点で「壊すコードが 1 行も無い」状態を作り、判断ロジックの正しさを確定させる

### Phase 1: copy mode

- `applier`（`NoOpApplier` / `CopyApplier`）/ `fsdates` / ExifTool 書き込み / 読み戻し検証
- 対応形式: JPEG / TIFF / PNG
- idempotency（`NO_CHANGE`）
- **完了条件**: §22.3 の copy mode 受入テスト（2 回実行での `NO_CHANGE` と sha256 一致、`sources/` 不変）が通る

### Phase 2: in-place mode + JSON 退避

- `InPlaceApplier`（`_original` バックアップ + 検証 + ロールバック）
- 確認プロンプト、クラウド同期フォルダ警告
- `jsonvault` + `_sidecar_index.csv`
- **完了条件**: §22.4 が通る

### Phase 3: タイムゾーン解決の充実 + 堅牢化

- GPS / 兄弟 / geoData（extras）によるオフセット解決
- `--resume`、エラー処理の網羅（§16）、シグナルハンドリング
- README / README-ja / CHANGELOG の整備
- **完了条件**: §21.2 のタイムゾーンテストが通り、`tz_source` がレポートで正しく分岐する

### Phase 4: 形式拡張（実サンプル入手後）

- HEIC、MP4 / MOV のメタデータ書き込み
- Live Photo ペア処理の検討
- 並列化（`--jobs`）の検討
- **前提**: 利用者から実 Takeout の HEIC / 動画サンプルを入手できること（§23-7）

---

## 付録 A. 参考実装・Issue 調査の要約

### A.1 GooglePhotosTakeoutHelper (GPTH) から採り入れる考え方

| 採り入れる点 | 出典 | 本ツールでの扱い |
| --- | --- | --- |
| JSON ファイル名の 51 文字切り詰めルール | `_shortenName`（Issue #8） | §5.3-e で採用。ただし `title` による裏付けを必須にする |
| `(n)` の位置スワップ（`image(11).jpg` ↔ `image.jpg(11).json`） | `_bracketSwap`（Issue #59 / #175 / #188） | §5.3-c で採用 |
| `-edited` 系サフィックスの多言語リスト（`-編集済み` を含む） | `extras.dart` | §5.3-b でそのまま流用 |
| macOS の NFD 問題に対する NFC 正規化 | PR #247 | §5.2 で採用。**全キー比較で NFC 統一** |
| 拡張子なしファイルへの対応 | `_noExtension` | §5.3-d で採用 |
| `photoTakenTime` を第一とする方針 | `json_extractor.dart` | §6 で採用（ただし EXIF 優先の点で異なる） |

### A.2 GPTH の問題点と本ツールでの回避

| GPTH の問題 | 出典 Issue | 本ツールの対応 |
| --- | --- | --- |
| `.supplemental-metadata.json` に未対応（v3 の `_jsonForFile` は `<name>.json` しか試さない） | #353 / #448 / #449（**いずれも未解決**） | §5.2 で suffix の前方一致分解を実装。切り詰め全パターンに対応 |
| 最初にヒットした JSON を無条件採用し、曖昧性を検出できない | #92 / #435 | §5.4 の tier + 1:1 制約 + `AMBIGUOUS_JSON` |
| `_removeDigit`（`(1)` 除去）が誤マッチしやすい | `tryhard` 扱いになっている | §5.3-f を既定 OFF、`title` の裏付け必須 |
| ファイル名からの日時推測が誤日付・1970-01-01 を生む | #436 | `--filename-date` を既定 OFF（§6.1-9） |
| mtime しか設定せず EXIF `DateTimeOriginal` を書かない | #149 / #195 / #450 | §9 で EXIF を明示的に書く。読み戻し検証まで行う |
| 既定でファイルを移動する（原本が消える） | README / 参考記事でも「事前バックアップ必須」と注意喚起 | **移動しない**。copy mode を既定 |
| 大文字小文字の違いでマッチ失敗 | #435 | §5.2 で casefold 第 2 段 |
| 非 UTF-8 JSON でクラッシュ | #143 | §16 で多段デコード |
| `altitude: NaN` で例外 | #51 | §16 で値検証 |
| EXIF `24:00:00` で例外 | #14 | §16 で正規化 |
| タイムゾーンの扱いが曖昧で数時間ずれる | #436 ほか | §6.3 / §8 が本設計の中核 |

### A.3 参考記事（storagelab.jp）から

- 「Takeout すると全ファイルの日時がダウンロード日になる」という現象の一般的な説明。
  §3.5-4 の実測（`FileModifyDate` が全件 2026-08-26）と一致する。
- 「2024 年以降の Takeout では `.supplemental-metadata` が付く」との注意喚起。
  本データ（2026 年取得）は **全件がこの形式**であり、旧形式は 1 件も無い。
  → **新形式への対応は必須要件であって、オプションではない。**
- 記事は Windows + GPTH GUI 前提の手順。本ツールは macOS + CLI + 原本非破壊という別の立ち位置を取る。

---

## 付録 B. 一般化した検証根拠

複数の一般化サンプルにより、JSON `title` と basename の照合、supplemental-metadata 形式、既存日時の優先、timezone 根拠、`creationTime` と `MetadataDate` の除外を検証した。実際のファイル名、アルバム名、撮影日時、位置情報、および件数は公開文書に記載しない。
