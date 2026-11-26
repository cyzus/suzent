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

; Used by scripts/patch-nsis.mjs in place of the template's copy out of the
; temp folder: move each unpacked top-level entry into the install folder, and
; copy only what cannot be moved (another drive, or a name already there).
; Leaves the error flag set when a copy fails, as the copy it replaces did.
!macro suzentMoveExtracted
  Push $R2
  Push $R3
  Push $R4
  StrCpy $R4 ""
  ClearErrors
  FindFirst $R2 $R3 "$PLUGINSDIR\7z-out\*"
  suzentMoveNext:
    StrCmp $R3 "" suzentMoveDone
    StrCmp $R3 "." suzentMoveFind
    StrCmp $R3 ".." suzentMoveFind
    ClearErrors
    Rename "$PLUGINSDIR\7z-out\$R3" "$OUTDIR\$R3"
    IfErrors 0 suzentMoveFind
    ClearErrors
    CopyFiles /SILENT "$PLUGINSDIR\7z-out\$R3" $OUTDIR
    IfErrors 0 suzentMoveFind
    StrCpy $R4 "failed"
  suzentMoveFind:
    ClearErrors
    FindNext $R2 $R3
    IfErrors 0 suzentMoveNext
  suzentMoveDone:
  FindClose $R2
  ClearErrors
  StrCmp $R4 "" +2
    SetErrors
  Pop $R4
  Pop $R3
  Pop $R2
!macroend
