"""旧カタログと訳文を照合し、移行候補を新しいローカルディレクトリへ出力する。"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jp_patch.catalog import IDENTITY, read_json
from jp_patch.migration import migrate
from jp_patch.regions import GAME, REGIONS
from jp_patch.tools import ROOT


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / '.local').resolve()) or output.exists():
        raise ValueError('出力先には.local内の新しいディレクトリを指定してください')
    reports = {}
    pending = {}
    for region in REGIONS:
        old_catalog = read_json(args.baseline / region.catalog)
        new_catalog = read_json(ROOT / region.catalog)
        rows, owners = [], {}
        for path in sorted((args.baseline / region.translations).glob('*.json')):
            entries = read_json(path)['entries']
            rows.extend(entries)
            owners.update({tuple(row[k] for k in IDENTITY): path.name for row in entries})
        migrated, reports[region.name] = migrate(old_catalog, new_catalog, rows)
        files = {path.name: [] for path in (args.baseline / region.translations).glob('*.json')}
        for row in migrated:
            filename = owners.get(tuple(row[k] for k in IDENTITY), 'ui.json' if region == GAME else 'input.json')
            files.setdefault(filename, []).append(row)
        for filename, entries in files.items():
            pending[Path(region.translations) / filename] = dict(schema_version=1, entries=entries)
        pending[Path(region.exclusions)] = []
        if region.probe:
            # 旧試作訳は引き継がず、製品版の正式訳をpreviewにも使用する。
            pending[Path(region.probe)] = dict(schema_version=1, entries=[])
    for relative, data in pending.items():
        write(output / relative, data)
    write(output / 'migration-report.json', reports)
    print(json.dumps({region: report['counts'] for region, report in reports.items()}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError):
        print('翻訳移行に失敗しました。入力カタログ・訳文と出力先を確認してください。', file=sys.stderr)
        sys.exit(1)
