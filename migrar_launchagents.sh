#!/bin/bash
set -e

OLD_DIR="/Users/pallusmassucci/Desktop/provas-4a"
NEW_DIR="/Users/pallusmassucci/Desktop/provas-4a-site"
LAUNCH_DIR="/Users/pallusmassucci/Library/LaunchAgents"
SITE_PLIST="$LAUNCH_DIR/com.pallus.4a.site.plist"
WHATSAPP_PLIST="$LAUNCH_DIR/com.pallus.4a.whatsapp.plist"
TS="$(date +%Y%m%d_%H%M%S)"

cp "$SITE_PLIST" "$SITE_PLIST.backup_$TS"
cp "$WHATSAPP_PLIST" "$WHATSAPP_PLIST.backup_$TS"

perl -0pi -e "s#${OLD_DIR}#${NEW_DIR}#g" "$SITE_PLIST" "$WHATSAPP_PLIST"

launchctl unload "$SITE_PLIST" 2>/dev/null || true
launchctl unload "$WHATSAPP_PLIST" 2>/dev/null || true
launchctl load "$SITE_PLIST"
launchctl load "$WHATSAPP_PLIST"

echo "LaunchAgents migrados para $NEW_DIR"
grep -n "provas-4a" "$SITE_PLIST" "$WHATSAPP_PLIST"
