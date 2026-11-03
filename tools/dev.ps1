# Runs a command (cmake, ctest, ...) inside the Visual Studio x64 developer
# environment, so clang-cl and lld-link find the Windows SDK and the MSVC STL.
#
# Usage: powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl
#
# The pinned CMake, Ninja, and LLVM stay ahead of anything the VS environment
# adds (VS ships its own CMake and Ninja), so the toolchain pin check sees the
# pinned tools. Arguments are read from $args so cmake flags pass through as is.

$ErrorActionPreference = 'Stop'

if ($args.Count -lt 1) {
    Write-Error 'usage: tools/dev.ps1 <command> [arguments...]'
    exit 2
}

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path $vswhere)) {
    Write-Error "vswhere not found at $vswhere; install Visual Studio with the C++ workload"
    exit 1
}
$vsPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsPath) {
    Write-Error 'No Visual Studio installation with the x64 C++ tools was found'
    exit 1
}
$vcvars = Join-Path $vsPath 'VC\Auxiliary\Build\vcvars64.bat'

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

# Capture the environment vcvars64.bat produces.
$vsEnv = & cmd.exe /d /s /c "`"$vcvars`" >nul 2>&1 && set"
if ($LASTEXITCODE -ne 0) {
    Write-Error "vcvars64.bat failed ($vcvars)"
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
