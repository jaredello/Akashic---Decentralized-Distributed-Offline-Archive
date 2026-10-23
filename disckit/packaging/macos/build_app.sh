#!/bin/bash
# Builds dist/DiscKit.app and dist/DiscKit-macOS-arm64.dmg on a Mac (used by GitHub Actions).
set -euo pipefail
cd "$(dirname "$0")/../.."           # -> disckit/
KIT="$(pwd)"
HERE="$KIT/packaging/macos"
BUILD="$KIT/build"
VERSION=$(python3 -c "import re;print(re.search(r'__version__ = \"([^\"]+)\"', open('disckit/__init__.py').read()).group(1))")
ARCH=$(uname -m)
echo "Building DiscKit $VERSION for $ARCH"

rm -rf "$BUILD" dist
mkdir -p "$BUILD"
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt pyinstaller

# App icon: icon.png -> DiscKit.icns
ICONSET="$BUILD/DiscKit.iconset"
mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$HERE/icon.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s * 2)) $((s * 2)) "$HERE/icon.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$BUILD/DiscKit.icns"

python3 -m PyInstaller --noconfirm --clean --windowed \
  --name DiscKit \
  --icon "$BUILD/DiscKit.icns" \
  --osx-bundle-identifier org.disckit.app \
  --target-architecture "$ARCH" \
  --paths "$KIT" \
  --add-data "$KIT/disckit/reader/shell.html:disckit/reader" \
  --collect-all libzim \
  --collect-all zstandard \
  --hidden-import disckit.gui \
  --workpath "$BUILD/work" --specpath "$BUILD" \
  "$HERE/launcher.py"

APP="dist/DiscKit.app"
PLIST="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $VERSION" "$PLIST" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :NSHumanReadableCopyright string 'DiscKit — Text Disc + Media Disc archiver'" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 12.0" "$PLIST" 2>/dev/null || true

# Unsigned build: ad-hoc signature so Apple Silicon will launch it.
codesign --force --deep --sign - "$APP"

# Smoke test the frozen binary (CLI mode) before packaging.
"$APP/Contents/MacOS/DiscKit" --help >/dev/null

DMG_SRC="$BUILD/dmg"
mkdir -p "$DMG_SRC"
cp -R "$APP" "$DMG_SRC/"
ln -s /Applications "$DMG_SRC/Applications"
cp "$HERE/FIRST_LAUNCH.txt" "$DMG_SRC/Read me first.txt"
DMG="dist/DiscKit-$VERSION-macOS-$ARCH.dmg"
hdiutil create -volname "DiscKit $VERSION" -srcfolder "$DMG_SRC" -ov -format UDZO "$DMG"
shasum -a 256 "$DMG" | tee "$DMG.sha256"
echo "Built $DMG"
