; Include required string functions
!include "StrFunc.nsh"
${StrRep}
${UnStrRep}


!macro NSIS_HOOK_POSTINSTALL
  ; Custom POSTINSTALL Hook - Add to PATH
  ; Read current PATH from Registry (Machine scope)
  ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path"
  
  ; Check if INSTDIR is already in PATH
  ${StrLoc} $1 $0 "$INSTDIR" ">"
  ${If} $1 == ""
      ; Not found, append it
      WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path" "$0;$INSTDIR"
      ; Broadcast change to all top-level windows
      SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:Environment" /TIMEOUT=5000
  ${EndIf}

  ; Move shims to root
  IfFileExists "$INSTDIR\resources\suzent.cmd" 0 +2
    Rename "$INSTDIR\resources\suzent.cmd" "$INSTDIR\suzent.cmd"
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; Custom POSTUNINSTALL Hook - Remove from PATH
  ; Read current PATH
  ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path"
  
  ; Remove INSTDIR from PATH (Simple string replacement)
  ${UnStrRep} $0 $0 ";$INSTDIR" "" 
  ${UnStrRep} $0 $0 "$INSTDIR;" "" 
  ${UnStrRep} $0 $0 "$INSTDIR" "" 
  
  ; Write back
  WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path" "$0"
  
  ; Broadcast change
  SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:Environment" /TIMEOUT=5000
!macroend
