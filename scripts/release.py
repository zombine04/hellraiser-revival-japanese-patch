import os
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jp_patch.release import GitHub, publish
from jp_patch.tools import ROOT, sha256
from check_package import check


def main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_REF')!='refs/heads/main':
        raise ValueError('mainのGitHub Actionsからのみ実行できます')
    version=(ROOT/'VERSION').read_text('ascii').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):
        raise ValueError('VERSIONが不正です')
    package=ROOT/'dist'/f'Hellraiser_Revival_Japanese_v{version}.zip'
    checksum=package.with_suffix('.sha256')
    check(package,release=True)
    if checksum.read_text('ascii')!=f'{sha256(package)}  {package.name}\n':
        raise ValueError('ZIPのチェックサムが一致しません')
    print(publish(GitHub(os.environ['GITHUB_REPOSITORY']),'v'+version,os.environ['GITHUB_SHA'],[package,checksum]))


if __name__=='__main__':
    try: main()
    except Exception as error:
        print(str(error) if isinstance(error,(ValueError,RuntimeError)) else 'リリース処理が失敗しました',file=sys.stderr)
        sys.exit(1)
