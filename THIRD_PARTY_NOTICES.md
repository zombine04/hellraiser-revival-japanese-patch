# 使用ツールと参照資料

## repak 0.2.3

- https://github.com/trumank/repak
- ライセンス: MIT OR Apache-2.0
- ビルド・解析に使用。ゲーム利用者向けZIPには実行ファイルを同梱しません。
- 配布アーカイブのバージョンとSHA-256は `tools.lock.json` に固定しています。

## retoc 0.1.5

- https://github.com/trumank/retoc
- ライセンス: MIT
- UE5.6で追加Pakを読み込むため、自作のUFont参照設定だけを収録するIoStoreコンテナを生成します。
- 実行ファイルはゲーム利用者向けZIPには同梱しません。バージョンとSHA-256を固定しています。

## LocRes形式の確認

Unreal Engineのローカライズ資料とCUE4ParseのLocRes v3読取処理を参照して形式を確認しています。公開ビルドはPython標準ライブラリで実装し、CUE4Parseを実行依存にはしません。

- https://dev.epicgames.com/documentation/en-us/unreal-engine/text-localization-in-unreal-engine?application_version=5.6
- https://github.com/FabianFG/CUE4Parse （Apache-2.0）

## 原本展開用ライブラリ

repakが使用するOodleライブラリはローカル解析専用です。ゲーム原本、抽出したフォント、Oodleのバイナリは公開リポジトリにも配布ZIPにも含めません。日本語化パッチのビルドは非圧縮Pakを生成し、Oodleを必要としません。

## フォント参照設定

表示にはゲーム同梱のNotoSansJP Regular／Boldを使用します。フォント本体の複製・再配布は行わず、UFontの参照先と文字範囲だけを自作ツールで生成します。バイナリ形式の確認には、RetocのUE5.6パッケージ処理とCUE4ParseのUFont／FFontData読取処理を参照しました。

- https://github.com/trumank/retoc/blob/v0.1.5/retoc/src/legacy_asset.rs
- https://dev.epicgames.com/documentation/en-us/unreal-engine/asset-localization-in-unreal-engine?application_version=5.6

ゲーム本体・名称・原作の権利は各権利者に帰属します。本リポジトリのライセンスはゲーム原本への権利を付与するものではありません。

## 導入時の生成ツール

`GeneratePatch.exe` は本リポジトリのRustソースからビルドします。oozextract 0.5.5（MIT）で対象の圧縮データを展開し、OodleのプロプライエタリDLLは使用・同梱しません。serde、serde_json、sha2などを含む固定済み依存関係と著作権・ライセンス表記は、同梱の `RUNTIME_LICENSES.txt` を参照してください。既存の `LICENSE` は変更せず同梱します。
