# Deploying Mars (mars-academic / mars-finance / mars-hr) to Railway

This covers what's actually needed to get the 3 Mars gateways running on Railway as one
service, based on how the official image (`Dockerfile`) and its s6-overlay supervision
(`docker/`) actually work — not a generic Railway tutorial.

## What's already fixed in this repo

- **`Dockerfile.railway`** — identical to `Dockerfile`, minus the `VOLUME [ "/opt/data" ]`
  instruction. Railway's build validator rejects any Dockerfile containing `VOLUME` outright;
  persistence is provided by a Railway Volume instead (see step 2).
- **`railway.json`** — points Railway's builder at `Dockerfile.railway`.
- **`docker-compose.yml` is NOT used for this deploy.** It uses `network_mode: host`, which
  Railway doesn't support (no host-networking mode — Railway gives each service its own
  network namespace + a public domain). Not a real problem here: Telegram gateways poll
  outbound, they don't need an inbound port, so Railway's default networking is fine. Deploy
  the Dockerfile directly, not via compose.
- **Multi-profile supervision needs no extra config.** The image's `02-reconcile-profiles`
  init hook (`docker/cont-init.d/02-reconcile-profiles`) scans `$HERMES_HOME/profiles/<name>/`
  at container start and creates a supervised s6 service per profile it finds. Put all three
  Mars profile folders on the volume and the container starts all three gateways automatically
  — no CMD override, no per-profile container needed.

## Manual steps (can't be done from this repo — do these in the Railway dashboard)

### 1. Create the service
New service → Deploy from this repo (or a registry image built from `Dockerfile.railway`) →
confirm Railway picks up `railway.json`'s `dockerfilePath`.

### 2. Attach a persistent Volume
Settings → Volumes → add a volume, mount path **`/opt/data`**. This is `$HERMES_HOME` inside
the container (`ENV HERMES_HOME=/opt/data`, `Dockerfile:391`) — everything writable (profiles,
vault, state.db) has to live under here or it's wiped on every redeploy (confirmed: Railway
volumes are not available at build time, only mounted at runtime).

### 3. Get the existing Mars data onto the volume
The live Mars profiles currently exist locally at `C:\Users\ACS\AppData\Local\hermes\profiles\
mars-{academic,finance,hr}` plus the shared vault at `C:\Users\ACS\.hermes\mars-vault` and
`mars-vault-confidential`. Railway volumes are only reachable from inside the running
container, so copy this data in via `railway ssh` (or the Railway CLI's file-copy path — check
current Railway docs for the exact command, it's changed before) onto the fresh volume,
preserving this exact layout:

```
/opt/data/
├── profiles/
│   ├── mars-academic/   (everything currently under profiles/mars-academic on this machine)
│   ├── mars-finance/
│   └── mars-hr/
├── mars-vault/           (currently C:\Users\ACS\.hermes\mars-vault)
└── mars-vault-confidential/
```

### 4. Environment variables (set as Railway secrets, never commit real values)
Each of the 3 profiles' `.env` currently sets these keys — set them as Railway service
variables (or per-profile `.env` files on the volume, which is what's there today and will
keep working as-is once the volume is populated per step 3):

- `MONGODB_URI`, `MONGODB_DB`, `MONGODB_COLLECTION` — already a remote Atlas URI, works
  unchanged from Railway (see step 5 for the one thing to verify).
- `OBSIDIAN_VAULT_PATH`, `CONFIDENTIAL_VAULT_PATH` — must point to the container paths from
  step 3 (`/opt/data/mars-vault`, `/opt/data/mars-vault-confidential`), not the Windows paths
  they currently hold. Update these in each profile's `.env` after copying the data over.
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS` — unchanged, just don't put real tokens in
  any file that gets committed to git.
- `HERMES_KANBAN_BOARD` — unchanged.

### 5. Verify MongoDB Atlas allows Railway's traffic
Atlas Network Access (console.mongodb.com → your project → Network Access) needs to allow
Railway's egress IPs. Railway's outbound IPs are dynamic/shared unless you're on Railway's Pro
plan with Static Outbound IPs enabled — the pragmatic options are: confirm Atlas already
allows "Access from Anywhere" (0.0.0.0/0) — likely already true, since the same URI worked
instantly from this Windows machine with zero IP configuration — or add Railway's regional
egress range to the allowlist. This can't be checked or changed from this repo; verify it in
the Atlas console directly.

## What this does NOT cover

- Safia is intentionally excluded from this deployment — Mars only, per current scope.
- The web dashboard (`hermes dashboard`) isn't part of this deploy target; it's a separate
  concern from the 3 Telegram gateways and binds to `127.0.0.1` by default even inside a
  container (see `docker-compose.yml`'s security notes) — exposing it needs its own reverse
  proxy + auth, not covered here.
