; Puts the `suzent` command (resources\bin\suzent.cmd) on the user's PATH.
; Per-user install, so the per-user PATH: no administrator prompt.
!include "StrFunc.nsh"
!include "WinMessages.nsh"
; electron-builder compiles the uninstaller in its own pass; declare each
; helper only in the pass that uses it, since unused functions are errors.
!ifdef BUILD_UNINSTALLER
  ${UnStrRep}
!else
  ${StrLoc}
!endif

!macro customInstall
  ReadRegStr $0 HKCU "Environment" "Path"
  ${StrLoc} $1 "$0" "$INSTDIR\resources\bin" ">"
  ${If} $1 == ""
    ${If} $0 == ""
      WriteRegExpandStr HKCU "Environment" "Path" "$INSTDIR\resources\bin"
    ${Else}
      WriteRegExpandStr HKCU "Environment" "Path" "$0;$INSTDIR\resources\bin"
    ${EndIf}
    SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:Environment" /TIMEOUT=5000
  ${EndIf}
!macroend

!macro customUnInstall
  ; An update reinstalls over the old copy; keep PATH as it is then.
  ${IfNot} ${isUpdated}
    ReadRegStr $0 HKCU "Environment" "Path"
    ${UnStrRep} $0 "$0" ";$INSTDIR\resources\bin" ""
    ${UnStrRep} $0 "$0" "$INSTDIR\resources\bin;" ""
    ${UnStrRep} $0 "$0" "$INSTDIR\resources\bin" ""
    WriteRegExpandStr HKCU "Environment" "Path" "$0"
    SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:Environment" /TIMEOUT=5000
  ${EndIf}
!macroend
