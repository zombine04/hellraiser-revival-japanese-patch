# 2026年11月7日のゲーム更新調査

## 判断

日本語パッチの更新が必要です。既存訳の原文に変更はありませんが、Gameに15件の追加があります。また、ニュース用UI資産が変わったため、v1.2.1の統合UI生成は新しい原本に対応できません。

本調査では配布物・翻訳・対応版の登録を変更していません。ゲームへの導入、起動、表示確認も実施していません。

## 比較対象と結果

- 旧版: `1.0.1.227219_HellraiserGame_Shipping_27809_ReleasePatch1_Test`
- 新版: `1.2.0.227791_HellraiserGame_Shipping_29359_ReleasePatch2_Test`
- 比較基準: developの公開カタログ、保存済みの旧Engine英語LocRes、配布済みv1.2.1のUI生成手順。

| 対象 | 結果 |
| --- | --- |
| Game英語 | 6,846 → 6,861件。追加15、削除0、変更0 |
| Game簡体字中国語 | 6,861件。英語とのキー差分・原文ハッシュ不一致0 |
| Engine英語全体 | 54,314件。追加・削除・変更すべて0 |
| Engine翻訳対象 | 164件。追加・削除・変更すべて0 |
| NotoSansJP Regular／Bold、置換対象のフォント設定 | 新しいコンテナ索引にも存在。内容一致・実機描画は未検証 |

Game英語とEngineの変更判定には、識別ハッシュだけでなく原文SHA-256、変数・タグ・改行の制約を含めています。原文と抽出物、比較ログはローカル専用領域に保存しています。

## 追加されたGameの識別キー

| 名前空間 | キー |
| --- | --- |
| `Item.Name` | `Item_CoilsVariant.Name` |
| `ST_UI_Options` | `fov_description` |
| `ST_UI_Options` | `xbox_input_type_psx_description` |
| `ST_UI_Optionsvolume` | `fov_name` |
| `ST_UI_Optionsvolume` | `hdr_max_brightness` |
| `ST_UI_Optionsvolume` | `hdr_max_brightness_description` |
| `ST_UI_Optionsvolume` | `hdr_name` |
| `ST_UI_Optionsvolume` | `hdr_paper_white` |
| `ST_UI_Optionsvolume` | `hdr_paper_white_description` |
| `ST_UI_Optionsvolume` | `hdr_saturation` |
| `ST_UI_Optionsvolume` | `hdr_saturation_description` |
| `ST_UI_Optionsvolume` | `hdr_settings` |
| `ST_UI_Optionsvolume` | `hdr_tone_mapping` |
| `ST_UI_Optionsvolume` | `hdr_tone_mapping_description` |
| `ST_UI_Optionsvolume` | `xbox_dualsense_controller_verb_imperative` |

内訳はFOV 2件、HDR 10件、コントローラー設定2件、アイテム名1件です。追加分は現行パッチに未収録で、表示時に日本語にならない可能性があります。既存訳の一括再翻訳は不要ですが、追加分の翻訳・文脈確認が必要です。

## ニュース・日時UI

配布済みv1.2.1のGeneratePatchを、新しいゲーム原本とローカルの空の出力先に対して実行したところ、互換性不一致を示す終了コード2でした。ゲーム側のファイルは変更していません。

対象チャンクを個別に取り出し、生成手順が要求するサイズ・SHA-256と比較しました。

| 対象 | サイズ（旧 → 新、バイト） | SHA-256照合 |
| --- | --- | --- |
| `W_MOTD` | 65,089 → 65,392 | 不一致 |
| `W_SaveLoadScreenSaveSlotButton` | 52,025 → 52,025 | 一致 |
| `W_SaveLoadScreenPlaythroughSlotButton` | 32,752 → 32,752 | 一致 |

ニュースUIの変更内容を再解析し、生成手順を更新する必要があります。日時の2資産は不変ですが、現行の生成処理は3資産をまとめて照合するため、v1.2.1を新原本へ再導入するとニュース・日時の両方を見送り、基本の日本語化に切り替える設計です。

調査時点の導入済みパッチはv1.2.1で、管理情報はUI変更あり、統合IoStoreも旧版向けの生成結果と一致しました。ゲーム更新だけでは再生成されず、古いニュースUIを上書きし続ける状態です。実際の不具合発生は未確認ですが、新版対応候補で置き換えて確認する必要があります。

## 更新作業と確認事項

1. 新カタログを反映し、追加15件を翻訳・レビューする。既存訳の識別ハッシュは維持する。
2. 新しいニュースUIの処理を確認し、原本を再配布しない生成手順を更新する。日時UIとの統合生成も再検証する。
3. 翻訳検査・配布物検査と、新原本での生成・導入・削除を検証する。
4. 実機でFOV・HDR・コントローラー設定、追加アイテム名、ニュース、セーブ日時、日本語フォントを確認する。
5. 実機確認後に対応版を追加し、公開候補を提示する。通しプレイとユーザーの最終承認までは公開準備完了としない。
