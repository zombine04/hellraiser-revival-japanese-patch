"""Windows配布用生成ツールと依存ライセンスを原本なしでビルドする。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jp_patch.runtime import source_fingerprint
from jp_patch.tools import ROOT

def build(cargo='cargo'):
    output=ROOT/'.local/runtime';output.mkdir(parents=True,exist_ok=True)
    env=os.environ | {'CARGO_TARGET_DIR':str(ROOT/'.local/runtime-target'), 'CARGO_INCREMENTAL':'0'}
    env.pop('RUSTFLAGS',None)
    env['CARGO_ENCODED_RUSTFLAGS']='\x1f'.join(['--remap-path-prefix='+str(ROOT)+'=/source','-C','link-arg=/Brepro'])
    def run(*args):
        result=subprocess.run([cargo,*args],cwd=ROOT/'runtime',env=env,capture_output=True)
        with (output/'build.log').open('ab') as log:log.write(result.stdout+result.stderr)
        if result.returncode:raise ValueError('生成ツールのビルドに失敗しました。.local/runtime/build.logを確認してください')
        return result.stdout
    version=run('--version').decode().strip()
    if not version.startswith('cargo 1.90.0 '):raise ValueError('Rust 1.90.0を使用してください')
    run('test','--locked')
    run('build','--release','--locked','--target','x86_64-pc-windows-msvc')
    binary=ROOT/'.local/runtime-target/x86_64-pc-windows-msvc/release/generate-patch.exe'
    shutil.copyfile(binary,output/'GeneratePatch.exe')
    metadata=json.loads(run('metadata','--locked','--format-version','1','--filter-platform','x86_64-pc-windows-msvc'))
    sections=[]
    for package in sorted(metadata['packages'],key=lambda p:(p['name'],p['version'])):
        if package['source'] is None:continue
        folder=Path(package['manifest_path']).parent
        candidates=sorted(p for p in folder.rglob('*') if p.is_file() and p.name.upper().startswith(('LICENSE','LICENCE','COPYING')) and not any(x in p.parts for x in ('tests','testdata','.git')))
        if not candidates:
            notice=ROOT/'runtime/licenses'/f"{package['name']}-{package['version']}.txt"
            if not notice.is_file():raise ValueError('依存ライセンスが見つかりません: '+package['name'])
            candidates=[notice]
        text='\n\n'.join(p.read_text(encoding='utf-8-sig').replace('\r\n','\n') for p in candidates)
        sections.append(package['name']+' '+package['version']+' ('+str(package['license'])+')\n'+text)
    (output/'RUNTIME_LICENSES.txt').write_text('\n\n'.join(sections)+'\n',encoding='utf-8',newline='\n')
    files={name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in ('GeneratePatch.exe','RUNTIME_LICENSES.txt')}
    (output/'runtime-build.json').write_text(json.dumps(dict(schema_version=1,source_fingerprint=source_fingerprint(),files=files),sort_keys=True)+'\n',encoding='utf-8')
    print('生成ツールと依存ライセンスを.local/runtimeへ保存しました')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cargo',default='cargo');args=parser.parse_args()
    try:build(args.cargo)
    except (OSError,ValueError) as e:print(str(e),file=sys.stderr);sys.exit(1)
