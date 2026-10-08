"""公開データから配布物を生成する。ゲーム本体へのアクセスは禁止する。"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

from .catalog import read_json
from .fonts import ASSETS, write_assets
from .locres import Entry, dumps, loads
from .runtime_text import runtime_text
from .tools import ROOT, repak, retoc, sha256
from .translation_set import load_regions
from .regions import GAME, REGIONS, coverage

RELATIVE = GAME.locres
STEM = 'Hellraiser_Revival_Japanese_P'


def build_fonts(work, stem=STEM):
    staging = work/'fonts'
    write_assets(staging)
    iostore = work/'iostore'/f'{stem}.utoc'
    iostore.parent.mkdir(parents=True)
    subprocess.run([str(retoc()),'to-zen',str(staging),str(iostore),'--version','UE5_6','--no-parallel'],check=True,capture_output=True)
    listing = subprocess.run([str(retoc()),'list',str(iostore),'--path'],check=True,capture_output=True,text=True).stdout.splitlines()
    expected = {f'../../../Hellraiser/Content/UI/Font/{asset}.uasset' for asset in ASSETS}
    paths = {line.split()[-1] for line in listing if 'ExportBundleData' in line}
    if paths != expected or len(listing) != 3 or sum('ContainerHeader' in line for line in listing) != 1:
        raise ValueError('IoStoreに対象外の資産が含まれています')
    return {file.name:file.read_bytes() for file in (iostore,iostore.with_suffix('.ucas'))}


def deterministic_zip(files, output):
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, content in sorted(files.items()):
            if Path(name).name != name or '/' in name or '\\' in name:
                raise ValueError('ZIPの収録パスが不正です')
            info = zipfile.ZipInfo(name, date_time=(2026,1,1,0,0,0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)


def build(*, preview=False):
    version = (ROOT/'VERSION').read_text('ascii').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('VERSIONの形式が不正です')
    regions = load_regions(ROOT, preview=preview, release=not preview)
    if preview:
        version += '-preview'
    catalog = regions[GAME.name]['catalog']
    report = coverage({name:data['report'] for name,data in regions.items()})
    payloads = {}
    for region in REGIONS:
        entries = [Entry(**{k:row[k] for k in ('namespace','namespace_hash','key','key_hash','source_hash')}, text=runtime_text(row))
                   for row in regions[region.name]['rows'] if row['status'] != 'untranslated']
        if not entries:
            raise ValueError('ビルドする訳文がない領域があります')
        payload = dumps(entries)
        if loads(payload) != sorted(entries, key=lambda e:e.identity):
            raise ValueError('LocRes読み戻し検査に失敗しました')
        payloads[region.locres] = payload
    destination = ROOT/'dist'
    destination.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='jp-build-') as temp:
        work = Path(temp)
        staging = work/'staging'
        for relative, payload in sorted(payloads.items()):
            locres = staging/relative
            locres.parent.mkdir(parents=True, exist_ok=True)
            locres.write_bytes(payload)
        pak = work/f'{STEM}.pak'
        # repak 0.2.3の並列packは読込完了順に書くため、複数LocResの順序を固定する。
        subprocess.run([str(repak()),'pack',str(staging),str(pak),'--version','V11','--quiet'],
                       check=True,capture_output=True,env=os.environ | {'RAYON_NUM_THREADS':'1'})
        listing = subprocess.run([str(repak()),'list',str(pak)],check=True,capture_output=True,text=True).stdout.splitlines()
        if sorted(listing) != sorted(payloads):
            raise ValueError('Pakに対象外の資産が含まれています')
        unpacked = work/'unpacked'
        subprocess.run([str(repak()),'unpack',str(pak),'-o',str(unpacked)],check=True,capture_output=True)
        if any((unpacked/relative).read_bytes() != payload for relative,payload in payloads.items()):
            raise ValueError('Pak読み戻し検査に失敗しました')
        files = {pak.name:pak.read_bytes(), **build_fonts(work)}
    manifest = dict(schema_version=1, product='hellraiser-revival-japanese', patch_version=version, preview=preview, game_version=catalog['game_version'], coverage=report,
                    files=[dict(name=name,sha256=hashlib.sha256(content).hexdigest()) for name,content in sorted(files.items())], supported_builds=read_json(ROOT/'catalog/supported-builds.json'))
    files['manifest.json'] = (json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    for name in ('Patch.ps1','Install.cmd','Uninstall.cmd'):
        raw = (ROOT/'distribution'/name).read_text('utf-8-sig').replace('\r\n','\n')
        files[name] = raw.replace('\n','\r\n').encode('utf-8-sig' if name.endswith('.ps1') else 'ascii')
    for name in ('README.md','THIRD_PARTY_NOTICES.md','LICENSE'):
        files[name] = (ROOT/name).read_text('utf-8-sig').replace('\r\n','\n').encode()
    if preview:
        files['README.md'] = (f'# 表示確認用の試作版\n\n開発中の日本語訳{report["translated"]-report["untranslated"]:,}件を含みます。正式公開前の表示確認用です。\n\n'.encode() + files['README.md'])
    files['SHA256SUMS.txt'] = ''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name,data in sorted(files.items())).encode('ascii')
    output = destination/f'Hellraiser_Revival_Japanese_v{version}.zip'
    deterministic_zip(files, output)
    output.with_suffix('.sha256').write_text(f'{sha256(output)}  {output.name}\n',encoding='ascii')
    return output, report
