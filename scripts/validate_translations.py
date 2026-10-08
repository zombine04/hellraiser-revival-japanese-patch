from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jp_patch.catalog import read_json, validate
from jp_patch.tools import ROOT
from jp_patch.translation_set import load_regions
from jp_patch.regions import coverage


def main():
    catalog=read_json(ROOT/'catalog/game.json')
    try:
        probe=validate(catalog,read_json(ROOT/'translations/probe.json')['entries'])
        formal=coverage({name:data['report'] for name,data in load_regions(ROOT).items()})
    except (ValueError, KeyError, TypeError):
        print('翻訳データの構造・書式検査に失敗しました。原文は表示しません。',file=sys.stderr)
        return 1
    print('初期試作の補助訳: '+str(probe))
    print('翻訳データ: '+str(formal))
    return 0


if __name__=='__main__':
    sys.exit(main())
