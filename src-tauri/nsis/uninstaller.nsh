!macro customUninstall
  IfFileExists "$INSTDIR\SUZENT.exe" 0 +2
    nsExec::ExecToLog '"$INSTDIR\SUZENT.exe" service uninstall'
  EnVar::SetHKCU
  EnVar::DeleteValue "PATH" "$INSTDIR"
!macroend
