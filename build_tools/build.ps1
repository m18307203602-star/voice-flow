# Voice Flow 一键打包脚本
# 用法: powershell -File build.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe"
$makensis = "C:\Program Files (x86)\NSIS\makensis.exe"
$spec = "$root\build_tools\voiceflow.spec"
$nsis = "$root\build_tools\installer.nsi"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Voice Flow 打包构建" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 第 1 步：清理旧构建
Write-Host "[1/3] 清理旧构建..." -ForegroundColor Yellow
if (Test-Path "$root\dist") { Remove-Item -Recurse -Force "$root\dist" }
if (Test-Path "$root\build") { Remove-Item -Recurse -Force "$root\build" }
Write-Host "      清理完成" -ForegroundColor Green

# 第 2 步：PyInstaller 构建
Write-Host "[2/3] PyInstaller 构建..." -ForegroundColor Yellow
& $python -m PyInstaller $spec --clean --noconfirm --distpath "$root\dist" --workpath "$root\build"
if ($LASTEXITCODE -ne 0) {
    Write-Host "      PyInstaller 构建失败！" -ForegroundColor Red
    exit 1
}
Write-Host "      PyInstaller 构建完成" -ForegroundColor Green

# 验证输出
$exe = "$root\dist\VoiceFlow\VoiceFlow.exe"
if (-not (Test-Path $exe)) {
    Write-Host "      错误: 找不到 $exe" -ForegroundColor Red
    exit 1
}
$exeSize = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "      VoiceFlow.exe: ${exeSize}MB" -ForegroundColor Gray

# 第 3 步：NSIS 安装包
Write-Host "[3/3] NSIS 安装包..." -ForegroundColor Yellow
& $makensis $nsis
if ($LASTEXITCODE -ne 0) {
    Write-Host "      NSIS 构建失败！" -ForegroundColor Red
    exit 1
}
Write-Host "      NSIS 构建完成" -ForegroundColor Green

# 完成
$setup = "$root\dist\VoiceFlow-Setup.exe"
if (Test-Path $setup) {
    $size = [math]::Round((Get-Item $setup).Length / 1MB, 1)
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  构建成功！" -ForegroundColor Green
    Write-Host "  安装包: $setup" -ForegroundColor White
    Write-Host "  大小: ${size}MB" -ForegroundColor White
    Write-Host "========================================" -ForegroundColor Cyan
} else {
    Write-Host "  错误: 安装包未生成" -ForegroundColor Red
    exit 1
}
