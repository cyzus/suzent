#!/usr/bin/env bash
# Sign the raw desktop assets that setup.sh downloads, then notarize them together.
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
ditto -c -k "$signing_dir/assets" "$signing_dir/assets.zip"
xcrun notarytool submit "$signing_dir/assets.zip" \
  --key "$signing_dir/AuthKey.p8" --key-id "$APP_STORE_CONNECT_KEY_ID" --issuer "$APP_STORE_CONNECT_ISSUER_ID" \
  --wait --timeout 30m --output-format json > "$signing_dir/result.json"
python3 - "$signing_dir/result.json" <<'PY'
import json
import sys
from pathlib import Path
result = json.loads(Path(sys.argv[1]).read_text())
print(f"Notarization: {result.get('status')} (submission {result.get('id')})")
if result.get('status') != 'Accepted':
    raise SystemExit(f"Notarization failed: {result.get('status')} (submission {result.get('id')})")
PY
# Mach-O files cannot carry a stapled ticket; Gatekeeper retrieves it online.
for binary in "$@"; do
  spctl --assess --type execute --verbose=2 "$binary"
done
