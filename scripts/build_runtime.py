"""Windows配布用生成ツールと依存ライセンスを原本なしでビルドする。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import struct
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jp_patch.runtime import source_fingerprint
from jp_patch.tools import ROOT

def assert_standalone(data):
    pe=struct.unpack_from('<I',data,0x3c)[0]
    if data[pe:pe+4]!=b'PE\0\0':raise ValueError('Windows実行形式ではありません')
    count=struct.unpack_from('<H',data,pe+6)[0]
    optional=pe+24;size=struct.unpack_from('<H',data,pe+20)[0]
    if struct.unpack_from('<H',data,optional)[0]!=0x20b:raise ValueError('Windows x64実行形式ではありません')
    sections=[struct.unpack_from('<IIII',data,optional+size+i*40+8) for i in range(count)]
    def offset(rva):
        for virtual_size,virtual,raw_size,raw in sections:
            if virtual<=rva<virtual+max(virtual_size,raw_size):return raw+rva-virtual
        raise ValueError('PEの参照先が不正です')
    imports=offset(struct.unpack_from('<I',data,optional+120)[0]);names=[]
    while any(data[imports:imports+20]):
        name=offset(struct.unpack_from('<I',data,imports+12)[0]);end=data.index(b'\0',name)
        names.append(data[name:end].decode('ascii').lower());imports+=20
    allowed={'kernel32.dll','ntdll.dll','advapi32.dll','userenv.dll','ws2_32.dll','bcrypt.dll','bcryptprimitives.dll'}
    if any(n not in allowed and not n.startswith('api-ms-win-core-') for n in names):
        raise ValueError('生成ツールに追加DLLへの依存があります')

def build(cargo='cargo'):
    output=ROOT/'.local/runtime';output.mkdir(parents=True,exist_ok=True)
    env=os.environ | {'CARGO_TARGET_DIR':str(ROOT/'.local/runtime-target'), 'CARGO_INCREMENTAL':'0'}
    env.pop('RUSTFLAGS',None)
    cargo_home=Path(env.get('CARGO_HOME',Path.home()/'.cargo')).resolve()
    env['CARGO_ENCODED_RUSTFLAGS']='\x1f'.join(['--remap-path-prefix='+str(Path.home())+'=/user','--remap-path-prefix='+str(ROOT)+'=/source','--remap-path-prefix='+str(cargo_home)+'=/cargo','-C','link-arg=/Brepro','-C','target-feature=+crt-static'])
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
    assert_standalone(binary.read_bytes())
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
