@echo off
chcp 65001 >nul
:: 安装加密版后运行此脚本，重命名快捷方式以便区分
if exist "%USERPROFILE%\Desktop\Voice Flow.lnk" (
    ren "%USERPROFILE%\Desktop\Voice Flow.lnk" "Voice Flow 加密版.lnk"
    echo ✅ 已重命名: Voice Flow 加密版
) else (
    echo ⚠️ 未找到 Voice Flow.lnk，请先安装加密版
)
:: 开始菜单
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Voice Flow\Voice Flow.lnk" (
    ren "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Voice Flow\Voice Flow.lnk" "Voice Flow 加密版.lnk"
    echo ✅ 开始菜单已重命名
)
pause
