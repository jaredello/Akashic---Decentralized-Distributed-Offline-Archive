#!/bin/bash
# Developer ID signing + Apple notarization helpers, sourced by build_app.sh.
# Enabled only when all five secrets below are present (see SIGNING.md):
#   MACOS_CERT_P12_BASE64  MACOS_CERT_PASSWORD
#   ASC_API_KEY_P8_BASE64  ASC_API_KEY_ID  ASC_API_ISSUER_ID

ENTITLEMENTS="$HERE/entitlements.plist"
IDENTITY=""

signing_enabled() {
  [ -n "${MACOS_CERT_P12_BASE64:-}" ] && [ -n "${MACOS_CERT_PASSWORD:-}" ] &&
  [ -n "${ASC_API_KEY_P8_BASE64:-}" ] && [ -n "${ASC_API_KEY_ID:-}" ] && [ -n "${ASC_API_ISSUER_ID:-}" ]
}

cleanup_signing() {
  [ -n "${KEYCHAIN:-}" ] && security delete-keychain "$KEYCHAIN" 2>/dev/null || true
  rm -f "$BUILD/cert.p12" "$BUILD/AuthKey.p8"
}

setup_keychain() {
  trap cleanup_signing EXIT
  KEYCHAIN="$BUILD/disckit-signing.keychain-db"
  local kpw
  kpw=$(uuidgen)
  security create-keychain -p "$kpw" "$KEYCHAIN"
  security set-keychain-settings -lut 21600 "$KEYCHAIN"
  security unlock-keychain -p "$kpw" "$KEYCHAIN"
  echo "$MACOS_CERT_P12_BASE64" | base64 --decode > "$BUILD/cert.p12"
  security import "$BUILD/cert.p12" -k "$KEYCHAIN" -P "$MACOS_CERT_PASSWORD" \
    -T /usr/bin/codesign -T /usr/bin/security
  security set-key-partition-list -S apple-tool:,apple: -s -k "$kpw" "$KEYCHAIN" >/dev/null
  # shellcheck disable=SC2046
  security list-keychains -d user -s "$KEYCHAIN" $(security list-keychains -d user | tr -d '"')
  IDENTITY=$(security find-identity -v -p codesigning "$KEYCHAIN" \
    | grep "Developer ID Application" | head -1 | sed -E 's/.*"(.*)"/\1/')
  if [ -z "$IDENTITY" ]; then
    echo "::error::No 'Developer ID Application' certificate found in MACOS_CERT_P12_BASE64."
    exit 1
  fi
  echo "Signing as: $IDENTITY"
  echo "$ASC_API_KEY_P8_BASE64" | base64 --decode > "$BUILD/AuthKey.p8"
}

sign_app() {
  local app="$1"
  # Sign every Mach-O binary inside the bundle first (innermost first), then the bundle itself.
  while IFS= read -r -d '' f; do
    if file -b "$f" | grep -q "Mach-O"; then
      codesign --force --timestamp --options runtime --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" "$f"
    fi
  done < <(find "$app/Contents" -type f -print0 | sort -rz)
  while IFS= read -r -d '' fw; do
    codesign --force --timestamp --options runtime --sign "$IDENTITY" "$fw"
  done < <(find "$app/Contents" -type d -name "*.framework" -print0 | sort -rz)
  codesign --force --timestamp --options runtime --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" "$app"
  codesign --verify --deep --strict --verbose=2 "$app"
}

notarize() {
  # Submit to Apple, wait for approval, then staple the ticket so it also works offline.
  local target="$1" upload="$1" out id status
  if [ -d "$target" ]; then
    upload="$BUILD/$(basename "$target").zip"
    ditto -c -k --keepParent "$target" "$upload"
  fi
  out=$(xcrun notarytool submit "$upload" --key "$BUILD/AuthKey.p8" --key-id "$ASC_API_KEY_ID" \
    --issuer "$ASC_API_ISSUER_ID" --wait --timeout 45m --output-format json)
  echo "$out"
  id=$(echo "$out" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))")
  status=$(echo "$out" | python3 -c "import sys,json;print(json.load(sys.stdin).get('status',''))")
  if [ "$status" != "Accepted" ]; then
    echo "::error::Apple notarization returned '$status'. Apple's log follows:"
    [ -n "$id" ] && xcrun notarytool log "$id" --key "$BUILD/AuthKey.p8" --key-id "$ASC_API_KEY_ID" \
      --issuer "$ASC_API_ISSUER_ID" || true
    exit 1
  fi
  xcrun stapler staple "$target"
  xcrun stapler validate "$target"
  if [ -d "$target" ]; then
    spctl --assess --type execute -vv "$target"
  fi
}
