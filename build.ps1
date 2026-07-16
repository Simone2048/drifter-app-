# Build script for Drifter
# Compiles main.py into a standalone Windows .exe using PyInstaller

Write-Host "=== Drifter Build Script ===" -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python not found. Please install Python 3.10+ from https://python.org" -ForegroundColor Red
    exit 1
}

Write-Host "[1/3] Installing dependencies..." -ForegroundColor Yellow
python -m pip install customtkinter pyinstaller --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to install dependencies." -ForegroundColor Red
    exit 1
}
Write-Host "       Done." -ForegroundColor Green

Write-Host "[2/3] Building executable..." -ForegroundColor Yellow
$buildArgs = @(
    "--onefile",
    "--windowed",
    "--name", "Drifter",
    "--clean",
    "--noconfirm",
    "--noupx",
    "main.py"
)
python -m PyInstaller @buildArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: PyInstaller build failed." -ForegroundColor Red
    exit 1
}
Write-Host "       Done." -ForegroundColor Green

Write-Host "[3/3] Moving executable..." -ForegroundColor Yellow
if (Test-Path "dist\Drifter.exe") {
    Copy-Item "dist\Drifter.exe" "Drifter.exe" -Force
    Write-Host "       Drifter.exe is ready in the current directory." -ForegroundColor Green
} else {
    Write-Host "WARNING: dist\Drifter.exe not found. Check dist\ folder." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Build Complete ===" -ForegroundColor Cyan
Write-Host "Run .\Drifter.exe to launch the app." -ForegroundColor White
