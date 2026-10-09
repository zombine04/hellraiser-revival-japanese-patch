"""導入時の生成処理と、原本を含まない変更手順の配布検査。"""
import hashlib
import json
from .tools import ROOT

NAMES=('GeneratePatch.exe','RUNTIME_LICENSES.txt')
def source_fingerprint():
    paths=[ROOT/'runtime/Cargo.toml',ROOT/'runtime/Cargo.lock',ROOT/'runtime/rust-toolchain.toml',ROOT/'scripts/build_runtime.py']
    paths+=sorted((ROOT/'runtime/src').glob('*.rs'))
    paths+=sorted((ROOT/'runtime/licenses').glob('*.txt'))
    h=hashlib.sha256()
    for p in sorted(paths):
        h.update(p.relative_to(ROOT).as_posix().encode());h.update(b'\0');h.update(p.read_bytes().replace(b'\r\n',b'\n'));h.update(b'\0')
    return h.hexdigest()
def runtime_files():
    folder=ROOT/'.local/runtime'
    try:stamp=json.loads((folder/'runtime-build.json').read_text(encoding='utf-8'))
    except (OSError,ValueError) as e:raise ValueError('先にscripts/build_runtime.pyで生成ツールをビルドしてください') from e
    if stamp.get('schema_version')!=1 or stamp.get('source_fingerprint')!=source_fingerprint():raise ValueError('生成ツールのソースが変わっています。再ビルドしてください')
    result={name:(folder/name).read_bytes() for name in NAMES}
    if stamp.get('files')!={name:hashlib.sha256(data).hexdigest() for name,data in result.items()}:raise ValueError('生成ツールのハッシュが一致しません')
    if not result['GeneratePatch.exe'].startswith(b'MZ'):raise ValueError('Windows用生成ツールではありません')
    return result

def read_recipe():
    raw=(ROOT/'distribution/ui-patch.json').read_bytes();recipe=json.loads(raw)
    if set(recipe)!={'schema_version','toc_sha256','seed_sha256','blocks','outputs'} or recipe['schema_version']!=1 or len(recipe['blocks'])!=3:raise ValueError('変更手順の形式が不正です')
    hashes=[recipe['toc_sha256'],recipe['seed_sha256']]
    for block in recipe['blocks']:
        if set(block)!={'offset','compressed_size','size','sha256','decoded_sha256','compression'} or block['compression']!='oodle':raise ValueError('対象範囲の情報が不正です')
        if not 0<block['compressed_size']<=1_000_000 or not 0<block['size']<=1_000_000 or block['offset']<0:raise ValueError('対象範囲が不正です')
        hashes.extend([block['sha256'],block['decoded_sha256']])
    if [o['name'] for o in recipe['outputs']]!=['Hellraiser_Revival_Japanese_P.utoc','Hellraiser_Revival_Japanese_P.ucas']:raise ValueError('生成先が不正です')
    literal_bytes=0
    for output in recipe['outputs']:
        if not 0<output['size']<=2_000_000:raise ValueError('生成サイズが不正です')
        hashes.append(output['sha256']);length=0
        for op in output['ops']:
            if set(op)=={'copy'}:
                source,offset,count=op['copy']
                if source not in range(4) or offset<0 or count<=0:raise ValueError('コピー範囲が不正です')
                if source and offset+count>recipe['blocks'][source-1]['size']:raise ValueError('コピー範囲が不正です')
                length+=count
            elif set(op)=={'data'}:
                data=bytes.fromhex(op['data']);literal_bytes+=len(data);length+=len(data)
            else:raise ValueError('変更命令が不正です')
        if length!=output['size']:raise ValueError('生成サイズが一致しません')
    if literal_bytes>4096:raise ValueError('追加データが上限を超えています。原資産の混入を確認してください')
    if any(len(h)!=64 or any(c not in '0123456789abcdef' for c in h) for h in hashes):raise ValueError('ハッシュの形式が不正です')
    return raw,recipe
