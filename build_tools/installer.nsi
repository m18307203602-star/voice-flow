; Voice Flow Windows Installer
; NSIS 3.x

Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"

!define PRODUCT_NAME "Voice Flow"
!define PRODUCT_VERSION "2.0.0"
!define PRODUCT_PUBLISHER "VoiceFlow"
!define PRODUCT_WEB_SITE "https://github.com/voice-flow"
!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\VoiceFlow.exe"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "G:\voice-workflow\dist\VoiceFlow-Setup-2.0.0.exe"
InstallDir "$PROGRAMFILES\VoiceFlow"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
RequestExecutionLevel admin
SetCompressor /SOLID lzma

!define MUI_ABORTWARNING
!define MUI_ICON "..\voice_flow_app\resources\icon.ico"
!define MUI_UNICON "..\voice_flow_app\resources\icon.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

Section "VoiceFlow" SecMain
    SetOutPath "$INSTDIR"
    SetOverwrite on

    File /r "..\dist\VoiceFlow\*.*"

    CreateDirectory "$INSTDIR\data"
    CreateDirectory "$INSTDIR\data\logs"
    CreateDirectory "$INSTDIR\data\history"

    WriteUninstaller "$INSTDIR\uninst.exe"

    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayName" "${PRODUCT_NAME}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninst.exe"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\VoiceFlow.exe"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
    WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "NoModify" 1
    WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "NoRepair" 1
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "EstimatedSize" "$0"

    WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\VoiceFlow.exe"
    WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "Path" "$INSTDIR"

    CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Voice Flow.lnk" "$INSTDIR\VoiceFlow.exe"
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall Voice Flow.lnk" "$INSTDIR\uninst.exe"

    CreateShortCut "$DESKTOP\Voice Flow.lnk" "$INSTDIR\VoiceFlow.exe"
SectionEnd

Section "Uninstall"
    Delete "$SMPROGRAMS\${PRODUCT_NAME}\Voice Flow.lnk"
    Delete "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall Voice Flow.lnk"
    RMDir "$SMPROGRAMS\${PRODUCT_NAME}"

    Delete "$DESKTOP\Voice Flow.lnk"

    RMDir /r "$INSTDIR"

    DeleteRegKey HKLM "${PRODUCT_UNINST_KEY}"
    DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"
SectionEnd
