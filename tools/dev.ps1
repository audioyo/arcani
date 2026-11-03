# Runs a command (cmake, ctest, ...) inside the Visual Studio developer
# environment for this machine (x64, or ARM64 on a Windows arm64 host), so
# clang-cl and lld-link find the Windows SDK and the MSVC STL.
#
# Usage: powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl
#
# The pinned CMake, Ninja, and LLVM stay ahead of anything the VS environment
# adds (VS ships its own CMake and Ninja), so the toolchain pin check sees the
# pinned tools. Arguments are read from $args so cmake flags pass through as is.

$ErrorActionPreference = 'Stop'

if ($args.Count -lt 1) {
    [Console]::Error.WriteLine('usage: tools/dev.ps1 <command> [arguments...]')
    exit 2
}

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path $vswhere)) {
    [Console]::Error.WriteLine("vswhere not found at $vswhere; install Visual Studio with the C++ workload")
    exit 1
}
# Pick the developer environment for this machine. A process emulated on
# arm64 sees AMD64 in PROCESSOR_ARCHITECTURE and ARM64 in PROCESSOR_ARCHITEW6432.
$arch = $env:PROCESSOR_ARCHITEW6432
if (-not $arch) { $arch = $env:PROCESSOR_ARCHITECTURE }
if ($arch -ieq 'ARM64') {
    $vcComponent = 'Microsoft.VisualStudio.Component.VC.Tools.ARM64'
    $vcvarsName = 'vcvarsarm64.bat'
    $archLabel = 'ARM64'
} else {
    $vcComponent = 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64'
    $vcvarsName = 'vcvars64.bat'
    $archLabel = 'x64'
}
$vsPath = & $vswhere -latest -products * -requires $vcComponent -property installationPath
if (-not $vsPath) {
    [Console]::Error.WriteLine("No Visual Studio installation with the $archLabel C++ tools was found")
    exit 1
}
$vcvars = Join-Path $vsPath "VC\Auxiliary\Build\$vcvarsName"

# Base PATH: this shell's PATH, then any user or machine PATH entries a shell
# opened before an install would be missing.
$entries = New-Object System.Collections.Generic.List[string]
$seen = @{}
function Add-PathEntries([string]$pathValue) {
    if (-not $pathValue) { return }
    foreach ($p in $pathValue.Split(';')) {
        $key = $p.Trim().TrimEnd('\').ToLowerInvariant()
        if ($key -and -not $seen.ContainsKey($key)) {
            $seen[$key] = $true
            $entries.Add($p.Trim())
        }
    }
}
Add-PathEntries $env:PATH
Add-PathEntries ([Environment]::GetEnvironmentVariable('Path', 'User'))
Add-PathEntries ([Environment]::GetEnvironmentVariable('Path', 'Machine'))

# Capture the environment the vcvars script produces.
$vsEnv = & cmd.exe /d /s /c "`"$vcvars`" >nul 2>&1 && set"
if ($LASTEXITCODE -ne 0) {
    [Console]::Error.WriteLine("$vcvarsName failed ($vcvars)")
    exit 1
}
$vsPathValue = $null
foreach ($line in $vsEnv) {
    $i = $line.IndexOf('=')
    if ($i -le 0) { continue }
    $name = $line.Substring(0, $i)
    $value = $line.Substring($i + 1)
    if ($name -ieq 'PATH') { $vsPathValue = $value; continue }
    Set-Item -Path "Env:$name" -Value $value
}
# VS additions go after the base entries.
Add-PathEntries $vsPathValue
$env:PATH = ($entries -join ';')

$exe = $args[0]
$rest = @()
if ($args.Count -gt 1) { $rest = $args[1..($args.Count - 1)] }
& $exe @rest
exit $LASTEXITCODE
