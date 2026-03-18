#!/usr/bin/env bash
set -euo pipefail

APP_NAME="Input Monitor"
DIST_DIR="dist"
DMG_NAME="InputMonitor.dmg"
SIGN_IDENTITY="Apple Development: riku0684@icloud.com (LLRX3LZ4AZ)"
ENTITLEMENTS="installer/entitlements.plist"

echo "==> .app に署名します..."
codesign \
  --force \
  --deep \
  --sign "${SIGN_IDENTITY}" \
  --entitlements "${ENTITLEMENTS}" \
  --options runtime \
  "${DIST_DIR}/${APP_NAME}.app"

echo "==> 署名を検証します..."
codesign --verify --deep --strict "${DIST_DIR}/${APP_NAME}.app" && \
  echo "    [OK] 署名検証成功"

echo "==> .dmg を生成します..."

create-dmg \
  --volname "${APP_NAME}" \
  --window-size 540 380 \
  --icon-size 128 \
  --icon "${APP_NAME}.app" 130 160 \
  --app-drop-link 400 160 \
  "${DIST_DIR}/${DMG_NAME}" \
  "${DIST_DIR}/${APP_NAME}.app"

echo "==> 完了: ${DIST_DIR}/${DMG_NAME}"
