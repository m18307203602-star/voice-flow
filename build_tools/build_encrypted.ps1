# Voice Flow 一键打包脚本（加密版）
# 用法: powershell -File build_encrypted.ps1
# 加密流程: PyArmor 混淆 -> PyInstaller 打包 -> NSIS 安装包
# 原始文件 G:\voice-workflow\voice_flow_app\ 不会被修改

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = "C:\Users\Administrator\.hermes\hermes-agent\venv\Scripts\python.exe"
$pyarmor = "C:\Users\Administrator\.hermes\hermes-agent\venv\Scripts\pyarmor.exe"
$makensis = "C:\Program Files (x86)\NSIS\makensis.exe"
$spec = "$root\build_tools\voiceflow_enc.spec"
$nsis = "$root\build_tools\installer.nsi"
$src = "$root\voice_flow_app"
$enc = "$root\build\voice_flow_app_enc"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Voice Flow 打包构建（加密版）" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 第 1 步：清理旧构建
Write-Host "[1/4] 清理旧构建..." -ForegroundColor Yellow
if (Test-Path "$root\dist") { Remove-Item -Recurse -Force "$root\dist" }
if (Test-Path "$enc") { Remove-Item -Recurse -Force "$enc" }
Write-Host "      清理完成" -ForegroundColor Green

# 第 2 步：PyArmor 代码混淆
Write-Host "[2/4] PyArmor 代码混淆..." -ForegroundColor Yellow
& $pyarmor gen --output "$enc" "$src"
if ($LASTEXITCODE -ne 0) {
    Write-Host "      PyArmor 混淆失败！" -ForegroundColor Red
    exit 1
}
Write-Host "      PyArmor 混淆完成" -ForegroundColor Green

# 验证混淆输出
if (-not (Test-Path "$enc\voice_flow_app\main.py")) {
    Write-Host "      错误: 混淆输出不完整" -ForegroundColor Red
    exit 1
}
$pyCount = (Get-ChildItem -Recurse -Path "$enc" -Filter "*.py").Count
Write-Host "      混淆模块: ${pyCount} 个" -ForegroundColor Gray

# 第 3 步：PyInstaller 构建
Write-Host "[3/4] PyInstaller 构建..." -ForegroundColor Yellow
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

# 第 4 步：NSIS 安装包
Write-Host "[4/4] NSIS 安装包..." -ForegroundColor Yellow
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
    Write-Host "  [加密保护] PyArmor 代码混淆已启用" -ForegroundColor Magenta
    Write-Host "========================================" -ForegroundColor Cyan
} else {
    Write-Host "  错误: 安装包未生成" -ForegroundColor Red
    exit 1
}
