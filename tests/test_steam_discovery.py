"""自作Steamマニフェストで製品版とデモ版の取り違えを検証する。"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = "Clive Barker's Hellraiser - Revival"
GAME = 'steamapps/common/' + FOLDER


@unittest.skipUnless(os.name == 'nt', 'WindowsのSteamパス検出')
class SteamDiscoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='jp-discovery-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.steam = self.root / "Steam 日本語's folder"
        self.create_game(self.steam)
        self.runner = self.root / 'discovery.ps1'
        self.runner.write_text('''param([string]$Patch,[string]$InputFile)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($Patch,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw '検出スクリプトの構文エラー' }
foreach ($name in @('Get-SteamRetailCandidate','Get-SteamGameCandidates')) {
    $function=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$false)
    Invoke-Expression $function.Extent.Text
}
$roots=Get-Content -LiteralPath $InputFile -Raw -Encoding UTF8 | ConvertFrom-Json
ConvertTo-Json -InputObject @(Get-SteamGameCandidates $roots)
''', encoding='utf-8-sig')

    def create_game(self, library, folder=FOLDER, appid='1551980'):
        (library / 'steamapps/common' / folder / 'Hellraiser/Content/Paks').mkdir(parents=True)
        (library / 'steamapps' / f'appmanifest_{appid}.acf').write_text(
            f'"AppState"\n{{\n"appid" "{appid}"\n"installdir" "{folder}"\n}}', encoding='utf-8')

    def discover(self, roots=None, libraries=None):
        roots = roots if roots is not None else [self.steam]
        libraries = libraries if libraries is not None else [self.steam]
        vdf = '"libraryfolders"\n{\n' + ''.join('"path" "' + str(p).replace('\\', '\\\\') + '"\n' for p in libraries) + '}\n'
        (self.steam / 'steamapps/libraryfolders.vdf').write_text(vdf, encoding='utf-8')
        input_file = self.root / 'roots.json'
        input_file.write_text(json.dumps([str(p) for p in roots]), encoding='utf-8')
        result = subprocess.run(['powershell.exe', '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                 '-File', str(self.runner), '-Patch', str(ROOT / 'distribution/Patch.ps1'),
                                 '-InputFile', str(input_file)], capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
        return json.loads(result.stdout.decode('utf-8-sig'))

    def test_duplicate_paths_are_normalized(self):
        variants = [str(self.steam), str(self.steam).upper().replace('\\', '/'), str(self.steam) + '\\.\\']
        found = self.discover(variants, variants)
        self.assertEqual(len(found), 1)
        self.assertTrue(Path(found[0]).samefile(self.steam / GAME))

    def test_separate_installations_remain_separate(self):
        second = self.root / '別のライブラリ'
        self.create_game(second, folder='別名の製品版')
        found = self.discover(libraries=[self.steam, second])
        expected = [self.steam / GAME, second / 'steamapps/common/別名の製品版']
        self.assertEqual({Path(p).resolve() for p in found}, {p.resolve() for p in expected})

    def test_demo_is_never_a_candidate(self):
        self.create_game(self.steam, folder="Clive Barker's Hellraiser Revival Demo", appid='5184670')
        self.assertEqual(len(self.discover()), 1)
        (self.steam / 'steamapps/appmanifest_1551980.acf').unlink()
        self.assertEqual(self.discover(), [])

    def test_missing_library_does_not_create_candidate(self):
        self.assertEqual(len(self.discover(libraries=[self.steam, self.root / 'ない場所'])), 1)

    def test_unsafe_ambiguous_or_wrong_manifest_is_rejected(self):
        manifest = self.steam / 'steamapps/appmanifest_1551980.acf'
        for body in ['"appid" "5184670" "installdir" "' + FOLDER + '"',
                     '"appid" "1551980" "installdir" "../escape"',
                     '"appid" "1551980" "installdir" "C:\\elsewhere"',
                     '"appid" "1551980" "installdir" ""',
                     '"appid" "1551980" "installdir" "a" "installdir" "b"']:
            with self.subTest(body=body):
                manifest.write_text(body, encoding='utf-8')
                self.assertEqual(self.discover(), [])
