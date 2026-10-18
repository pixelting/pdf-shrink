#!/usr/bin/env bash
# Builds "PDF Shrink.app" and a .dmg on macOS.
# Usage: packaging/build_mac.sh [arch-label]   e.g. arm64 or intel
set -euo pipefail
cd "$(dirname "$0")/.."

ARCH_LABEL="${1:-$(uname -m)}"
APP_NAME="PDF Shrink"

# 1. icon: icon.png -> icon.icns
python packaging/make_icon.py
rm -rf packaging/icon.iconset && mkdir packaging/icon.iconset
for s in 16 32 64 128 256 512; do
  sips -z $s $s packaging/icon.png --out "packaging/icon.iconset/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2))
  sips -z $d $d packaging/icon.png --out "packaging/icon.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns packaging/icon.iconset -o packaging/icon.icns

# 2. the .app
rm -rf build dist
pyinstaller --noconfirm --windowed \
  --name "$APP_NAME" \
  --icon packaging/icon.icns \
  --osx-bundle-identifier com.pdfshrink.app \
  run_pdfshrink.py

# 3. ad-hoc sign (free; not the same as Apple notarization, see README)
codesign --force --deep --sign - "dist/${APP_NAME}.app"

# 4. the .dmg with an Applications shortcut
rm -rf dist/dmgroot && mkdir dist/dmgroot
cp -R "dist/${APP_NAME}.app" dist/dmgroot/
ln -s /Applications dist/dmgroot/Applications
DMG="dist/PDF-Shrink-${ARCH_LABEL}.dmg"
hdiutil create -volname "$APP_NAME" -srcfolder dist/dmgroot -ov -format UDZO "$DMG"
echo "Built $DMG"
