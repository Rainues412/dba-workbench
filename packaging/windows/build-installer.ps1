[CmdletBinding()]
param(
    [string]$OutputDirectory,
    [string]$Version = "1.0.0",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path (Split-Path $repoRoot -Parent) "DBA工作台-发布"
}
$outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
$sourceRoot = [System.IO.Path]::GetFullPath($repoRoot)
if ($outputRoot.StartsWith($sourceRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "构建输出目录必须位于 Git 源码目录之外。"
}

$buildRoot = Join-Path $outputRoot ".build"
$venvRoot = Join-Path $buildRoot "venv"
$nuitkaRoot = Join-Path $buildRoot "nuitka"
$cacheRoot = Join-Path $buildRoot "cache"
$toolsRoot = Join-Path $buildRoot "tools"
$releaseRoot = Join-Path $outputRoot "installer"
$python = Join-Path $venvRoot "Scripts\python.exe"
$iscc = Join-Path $toolsRoot "Inno Setup 7\ISCC.exe"
$iconPath = Join-Path $repoRoot "assets\dba-workbench-icon.ico"

New-Item -ItemType Directory -Force -Path $buildRoot, $nuitkaRoot, $cacheRoot, $toolsRoot, $releaseRoot | Out-Null
$env:PIP_CACHE_DIR = Join-Path $cacheRoot "pip"
$env:NUITKA_CACHE_DIR = $cacheRoot
$env:TEMP = Join-Path $buildRoot "temp"
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:PIP_CACHE_DIR, $env:TEMP | Out-Null

if (-not (Test-Path $python)) {
    $bootstrapPython = (Get-Command py.exe -ErrorAction SilentlyContinue)
    if (-not $bootstrapPython) {
        throw "构建机需要 Python 3.12 x64；目标安装机不需要 Python。"
    }
    & $bootstrapPython.Source -3.12 -m venv $venvRoot
}

& $python -m pip install --disable-pip-version-check -r (Join-Path $repoRoot "server\requirements-build.txt")

if (-not $SkipTests) {
    & $python -m pip install --disable-pip-version-check -r (Join-Path $repoRoot "server\requirements-dev.txt")
    Push-Location $repoRoot
    try { & $python -m pytest } finally { Pop-Location }
}

if (Test-Path $nuitkaRoot) {
    $resolvedNuitkaRoot = [System.IO.Path]::GetFullPath($nuitkaRoot)
    $resolvedBuildRoot = [System.IO.Path]::GetFullPath($buildRoot)
    if (-not $resolvedNuitkaRoot.StartsWith($resolvedBuildRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Nuitka 清理目录超出构建目录。"
    }
    Get-ChildItem -LiteralPath $nuitkaRoot -Force | Remove-Item -Recurse -Force
}

Push-Location (Join-Path $repoRoot "server")
try {
    & $python -m nuitka `
        --mode=standalone `
        --assume-yes-for-downloads `
        --windows-console-mode=disable `
        --windows-icon-from-ico=$iconPath `
        --output-dir=$nuitkaRoot `
        --output-filename="DBA工作台.exe" `
        --include-data-dir="frontend_dist=frontend_dist" `
        --include-data-files="backend/migrations/*.sql=backend/migrations/" `
        --include-module=main `
        --include-package=backend `
        --include-module=h11 `
        --nofollow-import-to=pytest `
        desktop.py
    if ($LASTEXITCODE -ne 0) { throw "Nuitka 编译失败。" }
} finally {
    Pop-Location
}

$distDir = Join-Path $nuitkaRoot "desktop.dist"
$executable = Join-Path $distDir "DBA工作台.exe"
if (-not (Test-Path $executable)) {
    throw "未找到 Nuitka 输出：$executable"
}
$forbidden = Get-ChildItem -LiteralPath $distDir -Recurse -Force -File | Where-Object {
    $_.Extension -in ".py", ".pyc", ".ts", ".tsx", ".map" -or $_.Name -eq "workspace.db"
}
if ($forbidden) {
    throw "发行目录包含不应交付的源码或数据：$($forbidden.FullName -join ', ')"
}

if (-not (Test-Path $iscc)) {
    $innoInstaller = Join-Path $toolsRoot "innosetup-7.1.0-x64.exe"
    $innoUrl = "https://github.com/jrsoftware/issrc/releases/download/is-7_1_0/innosetup-7.1.0-x64.exe"
    $innoSha256 = "0362A383ED217D4C4239B5933866DD96D3EB2102737DA92F80F6057A4B40DF2F"
    if (-not (Test-Path $innoInstaller)) {
        Invoke-WebRequest -Uri $innoUrl -OutFile $innoInstaller
    }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $innoInstaller).Hash -ne $innoSha256) {
        throw "Inno Setup 安装器校验失败。"
    }
    $innoDirectory = Join-Path $toolsRoot "Inno Setup 7"
    $process = Start-Process -FilePath $innoInstaller -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/CURRENTUSER", "/DIR=`"$innoDirectory`""
    ) -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0 -or -not (Test-Path $iscc)) {
        throw "Inno Setup 编译器安装失败。"
    }
}

$iss = Join-Path $repoRoot "packaging\windows\installer.iss"
& $iscc "/DSourceDir=$distDir" "/DOutputDir=$releaseRoot" "/DAppVersion=$Version" $iss
if ($LASTEXITCODE -ne 0) { throw "安装程序生成失败。" }

$installer = Get-ChildItem -LiteralPath $releaseRoot -Filter "DBA工作台-安装程序-$Version-x64.exe" | Select-Object -First 1
if (-not $installer) { throw "没有找到最终安装程序。" }
$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $installer.FullName
$hashLine = "$($hash.Hash) *$($installer.Name)"
Set-Content -LiteralPath (Join-Path $releaseRoot "$($installer.Name).sha256") -Value $hashLine -Encoding utf8
Write-Host "安装程序：$($installer.FullName)"
Write-Host "SHA256：$($hash.Hash)"
