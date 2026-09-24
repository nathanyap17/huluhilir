#!/usr/bin/env bash
# Assembles the Firebase Hosting payload in public_site/: the PepperDex landing
# page, plus the latest signed Android APK under a FIXED name, so the QR code
# on the page and on the bunting never changes.
#
#   ./build-site.sh [path/to/signed.apk]      # default: $APK or C:/pdx/pepperdex-latest.apk
#   ./build-site.sh --deploy [path]           # ...and publish (needs `firebase login`)
#
# public_site/ is generated and never committed. The v1 Flutter web app that
# used to live under /app is gone on purpose: v2 is Android-only.
set -euo pipefail
cd "$(dirname "$0")"

DEPLOY=0
if [ "${1:-}" = "--deploy" ]; then DEPLOY=1; shift; fi
APK_SRC="${1:-${APK:-/c/pdx/pepperdex-latest.apk}}"
PROJECT=sfws-aicc-workspace-1

echo "==> landing (React + anime.js)"
( cd landing && npm run build )

echo "==> staging public_site/"
rm -rf public_site
mkdir -p public_site
cp -r landing/dist/. public_site/

if [ -f "$APK_SRC" ]; then
  cp "$APK_SRC" public_site/pepperdex-latest.apk
  # Version facts come from the APK itself, not from anything typed by hand.
  BT="${ANDROID_BUILD_TOOLS:-/c/Users/User/AppData/Local/Android/Sdk/build-tools/36.1.0}"
  BADGE=$("$BT/aapt2.exe" dump badging "$APK_SRC" 2>/dev/null | head -1 || true)
  python - "$APK_SRC" "$BADGE" > public_site/version.json <<'EOF'
import json, os, re, sys, datetime
apk, badge = sys.argv[1], sys.argv[2]
code = re.search(r"versionCode='(\d+)'", badge)
name = re.search(r"versionName='([^']+)'", badge)
built = datetime.datetime.fromtimestamp(os.path.getmtime(apk), datetime.timezone(datetime.timedelta(hours=8)))
print(json.dumps({
    "versionCode": int(code.group(1)) if code else None,
    "versionName": name.group(1) if name else None,
    "builtAt": built.isoformat(timespec="minutes"),
    "sizeMB": round(os.path.getsize(apk) / 1e6),
}))
EOF
  echo "  APK:  $(cat public_site/version.json)"
else
  echo "  WARNING: no APK at $APK_SRC -- the Download button will 404 until one is staged."
fi

if [ "$DEPLOY" = 1 ]; then
  echo "==> firebase deploy (project $PROJECT)"
  npx firebase-tools deploy --only hosting --project "$PROJECT"
else
  echo "Staged. Deploy with:  ./build-site.sh --deploy   (or: npx firebase-tools deploy --only hosting --project $PROJECT)"
fi
