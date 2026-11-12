<#
.SYNOPSIS
    Builds HomeLabMaker for Windows: the application as a folder, and a zip of it.

.PARAMETER OutDir
    Where the finished application goes. Defaults to "dist" in the repository. If your
    checkout sits deep inside nested folders, pass a short path: Windows stops at 260
    characters unless long paths are switched on.

.NOTES
    An installer is not built yet; that comes with the first public release.
#>
param(
    [string]$OutDir = "dist"
)

# Not "Stop": Windows PowerShell 5.1 would treat any text a tool writes to stderr
# (pip's upgrade notice, say) as a failure. Every step checks its exit code instead.
$repo = Resolve-Path "$PSScriptRoot\.."
Set-Location $repo

python -m pip install --quiet -e ".[build]"
if ($LASTEXITCODE -ne 0) { throw "could not install the build requirements" }

# From the package that was just installed, which is the number the app shows.
$version = (python -c "import homelab_maker; print(homelab_maker.__version__)").Trim()
if ($LASTEXITCODE -ne 0 -or -not $version) { throw "could not read the version from the package" }
Write-Host "Building HomeLabMaker $version"

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }
$OutDir = (Resolve-Path $OutDir).Path

# The icon is drawn in code; write it out as the file Windows wants for the .exe.
$icon = Join-Path $OutDir "homelab-maker.ico"
$env:QT_QPA_PLATFORM = "offscreen"
python -m homelab_maker.gui.icons $icon
if ($LASTEXITCODE -ne 0) { throw "could not draw the icon" }

$work = Join-Path $OutDir "work"
python -m PyInstaller packaging\launcher.py `
    --noconfirm --clean --windowed --onedir `
    --name HomeLabMaker `
    --icon $icon `
    --paths src `
    --distpath $OutDir `
    --workpath $work `
    --specpath $work
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$app = Join-Path $OutDir "HomeLabMaker"
$zip = Join-Path $OutDir "HomeLabMaker-$version-windows.zip"
Compress-Archive -Path $app -DestinationPath $zip -Force -ErrorAction Stop
Write-Host "Built  $app"
Write-Host "Zipped $zip"
