"""自作の小さなコンテナを使う。実ゲームにはアクセスしない。"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
NAMES = [f'Hellraiser_Revival_Japanese_P.{ext}' for ext in ('pak', 'utoc', 'ucas')]
ORIGINALS = ['global.utoc', 'global.ucas'] + [f'{stem}.{ext}' for stem in ('pakchunk0-Windows', 'pakchunk0optional-Windows') for ext in ('pak', 'utoc', 'ucas')]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(os.name == 'nt', 'Windows導入スクリプトの検証')
class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jp-installer-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        # 実ゲームの起動状態をテストから参照せず、子PowerShell内で固定する。
        self.runner = self.base / 'fixture-runner.ps1'
        self.runner.write_text("""param([string]$FixturePatch,[string]$Action,[string]$GameDir,
    [switch]$NonInteractive,[switch]$AllowUnsupported,[switch]$FixtureGameRunning)
function Get-Process {
    param($Name,$ErrorAction)
    if ($FixtureGameRunning) { [pscustomobject]@{ Id=1 } }
}
& $FixturePatch -Action $Action -GameDir $GameDir -NonInteractive:$NonInteractive -AllowUnsupported:$AllowUnsupported
exit $LASTEXITCODE
""", encoding='utf-8-sig')
        self.package = self.base / "配布 ZIP's folder"
        self.package.mkdir()
        self.game = self.base / "Steam library/steamapps/common/ゲーム 空白's folder"
        self.paks = self.game / 'Hellraiser/Content/Paks'
        self.paks.mkdir(parents=True)
        self.exe = self.game/'Hellraiser/Binaries/Win64/Hellraiser-Win64-Shipping.exe'
        self.exe.parent.mkdir(parents=True)
        self.exe.write_bytes(b'self-made-executable-marker')
        (self.game/'Version.txt').write_text('1.0.0_HellraiserGame_Shipping_Test\n', encoding='utf-8')
        for name in ORIGINALS:
            (self.paks / name).write_bytes(('自作の元データ:' + name).encode())
        for name in ('Patch.ps1', 'Install.cmd', 'Uninstall.cmd'):
            shutil.copyfile(ROOT / 'distribution' / name, self.package / name)
        for name in ('README.md', 'LICENSE'):
            (self.package / name).write_text('自作のテスト用説明', encoding='utf-8')
        self.manifest = dict(schema_version=1, product='hellraiser-revival-japanese', patch_version='1.0.0', files=[], supported_builds=[dict(version='1.0.0_HellraiserGame_Shipping_Test')])
        self.prepare('1.0.0')
        self.original_bytes = {n: (self.paks/n).read_bytes() for n in ORIGINALS}

    def prepare(self, version):
        self.manifest['patch_version'] = version
        for name in NAMES:
            (self.package/name).write_bytes(('自作パッチ:' + version + name).encode())
        self.manifest['files'] = [dict(name=n, sha256=digest(self.package/n)) for n in NAMES]
        self.checksums()

    def checksums(self):
        (self.package/'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        names = NAMES + ['Patch.ps1', 'Install.cmd', 'Uninstall.cmd', 'README.md', 'manifest.json', 'LICENSE']
        if self.manifest['schema_version']==2:names+=['GeneratePatch.exe','RUNTIME_LICENSES.txt','ui-patch.json']
        (self.package/'SHA256SUMS.txt').write_text(''.join(f'{digest(self.package/n)}  {n}\n' for n in sorted(names)), encoding='ascii')

    def run_patch(self, action='Install', success=True, *, non_interactive=True, allow_unsupported=False, input=None, running=False):
        command = ['powershell.exe','-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',str(self.runner),'-FixturePatch',str(self.package/'Patch.ps1'),'-Action',action,'-GameDir',str(self.game)]
        if non_interactive:
            command.append('-NonInteractive')
        if allow_unsupported:
            command.append('-AllowUnsupported')
        if running:
            command.append('-FixtureGameRunning')
        result = subprocess.run(command, input=input, capture_output=True, timeout=30)
        self.assertEqual(result.returncode == 0, success, result.stdout.decode('utf-8', errors='replace') + result.stderr.decode('utf-8', errors='replace'))
        self.assertFalse((self.paks/'.hellraiser-revival-japanese-patch.lock').exists())
        for n, data in self.original_bytes.items():
            self.assertEqual((self.paks/n).read_bytes(), data)

    def enable_generation(self):
        helper=ROOT/'.local/runtime/GeneratePatch.exe'
        self.assertTrue(helper.is_file(),'先にscripts/build_runtime.pyを実行してください')
        shutil.copyfile(helper,self.package/'GeneratePatch.exe')
        (self.package/'RUNTIME_LICENSES.txt').write_text('自作試験の説明',encoding='utf-8')
        raw=(self.paks/'pakchunk0-Windows.ucas').read_bytes()
        block=dict(offset=0,compressed_size=len(raw),size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),decoded_sha256=hashlib.sha256(raw).hexdigest(),compression='none')
        outputs=[];self.generated={NAMES[0]:(self.package/NAMES[0]).read_bytes()}
        for n in NAMES[1:]:
            literal=('生成結果:'+self.manifest['patch_version']+n).encode()
            expected=literal+raw
            self.generated[n]=expected
            outputs.append(dict(name=n,size=len(expected),sha256=hashlib.sha256(expected).hexdigest(),ops=[dict(data=literal.hex()),dict(copy=[1,0,len(raw)])]))
        self.recipe=dict(schema_version=1,toc_sha256=digest(self.paks/'pakchunk0-Windows.utoc'),seed_sha256=digest(self.package/NAMES[2]),blocks=[block]*3,outputs=outputs)
        (self.package/'ui-patch.json').write_text(json.dumps(self.recipe),encoding='utf-8')
        self.manifest['schema_version']=2
        self.manifest['generated_files']=[dict(name=n,sha256=hashlib.sha256(data).hexdigest()) for n,data in self.generated.items()]
        self.manifest['legacy_probe_files']=[]
        self.checksums()

    def test_generated_install_update_and_remove_without_sources(self):
        self.run_patch() # v1の管理情報から更新
        self.prepare('1.1.0');self.enable_generation();self.run_patch()
        self.assertEqual({n:(self.paks/n).read_bytes() for n in NAMES},self.generated)
        self.run_patch() # 再導入
        self.prepare('1.1.1');self.enable_generation();self.run_patch()
        self.assertEqual({n:(self.paks/n).read_bytes() for n in NAMES},self.generated)
        (self.game/'Version.txt').unlink()
        for name in ('GeneratePatch.exe','ui-patch.json','manifest.json'):(self.package/name).unlink()
        (self.paks/'pakchunk0-Windows.utoc').write_bytes(b'game updated')
        self.original_bytes['pakchunk0-Windows.utoc']=b'game updated'
        self.run_patch('Uninstall')
        self.assertFalse(any((self.paks/n).exists() for n in NAMES))

    def test_generated_wrong_source_or_output_preserves_old_install(self):
        self.run_patch();before={p.name:p.read_bytes() for p in self.paks.iterdir() if p.is_file()}
        self.enable_generation()
        for field in ('toc_sha256','decoded_sha256','output'):
            recipe=json.loads((self.package/'ui-patch.json').read_text())
            bad=json.loads(json.dumps(recipe))
            if field=='toc_sha256':bad[field]='0'*64
            elif field=='decoded_sha256':bad['blocks'][0][field]='0'*64
            else:bad['outputs'][0]['sha256']='0'*64
            (self.package/'ui-patch.json').write_text(json.dumps(bad));self.checksums()
            self.run_patch(success=False)
            self.assertEqual(before,{p.name:p.read_bytes() for p in self.paks.iterdir() if p.is_file()})
            (self.package/'ui-patch.json').write_text(json.dumps(recipe))

    def test_generation_rejects_unsupported_even_when_forced(self):
        self.enable_generation()
        (self.game/'Version.txt').write_text('1.0.2_HellraiserGame_Shipping_Test')
        self.run_patch(success=False,allow_unsupported=True)
        self.assertFalse(any((self.paks/n).exists() for n in NAMES))

    def prepare_known_probe(self):
        self.probe={f'Hellraiser_Revival_EnglishProbe_P.{ext}':('自作試作'+ext).encode() for ext in ('pak','utoc','ucas')}
        for n,b in self.probe.items():(self.paks/n).write_bytes(b)
        self.manifest['legacy_probe_files']=[dict(name=n,sha256=hashlib.sha256(b).hexdigest()) for n,b in self.probe.items()]
        self.checksums()

    def test_known_probe_migration(self):
        self.enable_generation();self.prepare_known_probe();self.run_patch()
        self.assertFalse(any((self.paks/n).exists() for n in self.probe))
        self.assertEqual({n:(self.paks/n).read_bytes() for n in NAMES},self.generated)
        self.run_patch('Uninstall')

    def test_unknown_or_partial_probe_is_preserved(self):
        self.enable_generation();self.prepare_known_probe()
        name=next(iter(self.probe));(self.paks/name).write_bytes(b'unknown')
        self.run_patch(success=False)
        self.assertEqual((self.paks/name).read_bytes(),b'unknown')
        (self.paks/name).unlink();self.run_patch(success=False)
        self.assertFalse(any((self.paks/n).exists() for n in NAMES))

    def test_migration_rolls_back_after_state_write_failure(self):
        self.run_patch();self.enable_generation();self.prepare_known_probe()
        before={p.name:p.read_bytes() for p in self.paks.iterdir() if p.is_file()}
        state=self.paks/'.hellraiser-revival-japanese-patch.json';state.chmod(0o444)
        try:self.run_patch(success=False)
        finally:state.chmod(0o666)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.paks.iterdir() if p.is_file()})

    def test_generation_bounds_and_changed_compressed_input(self):
        self.enable_generation();good=json.loads(json.dumps(self.recipe))
        variants=[]
        bad=json.loads(json.dumps(good));bad['blocks'][0]['sha256']='0'*64;variants.append(bad)
        bad=json.loads(json.dumps(good));bad['blocks'][0]['offset']=2**63;variants.append(bad)
        bad=json.loads(json.dumps(good));bad['outputs'][0]['ops']=[dict(copy=[1,0,2**40])];variants.append(bad)
        bad=json.loads(json.dumps(good));bad['outputs'][0]['name']='../unrelated.txt';variants.append(bad)
        for recipe in variants:
            (self.package/'ui-patch.json').write_text(json.dumps(recipe));self.checksums()
            self.run_patch(success=False)
            self.assertFalse(any((self.paks/n).exists() for n in NAMES))

    def test_running_game_prevents_install_and_uninstall(self):
        self.run_patch(success=False, running=True)
        self.assertFalse(any((self.paks/n).exists() for n in NAMES))
        self.run_patch()
        installed = {n: (self.paks/n).read_bytes() for n in NAMES}
        self.run_patch('Uninstall', success=False, running=True)
        self.assertEqual(installed, {n: (self.paks/n).read_bytes() for n in NAMES})

    def test_install_reinstall_update_remove(self):
        self.run_patch()
        self.run_patch()
        self.prepare('1.0.1')
        self.run_patch()
        for n in NAMES:
            self.assertEqual((self.paks/n).read_bytes(), (self.package/n).read_bytes())
        self.run_patch('Uninstall')
        self.run_patch('Uninstall')
        self.assertFalse(any((self.paks/n).exists() for n in NAMES))

    def test_unknown_file_is_preserved(self):
        target = self.paks/NAMES[0]
        target.write_bytes(b'other-mod')
        self.run_patch(success=False)
        self.assertEqual(target.read_bytes(), b'other-mod')

    def test_modified_patch_is_preserved(self):
        self.run_patch()
        target = self.paks/NAMES[1]
        target.write_bytes(b'modified')
        self.run_patch(success=False)
        self.run_patch('Uninstall', success=False)
        self.assertEqual(target.read_bytes(), b'modified')

    def test_package_corruption_is_rejected(self):
        (self.package/NAMES[0]).write_bytes(b'bad')
        self.run_patch(success=False)
        self.assertFalse((self.paks/NAMES[0]).exists())

    def test_unsupported_game_requires_explicit_noninteractive_permission(self):
        (self.game/'Version.txt').write_text('1.0.2_HellraiserGame_Shipping_Test', encoding='utf-8')
        self.run_patch(success=False)
        self.run_patch(allow_unsupported=True)

    def test_game_files_are_not_hashed(self):
        self.exe.write_bytes(b'updated-executable')
        (self.paks/ORIGINALS[0]).write_bytes(b'game-update')
        self.original_bytes[ORIGINALS[0]] = b'game-update'
        self.run_patch()

    def test_unsupported_game_can_be_confirmed_interactively(self):
        (self.game/'Version.txt').write_text('1.0.2_HellraiserGame_Shipping_Test', encoding='utf-8')
        self.run_patch(non_interactive=False, input=b'y\n')

    def test_unsupported_game_can_be_declined_interactively(self):
        (self.game/'Version.txt').write_text('1.0.2_HellraiserGame_Shipping_Test', encoding='utf-8')
        self.run_patch(success=False, non_interactive=False, input=b'n\n')

    def test_missing_version_requires_retail_manifest_and_warning_permission(self):
        (self.game/'Version.txt').unlink()
        self.run_patch(success=False)
        self.run_patch(success=False, allow_unsupported=True)
        (self.game.parent.parent/'appmanifest_1551980.acf').write_text(
            '"appid" "1551980" "installdir" "' + self.game.name + '"', encoding='utf-8')
        self.run_patch(success=False)
        self.run_patch(allow_unsupported=True)

    def test_probe_patch_conflict_is_rejected(self):
        for stem in ('Hellraiser_Japanese_P', 'Hellraiser_Japanese_Probe_P', 'Hellraiser_Japanese_Font_P', 'Hellraiser_Revival_Japanese_Probe_P'):
            with self.subTest(stem=stem):
                trial=self.paks/(stem+'.pak')
                trial.write_bytes(b'trial')
                self.run_patch(success=False)
                self.assertEqual(trial.read_bytes(),b'trial')
                trial.unlink()

    def test_demo_or_unidentifiable_game_is_rejected_even_when_forced(self):
        for version in ('1.0.0_HellraiserGameDemo_Shipping_Test', 'UnknownOtherGame'):
            with self.subTest(version=version):
                (self.game/'Version.txt').write_text(version, encoding='utf-8')
                self.run_patch(success=False, allow_unsupported=True)
                self.assertFalse(any((self.paks/name).exists() for name in NAMES))

    def test_demo_management_information_is_not_overwritten(self):
        state = self.paks/'.hellraiser-japanese-patch.json'
        state.write_text('{"product":"hellraiser-revival-demo-japanese"}', encoding='utf-8')
        before = state.read_bytes()
        self.run_patch(success=False)
        self.assertEqual(state.read_bytes(), before)

    def test_other_product_package_is_rejected(self):
        self.manifest['product'] = 'hellraiser-revival-demo-japanese'
        self.checksums()
        self.run_patch(success=False)

    def test_uninstall_does_not_require_current_version(self):
        self.run_patch()
        (self.game/'Version.txt').unlink()
        self.run_patch('Uninstall')

    def test_manifest_traversal_is_rejected(self):
        self.manifest['files'][0]['name'] = '../unrelated.txt'
        self.checksums()
        self.run_patch(success=False)

    def test_uninstall_after_game_update(self):
        self.run_patch()
        target = self.paks/ORIGINALS[0]
        target.write_bytes(b'game-update')
        self.original_bytes[ORIGINALS[0]] = b'game-update'
        self.run_patch('Uninstall')

    def test_missing_patch_fails_closed(self):
        self.run_patch()
        (self.paks/NAMES[1]).unlink()
        self.run_patch('Uninstall', success=False)
        self.assertTrue((self.paks/NAMES[0]).exists())

    def test_unrelated_mod_is_preserved(self):
        unrelated = self.paks/'OtherMod.pak'
        unrelated.write_bytes(b'unrelated')
        self.run_patch()
        self.run_patch('Uninstall')
        self.assertEqual(unrelated.read_bytes(), b'unrelated')

    def test_readonly_target_rolls_back(self):
        self.run_patch()
        target = self.paks/NAMES[1]
        old = {n:(self.paks/n).read_bytes() for n in NAMES}
        self.prepare('1.0.1')
        target.chmod(0o444)
        try:
            self.run_patch(success=False)
            for n, data in old.items():
                self.assertEqual((self.paks/n).read_bytes(), data)
        finally:
            target.chmod(0o666)


if __name__ == '__main__':
    unittest.main()
