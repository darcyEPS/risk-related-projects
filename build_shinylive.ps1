# build_shinylive.ps1
# Package Shinylive app into .\site with only:
# - app.py
# - ./www
# - ./data

# --- config: your Anaconda Python ---
$py = 'C:\ProgramData\anaconda3\python.exe'

Write-Host "Using Python:" $py -ForegroundColor Cyan

# 1) Sanity check
& $py --version
if ($LASTEXITCODE -ne 0) {
    throw "Python sanity check failed (is $py correct?)."
}

# 2) Install/upgrade Shinylive for THIS interpreter
Write-Host "Ensuring shinylive is installed/upgraded for this interpreter..." -ForegroundColor Cyan
& $py -m pip install --upgrade --user shinylive
if ($LASTEXITCODE -ne 0) {
    throw "pip install shinylive failed."
}

# 3) Find where Shinylive is installed and locate shinylive.exe
$pkgInfo = & $py -m pip show shinylive
if (-not $pkgInfo) { throw "pip show shinylive failed (not installed for $py?)" }

# Extract the 'Location:' line
$locLine = $pkgInfo | Where-Object { $_ -match '^Location\s*:' }
$pkgLoc  = $locLine -replace '^Location\s*:\s*',''
if (-not (Test-Path $pkgLoc)) { throw "Can't resolve Shinylive Location: $pkgLoc" }

# On Windows, console scripts sit in the sibling 'Scripts' dir to site-packages parent
$maybeRoot  = Split-Path $pkgLoc -Parent
$scriptDir1 = Join-Path $maybeRoot 'Scripts'
$exe1       = Join-Path $scriptDir1 'shinylive.exe'

# Also check the base env Scripts just in case
$baseScripts = Join-Path (Split-Path $py -Parent) 'Scripts'
$exe2        = Join-Path $baseScripts 'shinylive.exe'

# And PATH, if available
$exe3 = (Get-Command shinylive -ErrorAction SilentlyContinue).Source

# Pick the first that exists
$shinylive = $null
foreach ($cand in @($exe1,$exe2,$exe3)) {
  if ($cand -and (Test-Path $cand)) { $shinylive = $cand; break }
}
if (-not $shinylive) {
  Write-Host "Tried:`n $exe1`n $exe2`n $exe3" -ForegroundColor Yellow
  throw "Couldn't find shinylive.exe (installed at $pkgLoc)."
}

Write-Host "Using shinylive:" $shinylive -ForegroundColor Cyan

# --------- BUILD FROM A MINIMAL TEMP APP FOLDER ---------

$root     = Get-Location
$buildDir = Join-Path $root '_shinylive_build'

Write-Host "Preparing clean build directory: $buildDir" -ForegroundColor Cyan

# Remove old temp build dir if it exists
if (Test-Path $buildDir) {
    Remove-Item $buildDir -Recurse -Force
}

New-Item -ItemType Directory -Path $buildDir | Out-Null

#  Copy ONLY the pieces we want: app.py, www, data
$appPy = Join-Path $root 'app.py'
if (-not (Test-Path $appPy)) {
    throw "app.py not found in $root . This script expects app.py in the current folder."
}

Copy-Item $appPy $buildDir -Force

foreach ($folder in @('www', 'data')) {
    $src = Join-Path $root $folder
    if (Test-Path $src) {
        Write-Host "Including folder: $folder" -ForegroundColor Green
        Copy-Item $src $buildDir -Recurse -Force
    }
    else {
        Write-Host "Folder not found (skipping): $folder" -ForegroundColor Yellow
    }
}

# 4) Export temp app folder -> .\site
$siteDir = Join-Path $root 'site'

Write-Host "Cleaning previous site directory (if any)..." -ForegroundColor Cyan
if (Test-Path $siteDir) {
    Remove-Item $siteDir -Recurse -Force
}

Write-Host "Exporting Shinylive app from _shinylive_build to site..." -ForegroundColor Cyan
& $shinylive export $buildDir $siteDir
if ($LASTEXITCODE -ne 0) {
    throw "shinylive export failed."
}

# Optional: clean up temp build dir
Write-Host "Removing temporary build directory..." -ForegroundColor Cyan
Remove-Item $buildDir -Recurse -Force

# 5) Patch the HTML <title> in site/index.html
$indexPath   = Join-Path $siteDir 'index.html'
$customTitle = 'Mainland Coast Salish Area Risk-Related Projects Database'

if (Test-Path $indexPath) {
    Write-Host "Patching <title> in site\index.html..." -ForegroundColor Cyan
    $html = Get-Content $indexPath -Raw

    # Replace whatever <title>...</title> is there with our custom title
    $html = $html -replace '<title>.*?</title>', "<title>$customTitle</title>"

    Set-Content -Path $indexPath -Value $html -Encoding UTF8

    Write-Host "Updated <title> in site\index.html to '$customTitle'." -ForegroundColor Green
} else {
    Write-Host "Warning: site\index.html not found; could not update title." -ForegroundColor Yellow
}

Write-Host "Shinylive packaging complete. Output: $siteDir" -ForegroundColor Green
