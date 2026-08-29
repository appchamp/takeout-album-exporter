# リリース手順

英語: [../en/release.md](../en/release.md)

この文書は maintainer 向けです。一般利用者は [usage.md](usage.md) を参照してください。

## 配布 ZIP の作成と検証

`dist/` は PyInstaller の生成物、`release/` は配布 ZIP の置き場であり、いずれも Git 管理対象外です。`dist/Photo Date Restore.app` から macOS の `ditto` で ZIP を作成します。`zip` コマンドは拡張属性を落とすことがあるため使いません。

```bash
ditto -c -k --sequesterRsrc --keepParent \
  "dist/Photo Date Restore.app" \
  "release/Photo-Date-Restore-v1.1.0-macOS-Apple-Silicon.zip"
```

展開して `.app` が起動することを確認します。

```bash
mkdir -p /tmp/photo-date-restore-test
ditto -x -k \
  "release/Photo-Date-Restore-v1.1.0-macOS-Apple-Silicon.zip" \
  /tmp/photo-date-restore-test
```

SHA-256 を主たる整合性確認値、MD5 を補助的な照合値として算出し、GitHub Release の説明へ記載します。

```bash
shasum -a 256 "release/Photo-Date-Restore-v1.1.0-macOS-Apple-Silicon.zip"
md5 "release/Photo-Date-Restore-v1.1.0-macOS-Apple-Silicon.zip"
```

ハッシュ値はビルドごとに変わるため、README や利用マニュアルへは埋め込みません。Apple Silicon（arm64）向け配布物は unsigned / not notarized であり、GitHub Release へ手動で添付します。

## リリース前の手動 GUI テスト

- GUI を起動でき、Input / Output folder を選択できる
- dry-run、既定 ON の Verbose output、timezone、出力上書き、監査 report の各切替を確認できる
- dry-run でも Verbose output が処理ファイルごとに説明を表示し、内部 status は report に残る
- 大きめのディレクトリで `Reading metadata:` から `Analyzing:` への進捗が表示される
- Cancel が次のバッチ境界または現在のファイルの完了後に安全に停止し、部分結果と report を保持する
- 正常完了・Cancel 完了時に別ウィンドウ（popup）が出ない
- About で Version、著作者、MIT License、Project URL を確認できる
- ExifTool の有無それぞれで、パス表示または明確な導入案内を確認できる
- dry-run で出力を作成せず、apply で copy mode の出力を確認できる
- 不正な入力後も再試行でき、成功後は `Open Output Folder` が Finder を開く
