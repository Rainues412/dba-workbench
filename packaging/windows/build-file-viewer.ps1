[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$SourceDirectory,
    [Parameter(Mandatory = $true)][string]$Destination,
    [Parameter(Mandatory = $true)][string]$CacheDirectory
)

$ErrorActionPreference = "Stop"
$expectedCommit = "3b82689a676e8a7e7d3ec4cc0c74de0676b0dac9"
$temurinVersion = "21.0.12.1_1"
$jdkUrl = "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_windows_hotspot_$temurinVersion.zip"
$jdkSha256 = "F9D6E191AB098C0D416E7D588A24420A8621CD2F4720DAB2459B8B7B2D2D8B4E"
$jreUrl = "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jre_x64_windows_hotspot_$temurinVersion.zip"
$jreSha256 = "D35F31E712F0FCF6AC5A093EDC90204FBFF22F720BA3950BD09D331D5E621636"
$mavenVersion = "3.9.11"
$mavenUrl = "https://archive.apache.org/dist/maven/maven-3/$mavenVersion/binaries/apache-maven-$mavenVersion-bin.zip"
$mavenSha512 = "03E2D65D4483A3396980629F260E25CAC0D8B6F7F2791E4DC20BC83F9514DB8D0F05B0479E699A5F34679250C49C8E52E961262DED468A20DE0BE254D8207076"

function Get-VerifiedArchive {
    param([string]$Url, [string]$Path, [string]$Algorithm, [string]$ExpectedHash)
    if (Test-Path -LiteralPath $Path) {
        $actual = (Get-FileHash -LiteralPath $Path -Algorithm $Algorithm).Hash
        if ($actual -ne $ExpectedHash) {
            Remove-Item -LiteralPath $Path
        }
    }
    if (-not (Test-Path -LiteralPath $Path)) {
        $partial = "$Path.partial"
        $curlArguments = @(
            "--fail",
            "--location",
            "--retry", "10",
            "--retry-delay", "5",
            "--retry-all-errors",
            "--connect-timeout", "30",
            "--output", $partial
        )
        if ((Test-Path -LiteralPath $partial) -and (Get-Item -LiteralPath $partial).Length -gt 0) {
            $curlArguments += @("--continue-at", "-")
        }
        $curlArguments += $Url
        & curl.exe @curlArguments
        if ($LASTEXITCODE -ne 0) {
            throw "下载失败：$Url。已保留断点文件以便重试：$partial"
        }
        Move-Item -LiteralPath $partial -Destination $Path
    }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm $Algorithm).Hash
    if ($actual -ne $ExpectedHash) {
        throw "下载文件校验失败：$Path"
    }
}

function Expand-CleanArchive {
    param([string]$Archive, [string]$Directory)
    if (Test-Path -LiteralPath $Directory) {
        Remove-Item -LiteralPath $Directory -Recurse
    }
    New-Item -ItemType Directory -Path $Directory | Out-Null
    Expand-Archive -LiteralPath $Archive -DestinationPath $Directory
}

$source = [System.IO.Path]::GetFullPath($SourceDirectory)
$destinationRoot = [System.IO.Path]::GetFullPath($Destination)
$cacheRoot = [System.IO.Path]::GetFullPath($CacheDirectory)
if (-not (Test-Path -LiteralPath (Join-Path $source "server\pom.xml"))) {
    throw "kkFileView 子模块未初始化。请执行 git submodule update --init --recursive。"
}
$actualCommit = (& git -C $source rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actualCommit -ne $expectedCommit) {
    throw "kkFileView 必须固定到 v5.0.3 ($expectedCommit)，当前为 $actualCommit。"
}

$downloads = Join-Path $cacheRoot "file-viewer-downloads"
$toolchains = Join-Path $cacheRoot "file-viewer-toolchains"
New-Item -ItemType Directory -Path $downloads, $toolchains -Force | Out-Null
$jdkArchive = Join-Path $downloads "temurin-jdk-$temurinVersion.zip"
$jreArchive = Join-Path $downloads "temurin-jre-$temurinVersion.zip"
$mavenArchive = Join-Path $downloads "apache-maven-$mavenVersion-bin.zip"
Get-VerifiedArchive $jdkUrl $jdkArchive "SHA256" $jdkSha256
Get-VerifiedArchive $jreUrl $jreArchive "SHA256" $jreSha256
Get-VerifiedArchive $mavenUrl $mavenArchive "SHA512" $mavenSha512

$jdkExtract = Join-Path $toolchains "jdk-$temurinVersion"
$jreExtract = Join-Path $toolchains "jre-$temurinVersion"
$mavenExtract = Join-Path $toolchains "maven-$mavenVersion"
if (-not (Test-Path -LiteralPath $jdkExtract)) { Expand-CleanArchive $jdkArchive $jdkExtract }
if (-not (Test-Path -LiteralPath $jreExtract)) { Expand-CleanArchive $jreArchive $jreExtract }
if (-not (Test-Path -LiteralPath $mavenExtract)) { Expand-CleanArchive $mavenArchive $mavenExtract }
$jdkHome = (Get-ChildItem -LiteralPath $jdkExtract -Directory | Select-Object -First 1).FullName
$jreHome = (Get-ChildItem -LiteralPath $jreExtract -Directory | Select-Object -First 1).FullName
$mavenHome = (Get-ChildItem -LiteralPath $mavenExtract -Directory | Select-Object -First 1).FullName
if (-not $jdkHome -or -not $jreHome -or -not $mavenHome) {
    throw "文件预览构建工具解压不完整。"
}

$previousJavaHome = $env:JAVA_HOME
$previousPath = $env:PATH
$env:JAVA_HOME = $jdkHome
$env:PATH = "$jdkHome\bin;$mavenHome\bin;$previousPath"
try {
    $mavenRepository = Join-Path $cacheRoot "maven-repository"
    New-Item -ItemType Directory -Path $mavenRepository -Force | Out-Null
    & (Join-Path $mavenHome "bin\mvn.cmd") `
        "-Dmaven.repo.local=$mavenRepository" `
        -f (Join-Path $source "pom.xml") `
        -pl server `
        -am `
        package `
        "-DskipTests" `
        "-Dassembly.skipAssembly=true"
    if ($LASTEXITCODE -ne 0) { throw "kkFileView v5.0.3 构建失败。" }
} finally {
    $env:JAVA_HOME = $previousJavaHome
    $env:PATH = $previousPath
}

$viewerJar = Get-ChildItem -LiteralPath (Join-Path $source "server\target") -Filter "kkFileView-*.jar" -File |
    Where-Object { $_.Name -notmatch "^(original-|.*-(sources|javadoc)\.jar$)" } |
    Sort-Object Length -Descending |
    Select-Object -First 1
if (-not $viewerJar) { throw "未找到 kkFileView 可执行 JAR。" }

if (Test-Path -LiteralPath $destinationRoot) {
    Remove-Item -LiteralPath $destinationRoot -Recurse
}
New-Item -ItemType Directory -Path $destinationRoot | Out-Null
New-Item -ItemType Directory -Path (Join-Path $destinationRoot "bin"), (Join-Path $destinationRoot "config") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $destinationRoot "templates") | Out-Null
Copy-Item -LiteralPath $viewerJar.FullName -Destination (Join-Path $destinationRoot "kkFileView.jar")
Copy-Item -LiteralPath (Join-Path $source "server\LibreOfficePortable") -Destination $destinationRoot -Recurse
Copy-Item -LiteralPath (Join-Path $source "server\src\main\config\application.properties") -Destination (Join-Path $destinationRoot "config\application.properties")
$htmlTemplate = Get-Content -LiteralPath (Join-Path $source "server\src\main\resources\web\code.ftl") -Raw -Encoding utf8
$htmlTemplate = $htmlTemplate.Replace("        loadText();", "        loadXmlData();")
Set-Content -LiteralPath (Join-Path $destinationRoot "templates\code.ftl") -Value $htmlTemplate -Encoding utf8
$viewerConfigPath = Join-Path $destinationRoot "config\application.properties"
$viewerConfig = Get-Content -LiteralPath $viewerConfigPath -Raw -Encoding utf8
$viewerConfig = $viewerConfig.Replace('kk.key = false', 'kk.key = ${KK_KEY:false}')
Set-Content -LiteralPath $viewerConfigPath -Value $viewerConfig -Encoding utf8
Copy-Item -LiteralPath $jreHome -Destination (Join-Path $destinationRoot "runtime") -Recurse
Copy-Item -LiteralPath (Join-Path $source "LICENSE") -Destination (Join-Path $destinationRoot "LICENSE-kkFileView.txt")

$notice = @"
DBA 工作台内置文件预览由 kkFileView v5.0.3 提供。
项目：https://github.com/kekingcn/kkFileView
版本提交：$expectedCommit
许可：Apache License 2.0（见 LICENSE-kkFileView.txt）

Java 运行时：Eclipse Temurin JRE 21.0.12.1+1。
项目：https://github.com/adoptium/temurin21-binaries
随附法律文件位于 runtime/legal。

Office 文档转换：kkFileView 随附的 LibreOffice Portable。
许可与声明位于 LibreOfficePortable/App/libreoffice/LICENSE.html 与 NOTICE。
"@
Set-Content -LiteralPath (Join-Path $destinationRoot "THIRD-PARTY-NOTICES.txt") -Value $notice -Encoding utf8
