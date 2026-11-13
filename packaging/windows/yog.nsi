; Windows installer for yogc (the YOG policy compiler). Built on Linux with makensis by scripts/build_downloads.sh:
;   makensis -DVERSION=<engine commit> -DSRC=<folder with yogc.exe, README.txt, LICENSE.txt, policy.yog> -DOUTFILE=<setup.exe> yog.nsi
; Per-user install (no administrator rights): %LOCALAPPDATA%\Programs\YOG, added to the user's PATH, with a Start-menu
; folder and an entry in "Installed apps". The uninstaller removes all of it, including the PATH entry.
Unicode true
SetCompressor /SOLID lzma
RequestExecutionLevel user

!ifndef VERSION
  !error "pass -DVERSION=<engine commit>"
!endif
!ifndef SRC
  !error "pass -DSRC=<folder with the files to install>"
!endif
!ifndef OUTFILE
  !define OUTFILE "yog-setup-windows-x64.exe"
!endif

!define PRODUCT "YOG compiler (yogc)"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\YOG-yogc"
; PATH values longer than this cannot be read back whole by NSIS; we then leave PATH alone and say so (never truncate it)
!define /math PATH_LIMIT ${NSIS_MAX_STRLEN} - 200

Name "${PRODUCT}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\YOG"
BrandingText "YOG engine ${VERSION}"
VIProductVersion "0.1.0.0"
VIAddVersionKey "ProductName" "${PRODUCT}"
VIAddVersionKey "ProductVersion" "engine ${VERSION}"
VIAddVersionKey "FileDescription" "Installer for yogc, the YOG policy compiler"
VIAddVersionKey "FileVersion" "0.1.0.0"
VIAddVersionKey "LegalCopyright" "MIT License, YOG engine team"

!include "MUI2.nsh"
!include "StrFunc.nsh"
${StrStr}
${UnStrRep}

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\README.txt"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Show the quick start"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${SRC}\LICENSE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "yogc" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  File "${SRC}\yogc.exe"
  File "${SRC}\README.txt"
  File "${SRC}\LICENSE.txt"
  SetOutPath "$INSTDIR\examples"
  File "${SRC}\policy.yog"
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Start menu
  CreateDirectory "$SMPROGRAMS\YOG"
  CreateShortcut "$SMPROGRAMS\YOG\YOG command prompt.lnk" "$SYSDIR\cmd.exe" '/k cd /d "$INSTDIR\examples" && yogc' "$INSTDIR\yogc.exe"
  CreateShortcut "$SMPROGRAMS\YOG\Quick start.lnk" "$INSTDIR\README.txt"
  CreateShortcut "$SMPROGRAMS\YOG\Uninstall yogc.lnk" "$INSTDIR\uninstall.exe"

  ; "Installed apps" entry (per user)
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "${PRODUCT}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "engine ${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "YOG project"
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\yogc.exe"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize" 400

  ; Add $INSTDIR to the user's PATH (only if it is not there yet, and only if PATH can be read back whole)
  ReadRegStr $0 HKCU "Environment" "Path"
  StrLen $1 $0
  IntCmp $1 ${PATH_LIMIT} 0 path_ok 0
    DetailPrint "Your PATH is too long to change safely; add $INSTDIR to it yourself."
    MessageBox MB_ICONINFORMATION|MB_OK "Your PATH is too long for the installer to change safely.$\r$\nAdd this folder to it yourself:$\r$\n$INSTDIR" /SD IDOK
    Goto path_done
  path_ok:
  ${StrStr} $2 ";$0;" ";$INSTDIR;"
  StrCmp $2 "" 0 path_done
  StrCmp $0 "" 0 +3
    StrCpy $0 "$INSTDIR"
    Goto path_write
  StrCpy $0 "$0;$INSTDIR"
  path_write:
  WriteRegExpandStr HKCU "Environment" "Path" "$0"
  SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:Environment" /TIMEOUT=5000
  DetailPrint "Added $INSTDIR to your PATH (open a new terminal to use yogc)."
  path_done:
SectionEnd

Section "Uninstall"
  ; Remove $INSTDIR from the user's PATH (same length guard)
  ReadRegStr $0 HKCU "Environment" "Path"
  StrCmp $0 "" unpath_done
  StrLen $1 $0
  IntCmp $1 ${PATH_LIMIT} 0 unpath_ok 0
    DetailPrint "PATH too long to change safely; remove $INSTDIR from it yourself."
    Goto unpath_done
  unpath_ok:
  ${UnStrRep} $0 ";$0;" ";$INSTDIR;" ";"
  ; strip the separators added above
  StrCpy $2 $0 1
  StrCmp $2 ";" 0 +2
    StrCpy $0 $0 "" 1
  StrCpy $2 $0 1 -1
  StrCmp $2 ";" 0 +2
    StrCpy $0 $0 -1
  WriteRegExpandStr HKCU "Environment" "Path" "$0"
  SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:Environment" /TIMEOUT=5000
  unpath_done:

  Delete "$INSTDIR\yogc.exe"
  Delete "$INSTDIR\README.txt"
  Delete "$INSTDIR\LICENSE.txt"
  Delete "$INSTDIR\examples\policy.yog"
  RMDir "$INSTDIR\examples"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$SMPROGRAMS\YOG\YOG command prompt.lnk"
  Delete "$SMPROGRAMS\YOG\Quick start.lnk"
  Delete "$SMPROGRAMS\YOG\Uninstall yogc.lnk"
  RMDir "$SMPROGRAMS\YOG"
  DeleteRegKey HKCU "${UNINST_KEY}"
SectionEnd
