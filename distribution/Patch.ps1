# Windows PowerShell 5.1 / PowerShell 7
[CmdletBinding()]
param([ValidateSet('Install','Uninstall')][string]$Action='Install', [string]$GameDir, [switch]$NonInteractive, [switch]$AllowUnsupported)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$product = 'hellraiser-revival-japanese'
$managedNames = @('Hellraiser_Revival_Japanese_P.pak','Hellraiser_Revival_Japanese_P.utoc','Hellraiser_Revival_Japanese_P.ucas')
$stateName = '.hellraiser-revival-japanese-patch.json'
$utf8 = New-Object System.Text.UTF8Encoding($false)
function Fail([string]$Message) { throw [InvalidOperationException]::new($Message) }
function Read-Json([string]$Path) {
    try { return [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8) | ConvertFrom-Json }
    catch { Fail '必要なJSONファイルを読み込めません。ZIPを再展開してください。' }
}
function Hash([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $hasher.Dispose() }
}
function Assert-NoLink([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if ((Test-Path -LiteralPath $current) -and ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            Fail 'リンクやジャンクションを含む場所には適用できません。実体のパスを指定してください。'
        }
        $parent = [IO.Directory]::GetParent($current)
        if ($null -eq $parent) { break }
        $current = $parent.FullName
    }
}
function Assert-GameStopped {
    if (@(Get-Process -Name 'Hellraiser','Hellraiser-Win64-Shipping' -ErrorAction SilentlyContinue).Count) { Fail 'ゲームを終了してから実行してください。' }
}
function Get-SteamRetailCandidate([string]$Library) {
    $manifestPath = Join-Path $Library 'steamapps\appmanifest_1551980.acf'
    if (!(Test-Path -LiteralPath $manifestPath -PathType Leaf)) { return }
    try { $manifestText = [IO.File]::ReadAllText($manifestPath) }
    catch { return }
    $ids = [regex]::Matches($manifestText, '"appid"\s+"([^"\r\n]*)"')
    $folders = [regex]::Matches($manifestText, '"installdir"\s+"([^"\r\n]*)"')
    if ($ids.Count -ne 1 -or $ids[0].Groups[1].Value -cne '1551980' -or $folders.Count -ne 1) { return }
    $folder = $folders[0].Groups[1].Value
    if ([string]::IsNullOrWhiteSpace($folder) -or $folder -in @('.','..') -or $folder.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0) { return }
    $candidate = [IO.Path]::GetFullPath((Join-Path (Join-Path $Library 'steamapps\common') $folder)).Replace('/','\').TrimEnd('\')
    if (Test-Path -LiteralPath (Join-Path $candidate 'Hellraiser\Content\Paks') -PathType Container) { return $candidate }
}
function Assert-RetailGame([string]$Directory, [string]$Version) {
    if ($Version -match 'HellraiserGameDemo') { Fail 'デモ版には製品版用パッチを適用できません。' }
    if ($Version -cmatch '^[0-9][A-Za-z0-9._-]*_HellraiserGame_Shipping_[A-Za-z0-9._-]+$') { return }
    # Version.txtが欠けた場合も、Steamの製品版AppIDと導入先が一致したときだけ判定する。
    if ([string]::IsNullOrWhiteSpace($Version)) {
        $common = [IO.Directory]::GetParent($Directory)
        if ($null -ne $common -and $common.Name -ieq 'common' -and $null -ne $common.Parent -and $common.Parent.Name -ieq 'steamapps') {
            $library = $common.Parent.Parent
            if ($null -ne $library) {
                $candidate = Get-SteamRetailCandidate $library.FullName
                if ($candidate -and [string]::Equals($candidate, $Directory.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) { return }
            }
        }
    }
    Fail '製品版のインストール先と確認できません。Steamの製品版フォルダーを指定してください。'
}
function Get-SteamGameCandidates([string[]]$SteamRoots) {
    $libraries = @($SteamRoots)
    foreach ($steamRoot in $SteamRoots) {
        $vdf = Join-Path $steamRoot 'steamapps\libraryfolders.vdf'
        if (Test-Path -LiteralPath $vdf -PathType Leaf) {
            foreach ($match in [regex]::Matches([IO.File]::ReadAllText($vdf), '"path"\s+"((?:\\.|[^"\\])*)"')) {
                $libraries += $match.Groups[1].Value.Replace('\\','\')
            }
        }
    }
    $seen = @{}
    foreach ($library in $libraries) {
        if ([string]::IsNullOrWhiteSpace($library)) { continue }
        $candidate = Get-SteamRetailCandidate $library
        if (!$candidate) { continue }
        # PowerShellの通常のハッシュテーブルは大文字小文字を区別しない。
        if (!$seen.ContainsKey($candidate) -and (Test-Path -LiteralPath (Join-Path $candidate 'Hellraiser\Content\Paks') -PathType Container)) {
            $seen[$candidate] = $true
            $candidate
        }
    }
}
function Find-Game {
    $steamRoots = @()
    foreach ($key in @('HKCU:\Software\Valve\Steam','HKLM:\SOFTWARE\WOW6432Node\Valve\Steam')) {
        $settings = Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue
        if ($null -eq $settings) { continue }
        foreach ($prop in @('SteamPath','InstallPath')) {
            if ($settings.PSObject.Properties[$prop]) { $steamRoots += [string]$settings.$prop }
        }
    }
    $found = @(Get-SteamGameCandidates $steamRoots)
    if ($found.Count -eq 1) { return $found[0] }
    if ($NonInteractive) { Fail 'ゲームを一意に検出できません。-GameDirで指定してください。' }
    return Read-Host 'ゲームのインストール先フォルダーを入力してください'
}
function Assert-FileList($Files) {
    if (@($Files).Count -ne 3) { Fail 'パッチファイル一覧が不正です。' }
    $seen = @{}
    foreach ($file in $Files) {
        if ($file.name -cnotin $managedNames -or $seen.ContainsKey([string]$file.name)) { Fail '管理対象外のファイルが指定されています。' }
        if ($file.sha256 -cnotmatch '^[0-9a-f]{64}$') { Fail 'ハッシュの形式が不正です。' }
        $seen[[string]$file.name] = $true
    }
}
function Get-SupportedVersions($Builds) {
    $versions = @()
    $seen = @{}
    foreach ($build in @($Builds)) {
        $version = [string]$build.version
        if ($version -cnotmatch '^[A-Za-z0-9._-]+$' -or $seen.ContainsKey($version)) { Fail '対応版の情報が不正です。' }
        $seen[$version] = $true
        $versions += $version
    }
    if (!$versions.Count) { Fail '対応版の情報がありません。' }
    return $versions
}
function Confirm-Unsupported([string]$Detected, [string[]]$Supported) {
    $display = if ([string]::IsNullOrWhiteSpace($Detected)) { '判定不能' } else { $Detected }
    [Console]::Error.WriteLine('警告: インストールされているゲーム版は、このパッチの対応版と一致しません。')
    [Console]::Error.WriteLine('検出した版: ' + $display)
    [Console]::Error.WriteLine('対応版: ' + ($Supported -join ', '))
    [Console]::Error.WriteLine('日本語が表示されない、表示が崩れる、またはゲームが起動しない可能性があります。')
    [Console]::Error.WriteLine('ゲーム本体は上書きされず、Uninstall.cmdでパッチを削除できます。')
    if ($AllowUnsupported) { return }
    if ($NonInteractive) { Fail '未対応版への適用には -AllowUnsupported を明示してください。' }
    $answer = Read-Host '続行しますか？ [y/N]'
    if ($answer -cne 'y' -and $answer -cne 'Y') { Fail '適用を中止しました。' }
}
function Assert-Package {
    Assert-NoLink $PSScriptRoot
    $checksumPath = Join-Path $PSScriptRoot 'SHA256SUMS.txt'
    if (!(Test-Path -LiteralPath $checksumPath -PathType Leaf)) { Fail 'チェックサム一覧がありません。配布ZIP全体を展開してください。' }
    $expected = @($managedNames) + @('Patch.ps1','Install.cmd','Uninstall.cmd','README.md','manifest.json','THIRD_PARTY_NOTICES.md','LICENSE')
    $seen = @{}
    foreach ($line in [IO.File]::ReadAllLines($checksumPath)) {
        if ($line -cnotmatch '^([0-9a-f]{64})  ([A-Za-z0-9_.-]+)$') { Fail 'チェックサム一覧の形式が不正です。' }
        $digest, $name = $Matches[1], $Matches[2]
        if ($name -cnotin $expected -or $seen.ContainsKey($name)) { Fail '配布ファイル一覧が不正です。' }
        $path = Join-Path $PSScriptRoot $name
        Assert-NoLink $path
        if (!(Test-Path -LiteralPath $path -PathType Leaf) -or (Hash $path) -cne $digest) { Fail '配布ファイルの整合性確認に失敗しました。ZIPを再取得してください。' }
        $seen[$name] = $true
    }
    if ($seen.Count -ne $expected.Count) { Fail '配布ファイルが不足しています。' }
}
$lock = $null
$lockPath = $null
try {
    Assert-GameStopped
    if (!$GameDir) { $GameDir = Find-Game }
    if (!$GameDir) { Fail 'ゲームのインストール先が指定されていません。' }
    $GameDir = [IO.Path]::GetFullPath($GameDir.Trim('"'))
    $pakDir = Join-Path $GameDir 'Hellraiser\Content\Paks'
    Assert-NoLink $pakDir
    if (!(Test-Path -LiteralPath $pakDir -PathType Container)) { Fail '対象のゲームフォルダーではありません。' }
    $statePath = Join-Path $pakDir $stateName
    Assert-NoLink $statePath
    $lockPath = Join-Path $pakDir '.hellraiser-revival-japanese-patch.lock'
    try { $lock = [IO.File]::Open($lockPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None) }
    catch { Fail '書き込み権限がないか、別の処理が実行中です。ロックが残る場合はREADMEを参照してください。' }
    $oldState = $null
    if (Test-Path -LiteralPath $statePath -PathType Leaf) {
        $oldState = Read-Json $statePath
        if ($oldState.schema_version -ne 1 -or $oldState.product -cne $product) { Fail '既存の管理情報を確認できません。' }
        Assert-FileList $oldState.files
    }
    foreach ($name in $managedNames) {
        $path = Join-Path $pakDir $name
        Assert-NoLink $path
        if (Test-Path -LiteralPath $path) {
            if ($null -eq $oldState) { Fail '同名の未知ファイルがあります。上書きせず中止します。' }
            $known = @($oldState.files | Where-Object { $_.name -ceq $name })[0]
            if (!(Test-Path -LiteralPath $path -PathType Leaf) -or (Hash $path) -cne $known.sha256) { Fail '導入済みファイルが変更されています。上書き・削除せず中止します。' }
        } elseif ($null -ne $oldState) { Fail '導入済みファイルが不足しています。READMEの復旧手順を確認してください。' }
    }
    if ($Action -eq 'Uninstall' -and $null -eq $oldState) { Write-Output 'このパッチは導入されていません。' }
    else {
        if ($Action -eq 'Install') {
            foreach ($trialStem in @('Hellraiser_Japanese_P','Hellraiser_Japanese_Probe_P','Hellraiser_Japanese_Font_P','Hellraiser_Revival_Japanese_Probe_P')) {
                foreach ($ext in @('pak','utoc','ucas')) {
                    if (Test-Path -LiteralPath (Join-Path $pakDir ($trialStem+'.'+$ext))) {
                        Fail 'デモ版用または旧試作のパッチが残っています。導入元の手順で削除してから切り替えてください。'
                    }
                }
            }
            if (Test-Path -LiteralPath (Join-Path $pakDir '.hellraiser-japanese-patch.json')) { Fail 'デモ版用パッチの管理情報が残っています。導入元の手順で削除してください。' }
            Assert-Package
            $manifest = Read-Json (Join-Path $PSScriptRoot 'manifest.json')
            if ($manifest.schema_version -ne 1 -or $manifest.product -cne $product -or $manifest.patch_version -cnotmatch '^\d+\.\d+\.\d+(?:-[a-z0-9.]+)?$') { Fail '配布物の対応情報が不正です。' }
            Assert-FileList $manifest.files
            $supportedVersions = @(Get-SupportedVersions $manifest.supported_builds)
            foreach ($file in $manifest.files) {
                if ((Hash (Join-Path $PSScriptRoot $file.name)) -cne $file.sha256) { Fail 'パッチのハッシュが対応情報と一致しません。' }
            }
            $installedVersion = ''
            $versionPath = Join-Path $GameDir 'Version.txt'
            Assert-NoLink $versionPath
            if (Test-Path -LiteralPath $versionPath -PathType Leaf) {
                try { $installedVersion = [IO.File]::ReadAllText($versionPath, [Text.Encoding]::UTF8).Trim() }
                catch { $installedVersion = '' }
            }
            Assert-RetailGame $GameDir $installedVersion
            if ($installedVersion -cnotin $supportedVersions) { Confirm-Unsupported $installedVersion $supportedVersions }
        }
        Assert-GameStopped
        $backup = @{}
        foreach ($name in @($managedNames) + @($stateName)) {
            $path = Join-Path $pakDir $name
            if (Test-Path -LiteralPath $path -PathType Leaf) { $backup[$name] = [IO.File]::ReadAllBytes($path) }
        }
        $changed = @()
        try {
            foreach ($name in $managedNames) {
                $path = Join-Path $pakDir $name
                $changed += $name
                if ($Action -eq 'Install') { [IO.File]::WriteAllBytes($path,[IO.File]::ReadAllBytes((Join-Path $PSScriptRoot $name))) }
                else { [IO.File]::Delete($path) }
            }
            $changed += $stateName
            if ($Action -eq 'Install') {
                $state = @{schema_version=1; product=$product; patch_version=$manifest.patch_version; files=@($manifest.files)}
                [IO.File]::WriteAllText($statePath,($state | ConvertTo-Json -Depth 8),$utf8)
                foreach ($file in $manifest.files) {
                    if ((Hash (Join-Path $pakDir $file.name)) -cne $file.sha256) { Fail 'コピー後の整合性検査に失敗しました。' }
                }
            } else { [IO.File]::Delete($statePath) }
        } catch {
            foreach ($name in $changed) {
                $path = Join-Path $pakDir $name
                if ($backup.ContainsKey($name)) { [IO.File]::WriteAllBytes($path,$backup[$name]) }
                elseif (Test-Path -LiteralPath $path -PathType Leaf) { [IO.File]::Delete($path) }
            }
            Fail '処理に失敗したため、処理前の状態に戻しました。'
        }
        if ($Action -eq 'Install') { Write-Output '導入完了。ゲームの言語設定で「日本語」を選択してください。' }
        else { Write-Output '削除完了。ゲーム本体とセーブデータは変更していません。' }
    }
} catch {
    if ($_.Exception -is [InvalidOperationException]) { [Console]::Error.WriteLine($_.Exception.Message) }
    else { [Console]::Error.WriteLine('処理を中止しました。ファイル形式、空き容量、書き込み権限を確認してください。') }
    exit 1
} finally {
    if ($null -ne $lock) { $lock.Dispose(); [IO.File]::Delete($lockPath) }
}
