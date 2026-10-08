"""ゲームの原文をローカル専用ディレクトリへ抽出する。"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jp_patch.locres import loads
from jp_patch.tools import ROOT, repak, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', type=Path, required=True)
    args = parser.parse_args()
    version = (args.game_dir / 'Version.txt').read_text('utf-8-sig').strip()
    if '_HellraiserGame_Shipping_' not in version or 'HellraiserGameDemo' in version:
        raise ValueError('製品版のゲームフォルダーを指定してください')
    original = args.game_dir / 'Hellraiser/Content/Paks/pakchunk0-Windows.pak'
    if not original.is_file():
        raise ValueError('指定先に対象ゲームのPakがありません')
    executable = repak()
    lock = json.loads((ROOT / 'tools.lock.json').read_text('utf-8'))['oodle_windows']
    oodle = executable.with_name(lock['filename'])
    if sys.platform == 'win32' and (not oodle.is_file() or sha256(oodle) != lock['sha256']):
        raise ValueError('検証済みのローカル展開用ライブラリが必要です')
    private = ROOT / '.local'
    private.mkdir(parents=True, exist_ok=True)
    output = private / 'extracted'
    # 展開ログはローカルに保存し、個人パスや原文をCI・公開ログへ流さない。
    with (private / 'extraction.log').open('wb') as log:
        result = subprocess.run([str(executable), 'unpack', str(original), '--output', str(output),
            '--include', 'Hellraiser/Content/Localization/', '--include', 'Hellraiser/Config/',
            '--include', 'Engine/Content/Localization/', '--force', '--quiet'], stdout=log, stderr=log)
    if result.returncode:
        raise ValueError('展開に失敗しました。.local/extraction.logをローカルで確認してください')
    entries = {}
    for culture in ['en', 'zh-Hans']:
        path = output / f'Hellraiser/Content/Localization/Game/{culture}/Game.locres'
        entries[culture] = loads(path.read_bytes())
        (private / f'source-{culture}.json').write_text(json.dumps([asdict(e) for e in entries[culture]], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    english = {e.identity: e for e in entries['en']}
    chinese = {e.identity: e for e in entries['zh-Hans']}
    summary = {
        'game_version': version,
        'original_pak_sha256': sha256(original),
        'counts': {k: len(v) for k, v in entries.items()},
        'english_only': len(english.keys() - chinese.keys()),
        'chinese_only': len(chinese.keys() - english.keys()),
        'source_hash_mismatch': sum(english[k].source_hash != chinese[k].source_hash for k in english.keys() & chinese.keys()),
    }
    (private / 'inventory.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        print(type(error).__name__ + ': 抽出に失敗しました。ゲームの配置とツールを確認してください。', file=sys.stderr)
        sys.exit(1)
