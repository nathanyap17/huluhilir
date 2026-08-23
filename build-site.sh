#!/usr/bin/env bash
# Assembles the Firebase Hosting payload: the React landing page at the root,
# the Flutter web app under /app.
#
# They are built separately and staged into public_site/ rather than pointed
# at directly, because Firebase Hosting serves exactly one directory. Nothing
# here is committed -- public_site/ is generated, and both source trees stay
# independently buildable.
set -euo pipefail
cd "$(dirname "$0")"

API_URL="${API_BASE_URL:-https://huluhilir-api-mfrzixfqeq-as.a.run.app}"

echo "==> landing (React + anime.js)"
( cd landing && npm run build )

echo "==> flutter web  [API_BASE_URL=$API_URL]"
# base href is patched into the built index.html afterwards rather than
# passed as --base-href: Git Bash on Windows rewrites any argument that looks
# like a Unix path, turning /app/ into "C:/Program Files/Git/app/", and the
# resulting error names a value nobody typed. Editing the output is immune to
# that and behaves identically on every platform.
( cd flutter_app && flutter build web --release     --dart-define=API_BASE_URL="$API_URL" )

python -c "
import io, re, sys
p = 'flutter_app/build/web/index.html'
s = io.open(p, encoding='utf-8').read()
s = re.sub(r'<base href=\"[^\"]*\">', '<base href=\"/app/\">', s)
io.open(p, 'w', encoding='utf-8').write(s)
print('  base href -> /app/')
"

echo "==> staging public_site/"
rm -rf public_site
mkdir -p public_site
cp -r landing/dist/. public_site/
mkdir -p public_site/app
cp -r flutter_app/build/web/. public_site/app/

echo "Staged. Deploy with:"
echo "  npx firebase-tools deploy --only hosting --project sfws-aicc-workspace-1"
