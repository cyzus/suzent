#!/usr/bin/env bash
set -euo pipefail
for name in IOS_CERTIFICATE_BASE64 IOS_CERTIFICATE_PASSWORD IOS_PROFILE_BASE64 APP_STORE_CONNECT_KEY_BASE64 APP_STORE_CONNECT_KEY_ID APP_STORE_CONNECT_ISSUER_ID APPLE_TEAM_ID; do
  [[ -n "${!name:-}" ]] || { echo "::error::Missing $name in mobile-release environment"; exit 1; }
done
sdk_version="$(xcrun --sdk iphoneos --show-sdk-version)"
[[ "${sdk_version%%.*}" -ge 26 ]] || { echo '::error::App Store uploads require iOS SDK 26 or newer'; exit 1; }
signing_dir="$(mktemp -d "$RUNNER_TEMP/suzent-signing.XXXXXX")"
keychain="$signing_dir/signing.keychain-db"
cleanup() {
  security delete-keychain "$keychain" >/dev/null 2>&1 || true
  if [[ -n "${profile_path:-}" ]]; then rm -f "$profile_path"; fi
  rm -rf "$signing_dir"
}
trap cleanup EXIT
export SIGNING_DIR="$signing_dir"
python3 - <<'PY'
import base64, os
from pathlib import Path
root = Path(os.environ['SIGNING_DIR'])
for key, name in [('IOS_CERTIFICATE_BASE64', 'certificate.p12'), ('IOS_PROFILE_BASE64', 'profile.mobileprovision'), ('APP_STORE_CONNECT_KEY_BASE64', 'AuthKey.p8')]:
    (root / name).write_bytes(base64.b64decode(os.environ[key], validate=True))
    (root / name).chmod(0o600)
PY
security cms -D -i "$signing_dir/profile.mobileprovision" > "$signing_dir/profile.plist"
profile_uuid="$(/usr/libexec/PlistBuddy -c 'Print UUID' "$signing_dir/profile.plist")"
export PROFILE_UUID="$profile_uuid"
python3 - <<'PY'
import os, plistlib
from pathlib import Path
root = Path(os.environ['SIGNING_DIR'])
p = plistlib.loads((root / 'profile.plist').read_bytes())
team = os.environ['APPLE_TEAM_ID']
if p['TeamIdentifier'][0] != team or p['Entitlements']['application-identifier'] != team + '.com.suzent.mobile':
    raise SystemExit('Provisioning profile must match the Apple team and com.suzent.mobile')
if p['Entitlements'].get('get-task-allow') or p.get('ProvisionedDevices') or p.get('ProvisionsAllDevices'):
    raise SystemExit('An App Store distribution profile is required')
options = {'method': 'app-store-connect', 'destination': 'upload', 'teamID': team,
           'signingStyle': 'manual', 'signingCertificate': 'Apple Distribution',
           'provisioningProfiles': {'com.suzent.mobile': p['UUID']},
           'manageAppVersionAndBuildNumber': False, 'uploadSymbols': True}
(root / 'ExportOptions.plist').write_bytes(plistlib.dumps(options))
PY
profile_path="$HOME/Library/MobileDevice/Provisioning Profiles/$profile_uuid.mobileprovision"
mkdir -p "$(dirname "$profile_path")"
cp "$signing_dir/profile.mobileprovision" "$profile_path"
keychain_password="$(openssl rand -hex 24)"
echo "::add-mask::$keychain_password"
security create-keychain -p "$keychain_password" "$keychain"
security set-keychain-settings -lut 21600 "$keychain"
security unlock-keychain -p "$keychain_password" "$keychain"
security import "$signing_dir/certificate.p12" -k "$keychain" -P "$IOS_CERTIFICATE_PASSWORD" -T /usr/bin/codesign -T /usr/bin/security
security set-key-partition-list -S apple-tool:,apple:,codesign: -k "$keychain_password" "$keychain" >/dev/null
security list-keychains -d user -s "$keychain" "$HOME/Library/Keychains/login.keychain-db"
xcodegen generate --spec apps/ios/project.yml
xcodebuild -project apps/ios/Suzent.xcodeproj -scheme Suzent -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$RUNNER_TEMP/Suzent.xcarchive" \
  DEVELOPMENT_TEAM="$APPLE_TEAM_ID" CODE_SIGN_STYLE=Manual CODE_SIGN_IDENTITY='Apple Distribution' \
  PROVISIONING_PROFILE_SPECIFIER="$profile_uuid" OTHER_CODE_SIGN_FLAGS="--keychain $keychain" archive
xcodebuild -exportArchive -archivePath "$RUNNER_TEMP/Suzent.xcarchive" \
  -exportPath "$RUNNER_TEMP/ios-export" -exportOptionsPlist "$signing_dir/ExportOptions.plist" \
  -authenticationKeyPath "$signing_dir/AuthKey.p8" -authenticationKeyID "$APP_STORE_CONNECT_KEY_ID" \
  -authenticationKeyIssuerID "$APP_STORE_CONNECT_ISSUER_ID" -allowProvisioningUpdates
