"""ローカル原文から公開用の識別情報だけを生成する。"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jp_patch.catalog import compare, metadata, read_json
from jp_patch.locres import Entry, loads
from jp_patch.tools import ROOT
from jp_patch.regions import ENGINE, scope_keys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region', choices=('game','engine'), default='game')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    if args.region == 'game':
        entries = [Entry(**row) for row in read_json(ROOT/'.local/source-en.json')]
    else:
        wanted = scope_keys(read_json(ROOT/ENGINE.scope))
        entries = [e for e in loads((ROOT/'.local/extracted/Engine/Content/Localization/Engine/en/Engine.locres').read_bytes()) if e.identity in wanted]
        if {e.identity for e in entries} != wanted:
            raise ValueError('Engineの対象キーが原本から欠落しています。対象範囲を再調査してください')
    if args.output is None:
        args.output = ROOT/f'catalog/{args.region}.json'
    inventory = read_json(ROOT/'.local/inventory.json')
    catalog = dict(schema_version=1, game_version=inventory['game_version'], entries=[metadata(e) for e in sorted(entries, key=lambda e:e.identity)])
    if args.compare:
        diff = compare(read_json(args.compare), catalog)
        (ROOT/f'.local/catalog-diff-{args.region}.json').write_text(json.dumps(diff, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print('更新差分: ' + ', '.join(f'{k}={len(v)}' for k,v in diff.items()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'原文を含まない識別情報を生成: {len(entries)}件')


if __name__ == '__main__':
    main()
