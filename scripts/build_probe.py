"""製品版の表示確認用ZIPを、通常のビルドと導入管理で生成する。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jp_patch.build import build

if __name__ == '__main__':
    output, report = build(preview=True)
    print('表示確認用ZIP: ' + output.name)
    print(report)
