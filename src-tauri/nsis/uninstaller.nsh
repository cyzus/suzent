!macro customUninstall
  EnVar::SetHKCU
  EnVar::DeleteValue "PATH" "$INSTDIR"
!macroend
