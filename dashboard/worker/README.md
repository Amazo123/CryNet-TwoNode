# The hosted dashboard (Cloudflare Workers + D1, free)

This is the online copy of the caregiver dashboard.  The offline copy is
`dashboard/server.py` — one Python file, no installs — and it keeps
working exactly as before; nothing about hosting changes how the hub
behaves offline.  The hub still records every cry to its own flash and
uploads whenever it can reach the internet.

Everything here runs on Cloudflare's free tier: no credit card, no
server to keep alive, no idle-reclaim.  The limits are far above what
one household generates:

| what                | free allowance            | this system uses             |
|---------------------|---------------------------|------------------------------|
| Worker requests     | 100,000 / day             | ~100 / day (uploads + pages) |
| D1 rows read        | 5,000,000 / day           | the requested window only    |
| D1 rows written     | 100,000 / day             | ~50 / night of cries         |
| D1 storage          | 5 GB total (500 MB / db)  | ~6 MB per *decade* of cries  |

## One-time setup (already done once — this is the record)

Needs only Node.js on the machine.

```sh
cd dashboard
npx wrangler login                                  # opens the browser, click Allow
npx wrangler d1 create crynet                       # prints the database_id
#   paste that id into wrangler.jsonc, then:
npx wrangler d1 execute crynet --remote --file worker/schema.sql
npx wrangler secret put UPLOAD_TOKEN        # the hub's token  (net token <value>)
npx wrangler secret put DASHBOARD_PASSWORD  # the caregiver's login password
```

The username is `caregiver` (change with `DASHBOARD_USER`).

## Deploy after a change

```sh
cd dashboard
npx wrangler deploy
```

The page is then at `https://amazings-crynet.<account>.workers.dev/`
— open it, log in with the password, done.

## Pointing the hub at it

On the hub's serial console (the port its log goes to):

```
net set https://amazings-crynet.<account>.workers.dev/api/v1/events
net token <the UPLOAD_TOKEN value>
net          # check: URL, token set, Wi-Fi, channel
upload       # send everything stored but not yet confirmed
```

The hub's firmware already trusts the certificate (Cloudflare's edge
chains to GTS Root R4, which is in the ESP-IDF CA bundle the hub was
built with), so nothing on the board changes but those two settings.

**Only one address to type.** The hub also reports who is here, and it
does that to `POST /api/v1/presence` — but that address is *derived*:
it is the events URL with its last path segment changed. So `net set
https://…/api/v1/events` is the only address the owner ever types.

### The token, kept off Git

The upload token is a secret and this repository is public, so it is
**not** in any tracked file. It lives in three places and nowhere else:
Cloudflare's secret store (`UPLOAD_TOKEN`), the hub's own NVS (set
once with `net token`), and a local, git-ignored `dashboard/.secrets`
on the machine that runs the offline copy:

```
CRYNET_TOKEN=<the UPLOAD_TOKEN value>
CRYNET_PASSWORD=<the DASHBOARD_PASSWORD value>
```

That file is what lets the offline dashboard be started against the same
token without typing it:

```sh
python dashboard/server.py --token "$(grep CRYNET_TOKEN dashboard/.secrets | cut -d= -f2)"
```

### One thing to know about Cloudflare and Python

Cloudflare's edge **rejects `Python-urllib` with error 1010** before
the request reaches the Worker, so a Python script that posts to the
hosted copy needs its own `User-Agent` header:

```python
req = urllib.request.Request(url, data=body, method="POST", headers={
    "Content-Type": "application/json",
    "X-CryNet-Token": token,
    "User-Agent": "CryNet-Tools/1.0",     # <- without this: 403
})
```

The hub is unaffected: it sends `ESP32 HTTP Client/1.0`, which the
edge passes.

## Backups

D1 keeps 7 days of point-in-time history ("Time Travel") on the free
plan.  For a copy that outlives that:

```sh
npx wrangler d1 export crynet --remote --output crynet-backup.sql
```

Run it now and then and keep the file; it is a plain SQLite dump the
offline server could be seeded from if the online copy ever went away.

## Changing the secrets

```sh
npx wrangler secret put UPLOAD_TOKEN        # then:  net token <new>   on the hub
npx wrangler secret put DASHBOARD_PASSWORD  # the browser asks again next login
```

## Local development without touching the live copy

`npx wrangler dev` serves the Worker on `http://127.0.0.1:8787` with a
local D1 (secrets come from a `.dev.vars` file, one `NAME=value` per
line).  Or skip all of it: `python dashboard/server.py` is the whole
offline dashboard and needs nothing but Python.
