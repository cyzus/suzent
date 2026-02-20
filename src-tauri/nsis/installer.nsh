!macro customInstall
  EnVar::SetHKCU
  EnVar::Check "PATH" "$INSTDIR"
  Pop $0
  ${If} $0 = 0
    EnVar::AddValue "PATH" "$INSTDIR"
  ${EndIf}
!macroend
