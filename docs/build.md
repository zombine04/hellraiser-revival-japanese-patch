# 抽出とビルド

開発にはPython 3.12を使用し、Windows用生成ツールのビルドにはRust 1.90.0とMSVCを使用します。翻訳データの検査・配布ビルド・CIは原本不要です。導入時のみ利用者のゲーム原本を参照します。依存ツールは `tools.lock.json` のバージョンとSHA-256で固定しています。

```powershell
py -3.12 scripts/extract.py --game-dir '<ゲームのインストール先>'
py -3.12 scripts/catalog.py
py -3.12 scripts/catalog.py --region engine
py -3.12 scripts/validate_translations.py
py -3.12 scripts/build_runtime.py
py -3.12 -m unittest discover -s tests -v
py -3.12 scripts/build.py --preview
```

抽出物は `.local/` のみへ保存します。`catalog/game.json` は識別情報、原文ハッシュ、原文のSHA-256、変数・タグ・改行の制約だけを含みます。原文は収録しません。`catalog/supported-builds.json` は確認済みのゲーム版名を記録します。現行の統合パッチ（配布manifestのschema 2）では、`Version.txt` を製品版の識別に使いますが、確認済み版との完全一致や続行確認は要求しません。版名が欠けた場合はSteamの製品版AppIDと導入先の一致で識別します。生成ツールは対象コンテナの索引全体、必要な圧縮ブロックと展開後のデータ、生成結果をSHA-256で照合します。大容量のucas全体を読むことはありません。データ不一致は強制適用指定でも停止します。索引の変更でも停止するため、すべてのゲーム更新に追随できる保証はありません。デモ版・製品不明の導入先と、デモ版パッチとの混在は引き続き拒否します。原本検証を持たない旧配布形式（schema 1）には従来の版名照合と警告・続行確認を残しています。

Engine領域は `catalog/engine-scope.json` の調査済みキーだけを `catalog/engine.json` に収録し、訳文は `translations/engine/*.json` へ保存します。GameとEngineで同じ名前空間・キーがあっても、領域ごとにハッシュと翻訳を検査します。対象範囲の欠落や、カタログ間の対応ゲーム版の不一致はビルドを停止させます。Engineの対象外判定は `translations/engine-exclusions.json` を使います。

正式訳は `translations/release/*.json` の `entries` 配列に記録します。各項目は `namespace`、`namespace_hash`、`key`、`key_hash`、`source_hash`、`ja`、`status` を持ちます。要確認事項は `review_note`、意図的な原語維持は `retained_reason`、実機表示確認は `display_checked` に記録します。レビュー方針は[翻訳方針](translation-guide.md)を参照してください。

正式ビルドは `py -3.12 scripts/build.py` です。未訳・要確認・キー欠落があると停止します。製品版の対象範囲外と確認したキーのみ `translations/exclusions.json` に名前空間・キー・理由・確認根拠を記録できます。判断できないキーを件数合わせのために除外してはいけません。

ビルドはLocResの読取・書込の一致、Pakの収録パスと再展開したLocResの一致を検査します。Pakには訳文のLocResだけを収録します。同名のIoStoreには、`jp_patch/fonts.py` が生成する2つのUFont参照設定だけを収録します。設定は同梱済みのNotoSansJPを参照し、フォント本体をコピーしません。ZIPには自作の `GeneratePatch.exe`、`ui-patch.json`、依存ライセンスを追加します。Retoc・repak・Oodle DLL、抽出した元ゲーム資産、ログは含めません。

フォント設定はUE5.6の対応版に限定したバイナリ生成処理です。元資産へのバイト置換ではなく、公開ソースからヘッダー・プロパティ・参照先を生成します。独立した読取テストでRegular／Bold、文字範囲、言語と参照先を検証し、配布物検査ではIoStoreの収録パスと全バイトの再生成一致を確認します。Retocは `--no-parallel` で実行し、資産の収録順を固定します。

PakにはGameとEngineのLocResを固定パスに収録します。repak v0.2.3のpack処理は並列読込の完了順でファイルを書くため、呼び出すプロセスに限って `RAYON_NUM_THREADS=1` を指定し、複数ファイルの格納順を固定します。ツール本体の改修は不要です。

ZIPのファイル順序、時刻、改行、文字コードを固定します。配布ファイルのSHA-256一覧とZIP自体のSHA-256を `dist/` に出力します。試作ZIPは `-preview` を付け、正式配布物と区別します。`manifest.json` の `coverage.regions` には領域別、`coverage` の各件数には合計を記録します。

試作ビルドは `translations/release/*.json` の作業中の訳を優先し、まだ正式訳のないキーだけを初期試作の `translations/probe.json` から補います。未訳と明示した正式訳を古い試作訳で埋めることはありません。要確認の訳は試作で表示できますが、正式ビルドでは従来どおり停止します。README冒頭には実際に収録した件数を表示します。

ゲーム更新時は旧カタログをローカルへ保存してから抽出し、`scripts/catalog.py --compare <旧カタログ>` を実行します。Engineには `--region engine` を追加し、領域ごとに比較結果を保存します。追加・削除・変更の識別情報だけを `.local/catalog-diff-game.json` または `.local/catalog-diff-engine.json` に出力します。Engineの新しい名前空間・入力機器が必要になっていないかも再調査し、必要なら対象範囲を更新します。変更項目の訳文と原文ハッシュを照合し、要確認へ戻して再レビューしてください。対応版の追加には実機確認が必要です。

導入テストはゲームと無関係な自作データを使います。WindowsではPowerShell 5.1の実処理を起動し、正常導入、再導入、更新、削除、未知・改変・欠落ファイル、版名が異なる統合パッチの導入、対象外データの更新、索引・対象データの不一致による既存パッチの保持、旧配布形式への警告と確認、書き込み失敗などを確認します。実機の通しプレイは別途必要です。

## デモ版からの移行

旧 `catalog/` と `translations/` を `.local/demo-baseline/` に保存し、製品版の抽出・カタログ生成後に実行します。

```powershell
py -3.12 scripts/migrate_translations.py --baseline .local/demo-baseline --output .local/migration-candidate
```

出力先は未作成の `.local/` 内ディレクトリに限ります。原文SHA-256、識別ハッシュ、書式がすべて一致する訳だけを引き継ぎ、製品版の実機表示状態は未確認へ戻します。変更・追加は空の未訳、削除は移行対象外とし、候補を確認してから翻訳ファイルへ反映します。原文を補ってビルドを通すことはしません。初期試作の補助訳は引き継がず空にします。

`scripts/build_probe.py` はフォント参照と導入・削除処理を含むpreview ZIPを生成します。個別の手動試作ファイルは生成しません。ビルド時のシェーダー文言だけに必要なCRLF変換は `jp_patch/runtime_text.py` で行い、公開訳文はLFのまま管理します。

## 導入時の統合生成

`runtime/` のRustツールを `scripts/build_runtime.py` でビルドし、`.local/runtime/` に保存します。依存関係はCargo.lock、Rustはrust-toolchain.tomlで固定します。生成ツールにはoozextractの展開実装を静的に組み込み、利用者にPython・Rust・.NETや追加DLLを要求しません。通信処理も持ちません。依存ライセンスは `RUNTIME_LICENSES.txt` へ収録します。

配布するIoStoreは従来のフォント設定だけです。`distribution/ui-patch.json` は原本のコピー元範囲、追加する変更バイト、入力と出力のハッシュを持ちます。完成したウィジェットは配布しません。追加バイトはコンテナの識別情報と処理変更に限定し、更新時は文字列・未変更データの混入をレビューします。公開検査では追加バイトの合計に上限を設けます。

インストーラーは原本を読み取り専用で開き、3つの圧縮範囲だけを展開し、統合IoStoreをゲーム側の `.local/` に生成します。原本の圧縮バイトを照合してからデコーダーへ渡します。生成した2ファイルと配布Pakの照合後に、従来と同名の3ファイルを更新します。配布manifestはschema 2ですが、導入済み管理情報はschema 1を保つため、従来のアンインストーラーでも3ファイルを削除できます。削除時は生成ツールや原本を読みません。

CIは最初にWindowsで生成ツールと依存ライセンスをビルドします。同じ生成ツール成果物をWindows・Linuxの配布ビルドと正式リリース再生成で使用し、ZIP全体の一致を検証します。異なるOSでWindows実行ファイルを独立コンパイルして一致させる検査ではありません。生成ツールのソース指紋とハッシュも照合します。
