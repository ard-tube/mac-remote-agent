$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildDir = Join-Path $Root "windows\.build"
$DistDir = Join-Path $Root "dist\windows"
$Python = (Get-Command python).Source

if (Test-Path $BuildDir) {
    Remove-Item -Recurse -Force $BuildDir
}
New-Item -ItemType Directory -Force $BuildDir, $DistDir | Out-Null

& $Python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")

& $Python -m PyInstaller --noconfirm --clean --windowed --onedir `
    --name MacRemote --distpath $DistDir --workpath $BuildDir `
    --specpath $BuildDir --hidden-import pystray._win32 `
    (Join-Path $PSScriptRoot "host_app.py")
if ($LASTEXITCODE -ne 0) { throw "Windows app packaging failed." }

& $Python -m PyInstaller --noconfirm --clean --onefile `
    --name MacRemoteAgent --distpath (Join-Path $BuildDir "agent-dist") `
    --workpath (Join-Path $BuildDir "agent-work") `
    --specpath $BuildDir (Join-Path $Root "agent.py")
if ($LASTEXITCODE -ne 0) { throw "Windows agent packaging failed." }

Copy-Item (Join-Path $BuildDir "agent-dist\MacRemoteAgent.exe") `
    (Join-Path $DistDir "MacRemote\MacRemoteAgent.exe")
Copy-Item (Join-Path $Root "LICENSE") (Join-Path $DistDir "MacRemote\LICENSE")
Compress-Archive -Path (Join-Path $DistDir "MacRemote\*") `
    -DestinationPath (Join-Path $Root "dist\MacRemote-Windows.zip") -Force
Write-Output "Built Windows app: $(Join-Path $Root 'dist\MacRemote-Windows.zip')"
