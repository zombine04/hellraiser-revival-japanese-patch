# 抽出とビルド

開発にはPython 3.12を使用します。ゲーム原本の参照は抽出工程だけで行い、翻訳データの検査・配布ビルド・CIは原本不要です。依存ツールは `tools.lock.json` のバージョンとSHA-256で固定しています。

```powershell
py -3.12 scripts/extract.py --game-dir '<ゲームのインストール先>'
py -3.12 scripts/catalog.py
py -3.12 scripts/catalog.py --region engine
py -3.12 scripts/validate_translations.py
py -3.12 -m unittest discover -s tests -v
py -3.12 scripts/build.py --preview
```

抽出物は `.local/` のみへ保存します。`catalog/game.json` は識別情報、原文ハッシュ、原文のSHA-256、変数・タグ・改行の制約だけを含みます。原文は収録しません。`catalog/supported-builds.json` はゲーム同梱の `Version.txt` と照合する対応版名です。インストーラーは大容量のゲームコンテナをハッシュせず、製品版と確認できる未対応ビルドには互換性を警告して続行確認を表示します。デモ版・製品不明の導入先と、デモ版パッチとの混在は続行指定でも拒否します。

Engine領域は `catalog/engine-scope.json` の調査済みキーだけを `catalog/engine.json` に収録し、訳文は `translations/engine/*.json` へ保存します。GameとEngineで同じ名前空間・キーがあっても、領域ごとにハッシュと翻訳を検査します。対象範囲の欠落や、カタログ間の対応ゲーム版の不一致はビルドを停止させます。Engineの対象外判定は `translations/engine-exclusions.json` を使います。

正式訳は `translations/release/*.json` の `entries` 配列に記録します。各項目は `namespace`、`namespace_hash`、`key`、`key_hash`、`source_hash`、`ja`、`status` を持ちます。要確認事項は `review_note`、意図的な原語維持は `retained_reason`、実機表示確認は `display_checked` に記録します。レビュー方針は[翻訳方針](translation-guide.md)を参照してください。

正式ビルドは `py -3.12 scripts/build.py` です。未訳・要確認・キー欠落があると停止します。製品版の対象範囲外と確認したキーのみ `translations/exclusions.json` に名前空間・キー・理由・確認根拠を記録できます。判断できないキーを件数合わせのために除外してはいけません。

ビルドはLocResの読取・書込の一致、Pakの収録パスと再展開したLocResの一致を検査します。Pakには訳文のLocResだけを収録します。同名のIoStoreには、`jp_patch/fonts.py` が生成する2つのUFont参照設定だけを収録します。設定は同梱済みのNotoSansJPを参照し、フォント本体をコピーしません。ZIPにはツール本体、抽出した元ゲーム資産、ログを含めません。

フォント設定はUE5.6の対応版に限定したバイナリ生成処理です。元資産へのバイト置換ではなく、公開ソースからヘッダー・プロパティ・参照先を生成します。独立した読取テストでRegular／Bold、文字範囲、言語と参照先を検証し、配布物検査ではIoStoreの収録パスと全バイトの再生成一致を確認します。Retocは `--no-parallel` で実行し、資産の収録順を固定します。

PakにはGameとEngineのLocResを固定パスに収録します。repak v0.2.3のpack処理は並列読込の完了順でファイルを書くため、呼び出すプロセスに限って `RAYON_NUM_THREADS=1` を指定し、複数ファイルの格納順を固定します。ツール本体の改修は不要です。

ZIPのファイル順序、時刻、改行、文字コードを固定します。配布ファイルのSHA-256一覧とZIP自体のSHA-256を `dist/` に出力します。試作ZIPは `-preview` を付け、正式配布物と区別します。`manifest.json` の `coverage.regions` には領域別、`coverage` の各件数には合計を記録します。

試作ビルドは `translations/release/*.json` の作業中の訳を優先し、まだ正式訳のないキーだけを初期試作の `translations/probe.json` から補います。未訳と明示した正式訳を古い試作訳で埋めることはありません。要確認の訳は試作で表示できますが、正式ビルドでは従来どおり停止します。README冒頭には実際に収録した件数を表示します。

ゲーム更新時は旧カタログをローカルへ保存してから抽出し、`scripts/catalog.py --compare <旧カタログ>` を実行します。Engineには `--region engine` を追加し、領域ごとに比較結果を保存します。追加・削除・変更の識別情報だけを `.local/catalog-diff-game.json` または `.local/catalog-diff-engine.json` に出力します。Engineの新しい名前空間・入力機器が必要になっていないかも再調査し、必要なら対象範囲を更新します。変更項目の訳文と原文ハッシュを照合し、要確認へ戻して再レビューしてください。対応版の追加には実機確認が必要です。

導入テストはゲームと無関係な自作データを使います。WindowsではPowerShell 5.1の実処理を起動し、正常導入、再導入、更新、削除、未知・改変・欠落ファイル、対応版の一致、未対応版への警告と確認、書き込み失敗などを確認します。実機の通しプレイは別途必要です。

## デモ版からの移行

旧 `catalog/` と `translations/` を `.local/demo-baseline/` に保存し、製品版の抽出・カタログ生成後に実行します。

```powershell
py -3.12 scripts/migrate_translations.py --baseline .local/demo-baseline --output .local/migration-candidate
```

出力先は未作成の `.local/` 内ディレクトリに限ります。原文SHA-256、識別ハッシュ、書式がすべて一致する訳だけを引き継ぎ、製品版の実機表示状態は未確認へ戻します。変更・追加は空の未訳、削除は移行対象外とし、候補を確認してから翻訳ファイルへ反映します。原文を補ってビルドを通すことはしません。初期試作の補助訳は引き継がず空にします。

`scripts/build_probe.py` はフォント参照と導入・削除処理を含むpreview ZIPを生成します。個別の手動試作ファイルは生成しません。ビルド時のシェーダー文言だけに必要なCRLF変換は `jp_patch/runtime_text.py` で行い、公開訳文はLFのまま管理します。
