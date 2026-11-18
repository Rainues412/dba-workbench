[CmdletBinding()]
param([Parameter(Mandatory)][string]$OutputDirectory)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).ProviderPath
$output = [System.IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
if ($output.Equals($repoRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $output.StartsWith($repoRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw '源码启动宿主的输出目录必须位于 Git 源码目录之外。'
}

$compiler = Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) {
    throw '未找到 64 位 .NET Framework C# 编译器。'
}

New-Item -ItemType Directory -Path $output -Force | Out-Null
$hostPath = Join-Path $output 'DBA工作台.exe'
$icon = Join-Path $repoRoot 'assets\dba-workbench-icon.ico'
& $compiler /nologo /target:winexe /platform:x64 /optimize+ /codepage:65001 "/win32icon:$icon" "/out:$hostPath" (Join-Path $PSScriptRoot 'DesktopHost.cs')
if ($LASTEXITCODE -ne 0) { throw '编译 DBA 工作台源码启动宿主失败。' }
Write-Output $hostPath
