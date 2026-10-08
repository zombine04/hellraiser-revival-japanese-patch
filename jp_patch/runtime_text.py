"""表示側が要求する書式へ変換する。訳文ファイルはLFで管理する。"""

SHADER_KEY = ('ST_UI_Unique', 'shader_precompilation')
SHADER_SOURCE_HASH = 78950914


def runtime_text(row):
    text = row['ja']
    if (row['namespace'], row['key']) == SHADER_KEY:
        if row['source_hash'] != SHADER_SOURCE_HASH:
            raise ValueError('シェーダー画面の原文が変更されています。改行処理を再確認してください')
        # W_WelcomeScreen_Description.ParseTextはCRLFで分割してから
        # 各行に装飾を付ける。LFだけだと改行を含む1つの装飾になる。
        text = text.replace('\n', '\r\n')
    return text
