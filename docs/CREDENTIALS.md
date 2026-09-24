# CREDENTIALS.md — Hosting, Environment Variables & Deployment URLs

> **This file is a template and reference — it never contains real secret values.** Real values live only in your actual `.env` file, which is `.gitignore`'d and never committed. Anywhere this file shows a placeholder like `<YOUR_KEY>`, that's intentional — fill it in locally, never here.

---

## 1 · Deployment URL stability — read this before your first deploy

**Once you deploy, the URL does not change on future redeploys.** Cloud Run and Firebase Hosting both bind a stable URL to the *service* (name + project + region) — not to any individual deployment. Every `gcloud run deploy` afterward pushes a new revision under the same URL; traffic switches over automatically, with zero reconfiguration needed downstream.

**Capture the URL once, right after the first deploy — not every time.**

```bash
# After the FIRST deploy only:
gcloud run services describe huluhilir-api --project sfws-aicc-workspace-1 --region asia-southeast1 --format='value(status.url)'
# → paste this into §3 below, and into every place listed in §4
```

**The URL only changes if you:**
1. Rename the Cloud Run service (`huluhilir-api` → anything else, including `pepperdex-api`)
2. Change project or region (`sfws-aicc-workspace-1` / `asia-southeast1`)

> **Cloud identifiers keep the v1 name on purpose** (owner decision 2026-09-24): Cloud Run service `huluhilir-api`, GCP/Firebase project `sfws-aicc-workspace-1`, region `asia-southeast1`, Cloud SQL `huluhilir-db`, secret `huluhilir-db-url`, bucket `huluhilir-media`, local DB `huluhilir.db`, repo `nathanyap17/huluhilir`. Renaming any of them creates a new service/URL. Deploy with `./deploy-cloud.sh`, which already uses these.
3. Delete and recreate the service, rather than redeploying it

**Avoid all three unless intentional.** Ordinary code changes + redeploy never trigger a new URL.

---

## 2 · Consolidated `.env` template

**No single file listed every required variable before this one did** — they were scattered across `CLAUDE.md`, `PLAN.md`, `WORKSPACE_SETUP.md`, and `VALIDATION_CHECKLIST.md`. This is the one place to check before either deploying or handing this project to a fresh session.

```bash
# .env  — copy this block, fill in real values, NEVER commit the result

# Switches local ↔ cloud with no code change — see PROJECT_SPEC.md §8
API_BASE_URL=http://<LAPTOP_LAN_IP>:8000        # local
# API_BASE_URL=<CLOUD_RUN_URL_FROM_SECTION_1>   # cloud — uncomment once deployed

LITELLM_MODEL=ollama_chat/qwen2.5:14b           # local -- gemma2:9b does NOT support tool calling at all
# LITELLM_MODEL=gemini/gemini-2.0-flash         # cloud — uncomment once deployed

DATABASE_URL=sqlite+aiosqlite:///./pepperdex.db # local
# DATABASE_URL=postgresql+asyncpg://<CLOUD_SQL_CONNECTION>  # cloud, if migrated

AGENT_TIMEOUT_S=180                             # max seconds for one agent LLM turn before the rules-table fallback takes over

GEMINI_API_KEY=<YOUR_KEY>                       # only required for the cloud LLM path
```

**Where this file physically lives:** `pepperdex/backend/.env`, listed in `.gitignore`. This `CREDENTIALS.md` is committed; your actual `.env` never is.

---

## 3 · Deployed URLs — fill in once, per environment

| Environment | URL | Captured on |
|---|---|---|
| Cloud Run (backend API) | *(paste after first deploy — §1)* | |
| Firebase Hosting (landing page) | **`https://sfws-aicc-workspace-1.web.app/`** — FIXED; this is the address printed as the bunting QR (see `PLAN.md` § HOLD). Never change it | 2026-09-20 |
| Firebase Storage (APK, assets bucket) | *(paste bucket path after first upload)* | |

---

## 4 · Post-deploy checklist — where the URL needs to actually go

Capturing the URL in §3 isn't the end of the task — it needs to be **used** in four places, or a `.env`-only update leaves other things silently pointing at nothing:

- [ ] `.env` → `API_BASE_URL` (backend, §2 above)
- [ ] `frontend-rn/.env` → `EXPO_PUBLIC_API_BASE_URL` (see `frontend-rn/.env.example`) — Expo only bakes client-visible vars into the bundle when prefixed `EXPO_PUBLIC_`, so the backend's own `API_BASE_URL` name doesn't work unprefixed here. An `eas build --profile cloud` variant is Phase D work — no `eas.json` exists yet.
- [ ] Landing page's "try it" link → Firebase Hosting URL from §3
- [ ] Pitch deck / demo materials, if they reference a live link

---

## 5 · GCP authentication — beyond the Gemini API key

The API key in §2 covers Gemini calls. **Deploying to Cloud Run and Firebase needs separate authentication**, previously undocumented anywhere in this project.

**Recommended for this project's scale — Application Default Credentials (ADC), not a service account key file:**

```bash
gcloud auth login                              # your own Google account
gcloud auth application-default login           # ADC — ties deploy auth to your login session
```

**Why ADC over a service account JSON key:** no separate credential file to manage, gitignore, or accidentally leak — auth is tied to your own `gcloud` session and expires/refreshes normally. A service account key is a downloadable file that behaves exactly like a password with no expiry; only introduce one if a future CI/CD pipeline genuinely requires non-interactive deploys.

**If a service account key is ever created later:** treat it with the same discipline as everything else here — store its path in `GOOGLE_APPLICATION_CREDENTIALS`, `.gitignore` the actual `.json` file, never paste its contents into any `.md`.

---

## 6 · What this file deliberately does not cover

Team access and credential-sharing across members — out of scope for this project by decision, not omission.

---

## 7 · Shipping the app to judges (APK) — decided 2026-09-19 · ⏸ ON HOLD until the owner verifies local testing (see `PLAN.md` § HOLD)

Expo Go can't run this app (maps/3D/calendar need native modules) and needs a laptop running Metro, so judges get a **standalone APK** that talks to Cloud Run over HTTPS. Firebase Hosting/Storage only holds the download link/file; Cloud Run only hosts the API.

1. Deploy the backend (§1), capture the Cloud Run URL, put it in `frontend-rn/eas.json` → `build.cloud.env.EXPO_PUBLIC_API_BASE_URL` (replace the `REPLACE_WITH_CLOUD_RUN_URL` placeholder — the build is meant to look obviously broken if you forget). The URL is baked in at build time; changing it means a new APK.
2. Build: `cd frontend-rn && eas build --profile cloud --platform android` (cloud build, free tier has monthly limits — check current numbers on expo.dev/pricing), **or** with no EAS account/billing at all: `eas build --profile cloud --platform android --local` / `npx expo prebuild` + Gradle on a machine with the Android SDK.
3. Host the resulting `.apk` (Firebase Hosting `public_site/` or Storage) and link it from the landing page. Judges: open link on the phone → allow "install unknown apps" for the browser → install.
4. `production` profile builds an `.aab` (Play Store format) — it **cannot** be sideloaded; use `cloud` for judges.

Backend-only changes after this need only a Cloud Run redeploy. Any screen/JS change needs a new APK (or EAS Update).
