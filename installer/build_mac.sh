#!/usr/bin/env bash
set -euo pipefail

APP_NAME="CunningApp"
DIST_DIR="../dist"
DMG_NAME="${APP_NAME}.dmg"

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
