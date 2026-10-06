#!/bin/sh
# Builds dist/Devkit.app (menu bar app + bundled devkit server) and optionally dist/Devkit.dmg.
#
#   app/build.sh                 build and sign the app
#   app/build.sh --dmg           also create a disk image
#
# Signing: DEVKIT_SIGN_IDENTITY selects a codesigning identity. Without it, the first "Developer ID Application"
# identity in the keychain is used, else the first "Apple Development" one, else an ad-hoc signature. With an ad-hoc
# signature macOS forgets privacy permissions (screen recording) after every rebuild.
# DEVKIT_BUNDLE_ID overrides the bundle identifier.
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
DIST="$ROOT/dist"
APP="$DIST/Devkit.app"
BUNDLE_ID="${DEVKIT_BUNDLE_ID:-io.github.rennerdo30.devkit}"
VERSION="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' "$ROOT/bin/devkit-server")"
BUILD="$(git -C "$ROOT" rev-list --count HEAD 2>/dev/null || echo 1)"

echo "==> building Devkit $VERSION ($BUILD)"
swift build --package-path "$HERE" -c release
BIN="$(swift build --package-path "$HERE" -c release --show-bin-path)/Devkit"

echo "==> assembling $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/devkit"
cp "$BIN" "$APP/Contents/MacOS/Devkit"
cp "$HERE/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
for d in bin lib web; do
  rsync -a --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' "$ROOT/$d" "$APP/Contents/Resources/devkit/"
done
sed -e "s|@BUNDLE_ID@|$BUNDLE_ID|" -e "s|@VERSION@|$VERSION|" -e "s|@BUILD@|$BUILD|" "$HERE/Info.plist.in" > "$APP/Contents/Info.plist"
plutil -lint -s "$APP/Contents/Info.plist"

IDENTITY="${DEVKIT_SIGN_IDENTITY:-}"
if [ -z "$IDENTITY" ]; then
  IDS="$(security find-identity -v -p codesigning 2>/dev/null || true)"
  IDENTITY="$(printf '%s\n' "$IDS" | sed -n 's/.*"\(Developer ID Application:[^"]*\)".*/\1/p' | head -1)"
  [ -n "$IDENTITY" ] || IDENTITY="$(printf '%s\n' "$IDS" | sed -n 's/.*"\(Apple Development:[^"]*\)".*/\1/p' | head -1)"
  [ -n "$IDENTITY" ] || IDENTITY="-"
fi
echo "==> signing with ${IDENTITY%% (*}"
if [ "$IDENTITY" = "-" ]; then
  codesign --force --sign - "$APP"
else
  case "$IDENTITY" in Developer\ ID*) TS="--timestamp" ;; *) TS="" ;; esac
  codesign --force --options runtime $TS --sign "$IDENTITY" "$APP"
fi
codesign --verify --strict "$APP"

if [ "${1:-}" = "--dmg" ]; then
  echo "==> creating Devkit.dmg"
  STAGE="$(mktemp -d)"
  cp -R "$APP" "$STAGE/"
  ln -s /Applications "$STAGE/Applications"
  hdiutil create -quiet -volname Devkit -srcfolder "$STAGE" -ov -format UDZO "$DIST/Devkit.dmg"
  rm -rf "$STAGE"
  echo "    $DIST/Devkit.dmg"
fi
echo "==> done: $APP"
