#!/usr/bin/env bash
# Sign the raw desktop assets that setup.sh downloads, then notarize them together.
# With MACOS_INSTALLER_APP, MACOS_INSTALLER_BINARY and MACOS_INSTALLER_DMG set, also
# wrap the installer app in a disk image that is notarized and stapled for Finder.
set -euo pipefail

for name in MACOS_CERTIFICATE_BASE64 MACOS_CERTIFICATE_PASSWORD MACOS_SIGNING_IDENTITY APP_STORE_CONNECT_KEY_BASE64 APP_STORE_CONNECT_KEY_ID APP_STORE_CONNECT_ISSUER_ID; do
  [[ -n "${!name:-}" ]] || { echo "::error::Missing $name for macOS release signing"; exit 1; }
done
[[ "$MACOS_SIGNING_IDENTITY" == "Developer ID Application: "* ]] || {
  echo '::error::A Developer ID Application signing identity is required'
  exit 1
}
[[ "$#" -gt 0 ]] || { echo 'Usage: sign-macos-release.sh executable ...' >&2; exit 1; }
for binary in "$@"; do
  [[ -f "$binary" ]] || { echo "::error::Missing executable: $binary"; exit 1; }
done
installer_dmg="${MACOS_INSTALLER_DMG:-}"
if [[ -n "${MACOS_INSTALLER_APP:-}${MACOS_INSTALLER_BINARY:-}$installer_dmg" ]]; then
  for name in MACOS_INSTALLER_APP MACOS_INSTALLER_BINARY MACOS_INSTALLER_DMG; do
    [[ -n "${!name:-}" ]] || { echo "::error::Missing $name for the macOS installer disk image"; exit 1; }
  done
  [[ -d "$MACOS_INSTALLER_APP/Contents/MacOS" ]] || {
    echo "::error::Missing installer app bundle: $MACOS_INSTALLER_APP"
    exit 1
  }
  # The embedded updater must be the same signed bytes that are published standalone.
  printf '%s\n' "$@" | grep -Fqx -- "$MACOS_INSTALLER_BINARY" || {
    echo '::error::MACOS_INSTALLER_BINARY must be one of the executables being signed'
    exit 1
  }
fi

signing_dir="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/suzent-macos-signing.XXXXXX")"
keychain="$signing_dir/signing.keychain-db"
security list-keychains -d user > "$signing_dir/keychains.txt"
cleanup() {
  # Restore the runner's search list before deleting the temporary keychain.
  python3 - "$signing_dir/keychains.txt" <<'PY'
import shlex
import subprocess
import sys
from pathlib import Path
subprocess.run(["security", "list-keychains", "-d", "user", "-s",
                *shlex.split(Path(sys.argv[1]).read_text())], check=False)
PY
  security delete-keychain "$keychain" >/dev/null 2>&1 || true
  rm -rf "$signing_dir"
}
trap cleanup EXIT
export SIGNING_DIR="$signing_dir"
python3 - <<'PY'
import base64
import os
from pathlib import Path
path = Path(os.environ['SIGNING_DIR']) / 'certificate.p12'
path.write_bytes(base64.b64decode(os.environ['MACOS_CERTIFICATE_BASE64'], validate=True))
path.chmod(0o600)
key = Path(os.environ['SIGNING_DIR']) / 'AuthKey.p8'
key.write_bytes(base64.b64decode(os.environ['APP_STORE_CONNECT_KEY_BASE64'], validate=True))
key.chmod(0o600)
PY
keychain_password="$(openssl rand -hex 24)"
echo "::add-mask::$keychain_password"
security create-keychain -p "$keychain_password" "$keychain"
security set-keychain-settings -lut 21600 "$keychain"
security unlock-keychain -p "$keychain_password" "$keychain"
security import "$signing_dir/certificate.p12" -k "$keychain" \
  -P "$MACOS_CERTIFICATE_PASSWORD" -T /usr/bin/codesign -T /usr/bin/security
security set-key-partition-list -S apple-tool:,apple:,codesign: -k "$keychain_password" "$keychain" >/dev/null
python3 - "$signing_dir/keychains.txt" "$keychain" <<'PY'
import shlex
import subprocess
import sys
from pathlib import Path
subprocess.run(["security", "list-keychains", "-d", "user", "-s", sys.argv[2],
                *shlex.split(Path(sys.argv[1]).read_text())], check=True)
PY
mkdir "$signing_dir/assets"
for binary in "$@"; do
  codesign --force --timestamp --options runtime --keychain "$keychain" \
    --sign "$MACOS_SIGNING_IDENTITY" "$binary"
  codesign --verify --strict --verbose=2 "$binary"
  cp "$binary" "$signing_dir/assets/$(basename "$binary")"
done
if [[ -n "$installer_dmg" ]]; then
  app_name="$(basename "$MACOS_INSTALLER_APP")"
  mkdir "$signing_dir/dmg"
  ditto "$MACOS_INSTALLER_APP" "$signing_dir/dmg/$app_name"
  # The installer stages this copy as ~/.suzent/updater/suzent-installer: a main
  # executable copied out of Contents/MacOS fails verification without its bundle.
  mkdir -p "$signing_dir/dmg/$app_name/Contents/Helpers"
  ditto "$MACOS_INSTALLER_BINARY" "$signing_dir/dmg/$app_name/Contents/Helpers/suzent-installer"
  codesign --force --timestamp --options runtime --keychain "$keychain" \
    --sign "$MACOS_SIGNING_IDENTITY" "$signing_dir/dmg/$app_name"
  codesign --verify --deep --strict --verbose=2 "$signing_dir/dmg/$app_name"
  ln -s /Applications "$signing_dir/dmg/Applications"
  rm -f "$installer_dmg"
  hdiutil create -volname "${app_name%.app}" -srcfolder "$signing_dir/dmg" \
    -fs HFS+ -format UDZO -ov "$installer_dmg"
  codesign --force --timestamp --keychain "$keychain" --sign "$MACOS_SIGNING_IDENTITY" "$installer_dmg"
  codesign --verify --strict --verbose=2 "$installer_dmg"
fi
# Preserve the exact signed bytes before waiting: a timeout does not cancel Apple's scan.
if [[ -n "${MACOS_SIGNED_ARCHIVE:-}" ]]; then
  if [[ -n "$installer_dmg" ]]; then
    cp "$installer_dmg" "$signing_dir/$(basename "$installer_dmg")"
    tar -czf "$MACOS_SIGNED_ARCHIVE" -C "$signing_dir/assets" . \
      -C "$signing_dir" "$(basename "$installer_dmg")"
  else
    tar -czf "$MACOS_SIGNED_ARCHIVE" -C "$signing_dir/assets" .
  fi
fi
ditto -c -k "$signing_dir/assets" "$signing_dir/assets.zip"
notarize() {
  xcrun notarytool submit "$1" \
    --key "$signing_dir/AuthKey.p8" --key-id "$APP_STORE_CONNECT_KEY_ID" --issuer "$APP_STORE_CONNECT_ISSUER_ID" \
    --wait --timeout 30m --output-format json > "$2"
}
# Submit together so the disk image does not queue behind the executables.
notarize "$signing_dir/assets.zip" "$signing_dir/result-assets.json" &
submissions=("$!")
if [[ -n "$installer_dmg" ]]; then
  notarize "$installer_dmg" "$signing_dir/result-dmg.json" &
  submissions+=("$!")
fi
submit_failed=0
for submission in "${submissions[@]}"; do
  wait "$submission" || submit_failed=1
done
python3 - "$signing_dir"/result-*.json <<'PY'
import json
import sys
from pathlib import Path
failed = []
for path in sys.argv[1:]:
    text = Path(path).read_text()
    result = json.loads(text) if text.strip() else {}
    print(f"Notarization: {result.get('status')} (submission {result.get('id')})")
    if result.get('status') != 'Accepted':
        failed.append(f"{result.get('status')} (submission {result.get('id')})")
if failed:
    raise SystemExit("Notarization failed: " + ", ".join(failed))
PY
[[ "$submit_failed" == 0 ]] || { echo '::error::notarytool submission failed'; exit 1; }
# Mach-O files cannot carry a stapled ticket; Gatekeeper retrieves it online.
for binary in "$@"; do
  codesign --verify --strict --verbose=4 -R="notarized" --check-notarization "$binary"
done
if [[ -n "$installer_dmg" ]]; then
  xcrun stapler staple "$installer_dmg"
  xcrun stapler validate "$installer_dmg"
  spctl --assess --type open --context context:primary-signature --verbose=2 "$installer_dmg"
  mount_point="$signing_dir/mount"
  mkdir "$mount_point"
  hdiutil attach -nobrowse -readonly -noautoopen -mountpoint "$mount_point" "$installer_dmg"
  verify_status=0
  {
    spctl --assess --type execute --verbose=2 "$mount_point/$app_name" &&
      codesign --verify --strict --verbose=4 -R="notarized" --check-notarization \
        "$mount_point/$app_name/Contents/Helpers/suzent-installer"
  } || verify_status=$?
  hdiutil detach "$mount_point"
  [[ "$verify_status" == 0 ]] || { echo '::error::Gatekeeper rejected the installer app'; exit 1; }
fi
