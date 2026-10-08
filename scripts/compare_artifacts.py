"""Windows・Linux・リリース用の独立ビルドが同じ配布物になることを検査する。"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jp_patch.tools import ROOT, sha256


def compare(folders, version):
    if len(folders) < 2:
        raise ValueError('照合には2つ以上の成果物が必要です')
    name = f'Hellraiser_Revival_Japanese_v{version}.zip'
    digests = set()
    for folder in folders:
        package = folder/name
        checksum = package.with_suffix('.sha256')
        if not package.is_file() or not checksum.is_file():
            raise ValueError('比較する配布物が不足しています')
        digest = sha256(package)
        if checksum.read_text('ascii') != f'{digest}  {name}\n':
            raise ValueError('配布物のSHA-256一覧が一致しません')
        digests.add(digest)
    if len(digests) != 1:
        raise ValueError('実行環境間で配布物が一致しません')
    return digests.pop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folders', type=Path, nargs='+')
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    print('環境間の成果物一致: '+compare(args.folders, (ROOT/'VERSION').read_text('ascii').strip() + ('-preview' if args.preview else '')))
