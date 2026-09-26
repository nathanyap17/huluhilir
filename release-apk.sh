#!/usr/bin/env bash
# One-command Android release WITHOUT EAS (the free build quota is spent until
# 1 Oct 2026): build the cloud APK locally, sign it with the EAS keystore so it
# installs as an UPDATE over earlier builds, then refresh the landing page's
# download (fixed URL, so the QR code never changes) and publish.
#
#   ./release-apk.sh            # build + sign + stage site (no publish)
#   ./release-apk.sh --deploy   # ...and firebase deploy
#
# Needs: Android Studio (JDK + SDK build-tools), frontend-rn/credentials.json
# and frontend-rn/credentials/android/keystore.jks (from `eas credentials`,
# gitignored). Passwords travel in environment variables only -- never argv,
# never logs.
#
# Why C:/pdx/fe: Windows' 260-character path limit breaks the native (CMake)
# build from the repo's deep path; a short copy builds cleanly.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
FE="$ROOT/frontend-rn"
SHORT=/c/pdx/fe
OUT=/c/pdx/pepperdex-latest.apk
API_URL="${API_BASE_URL:-https://huluhilir-api-mfrzixfqeq-as.a.run.app}"
EXPECTED_CERT="0e85a8b56967b2fc46a1b8de8dae1fbb0bcda59dec0d5430bee6da11c22c1235"
export JAVA_HOME="${JAVA_HOME:-/c/Program Files/Android/Android Studio/jbr}"
export ANDROID_HOME="${ANDROID_HOME:-/c/Users/User/AppData/Local/Android/Sdk}"
BT="${ANDROID_BUILD_TOOLS:-/c/Users/User/AppData/Local/Android/Sdk/build-tools/36.1.0}"

echo "==> bump android.versionCode in app.json (each release must be newer)"
CODE=$(cd "$FE" && python - <<'EOF'
import json, io
p = "app.json"
d = json.load(io.open(p, encoding="utf-8"))
d["expo"]["android"]["versionCode"] += 1
io.open(p, "w", encoding="utf-8").write(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print(d["expo"]["android"]["versionCode"])
EOF
)
echo "  versionCode $CODE"

echo "==> sync frontend-rn -> $SHORT"
mkdir -p "$SHORT"
# /E, not /MIR: a mirror would purge the generated android/ folder there.
# robocopy exit codes below 8 mean success.
MSYS_NO_PATHCONV=1 robocopy "$(cygpath -w "$FE")" "$(cygpath -w "$SHORT")" /E /NFL /NDL /NJH /NJS /NP \
  /XD "$(cygpath -w "$FE/android")" "$(cygpath -w "$FE/credentials")" .expo \
  /XF credentials.json .env maps-api.key || [ $? -lt 8 ]

echo "==> Google Maps key (live walk map)"
# Never committed: read from the gitignored frontend-rn/maps-api.key, or the
# GOOGLE_MAPS_ANDROID_API_KEY environment variable. Without it the build
# still works; the walk just uses the fallback map. The key is restricted in
# Google Cloud to this package + signing certificate.
if [ -z "${GOOGLE_MAPS_ANDROID_API_KEY:-}" ] && [ -f "$FE/maps-api.key" ]; then
  GOOGLE_MAPS_ANDROID_API_KEY="$(tr -d '[:space:]' < "$FE/maps-api.key")"
fi
if [ -n "${GOOGLE_MAPS_ANDROID_API_KEY:-}" ]; then
  export GOOGLE_MAPS_ANDROID_API_KEY EXPO_PUBLIC_ENABLE_MAP=1
  echo "  Google map ON (key found, not printed)"
else
  echo "  no key: Google map OFF, fallback map used"
fi

echo "==> expo prebuild (android)"
( cd "$SHORT" && EXPO_PUBLIC_API_BASE_URL="$API_URL" npx expo prebuild --platform android --no-install >/dev/null )

echo "==> gradle assembleRelease  [API $API_URL]"
( cd "$SHORT/android" && EXPO_PUBLIC_API_BASE_URL="$API_URL" NODE_ENV=production \
    ./gradlew assembleRelease --no-daemon -PreactNativeArchitectures=armeabi-v7a,arm64-v8a -q )

echo "==> sign with the EAS keystore"
read -r KS ALIAS < <(cd "$FE" && python -c "import json;k=json.load(open('credentials.json'))['android']['keystore'];print(k['keystorePath'],k['keyAlias'])")
export KS_PASS KEY_PASS
KS_PASS=$(cd "$FE" && python -c "import json;print(json.load(open('credentials.json'))['android']['keystore']['keystorePassword'])")
KEY_PASS=$(cd "$FE" && python -c "import json;print(json.load(open('credentials.json'))['android']['keystore']['keyPassword'])")
cmd //c "$(cygpath -w "$BT/apksigner.bat")" sign \
  --ks "$(cygpath -w "$FE/$KS")" --ks-key-alias "$ALIAS" \
  --ks-pass env:KS_PASS --key-pass env:KEY_PASS \
  --out "$(cygpath -w "$OUT")" "$(cygpath -w "$SHORT/android/app/build/outputs/apk/release/app-release.apk")"
unset KS_PASS KEY_PASS

GOT=$(cmd //c "$(cygpath -w "$BT/apksigner.bat")" verify --print-certs "$(cygpath -w "$OUT")" \
  | grep -i "SHA-256 digest" | head -1 | awk '{print $NF}' | tr -d '\r')
[ "$GOT" = "$EXPECTED_CERT" ] || { echo "CERTIFICATE MISMATCH ($GOT) -- not publishing"; exit 1; }
echo "  signed $OUT, certificate matches EAS"

"$ROOT/build-site.sh" ${1:-} "$OUT"
