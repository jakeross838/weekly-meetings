# Email Intel — Setup

The email-capture service reads PMs' **sent** mail via Microsoft Graph, extracts
durable job intelligence with Claude, resolves each email to a real job, and
stores it in Supabase `job_intel` (`source='email'`). It ships in two phases:

- **Phase 1 — `AUTH_MODE=device`** (default): you log in once in a browser and it
  reads **your own** sent items. Good for a single PM to try it immediately.
- **Phase 4 — `AUTH_MODE=app`**: unattended, reads a **list of PM mailboxes** with
  no user present (e.g. nightly Task Scheduler). Requires tenant-admin consent.

Both modes share all fetch/route/store logic; only token acquisition and which
mailboxes are swept differ.

---

## 0. Install + base config (both phases)

```bash
cd email-intel
python -m pip install -r requirements.txt
```

`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `ANTHROPIC_API_KEY` already live
in the repo-root `.env` (`…/weekly-meetings/.env`), which `config.py` loads
automatically. You only add the `AZURE_*` and behavior variables (below). Put
them in that same repo-root `.env`, export them in your shell, or drop an
optional `email-intel/.env`. See `config.example.py` for the full list.

> Never hardcode secrets and never pass a password anywhere — the OAuth flows
> below handle all authentication.

---

## 1. Populate the routing map FIRST (do this before either phase)

Routing attaches each email to a real `jobs.id`. The reliable path is an exact
match of the email's people (sender + to + cc) against each job's
**`client_emails[]`** and **`pm_email`**. If those columns are empty, routing
falls back to matching Claude's inferred **project name** to a job name, and
otherwise leaves `job_id = NULL` (an "unrouted" row a human fixes later).

So fill them in for the jobs you care about:

- **Admin UI:** edit each job and set the PM's email and the client email(s).
- **Or SQL** (Supabase SQL editor):

  ```sql
  update public.jobs
     set pm_email      = 'jake@rossbuilt.com',
         client_emails = array['owner@example.com','owner.spouse@example.com']
   where id = 'krauss';
  ```

`client_emails` is `text[]` (a Postgres array); `pm_email` is a single address.
Addresses are matched case-insensitively. `pm_email` alone is shared across all
of a PM's jobs, so it can't pin a job by itself — it's the **client** address on
an email that identifies the job. Populate `client_emails` for best results.

Check what's routable:

```sql
select id, name, pm_email, client_emails
from public.jobs
where active
order by id;
```

---

## 2. Phase 1 — device mode (read your own mailbox)

### 2a. Create the Azure app registration (public client)

1. Azure Portal → **Microsoft Entra ID** → **App registrations** → **New registration**.
   - Name: `Ross Built Email Intel`.
   - Supported account types: **Single tenant** (this org only).
   - Redirect URI: leave blank (device code needs none).
   - **Register**. Copy the **Application (client) ID** and **Directory (tenant) ID**.
2. **Authentication** → **Advanced settings** → set **Allow public client flows** = **Yes**. Save.
   (Required for the device-code flow.)
3. **API permissions** → **Add a permission** → **Microsoft Graph** →
   **Delegated permissions** → add **`Mail.Read`** → **Add permissions**.
4. Click **Grant admin consent for <tenant>** (or have an admin do it). The
   `Mail.Read` row should show a green "Granted" state.

### 2b. Configure + run

Add to your `.env` (or environment):

```
AZURE_CLIENT_ID=<Application (client) ID>
AZURE_TENANT_ID=<Directory (tenant) ID>
AUTH_MODE=device
MAILBOX_LABEL=jake          # any stable label; keys this mailbox's watermark row
```

Run it:

```bash
python capture.py
```

The first run prints a URL + code — open the URL, enter the code, sign in as the
PM whose sent mail you want. The token is cached in `.token_cache.bin`
(git-ignored), so subsequent runs are silent for weeks/months.

### 2c. Verify

- The run prints lines like `+ [commitment] krauss (address:client): …` and a
  per-mailbox summary (`stored N (M unrouted), skipped …`).
- Confirm rows landed on the right job:

  ```sql
  select job_id, project, intel_type, summary, sent_at
  from public.job_intel
  where source = 'email'
  order by created_at desc
  limit 20;
  ```
- Rows with `job_id IS NULL` are the **unrouted** bucket — fix the job's
  `client_emails`/`pm_email` (step 1) and they'll route on the next capture.
- Re-running is safe: `message_id` dedupe + the per-mailbox watermark mean the
  same email is never re-processed or double-billed.

---

## 3. Phase 4 — app mode (unattended, all PM mailboxes)

> **Read this:** app mode reads **every listed PM mailbox with no user present**.
> It uses an **application** permission, which grants org-wide mailbox read and
> **requires tenant-admin consent**. Scope it down with an application access
> policy (3c) so it can only read the intended mailboxes.

### 3a. Add the application permission to the same app registration

1. **API permissions** → **Add a permission** → **Microsoft Graph** →
   **Application permissions** → add **`Mail.Read`** → **Add permissions**.
2. Click **Grant admin consent for <tenant>** — the **Application** `Mail.Read`
   row must show "Granted". (You now have both the delegated and application
   `Mail.Read`; that's fine.)

### 3b. Create a client secret

1. **Certificates & secrets** → **Client secrets** → **New client secret**.
2. Description + expiry (e.g. 12–24 months — set a calendar reminder to rotate).
3. Copy the secret **Value** immediately (it's shown only once).

### 3c. (Recommended) Scope which mailboxes it can read

By default the application permission can read **all** mailboxes. Restrict it with
an application access policy (Exchange Online PowerShell), e.g. a mail-enabled
security group `email-intel-mailboxes` containing only the PM mailboxes:

```powershell
New-ApplicationAccessPolicy `
  -AppId <AZURE_CLIENT_ID> `
  -PolicyScopeGroupId email-intel-mailboxes@rossbuilt.com `
  -AccessRight RestrictAccess `
  -Description "Email Intel: sent-mail read, PM mailboxes only"
```

### 3d. Configure + run unattended

Add to the environment the scheduler will use:

```
AZURE_CLIENT_ID=<Application (client) ID>
AZURE_TENANT_ID=<Directory (tenant) ID>
AZURE_CLIENT_SECRET=<the secret Value from 3b>
AUTH_MODE=app
PM_MAILBOXES=pm1@rossbuilt.com,pm2@rossbuilt.com   # or leave blank -> derived from jobs.pm_email
```

If `PM_MAILBOXES` is blank the service sweeps every **distinct `jobs.pm_email`**.
Each mailbox gets its **own** `sync_state` watermark row keyed by its address.

Run once by hand to confirm, then schedule it:

```bash
python capture.py
```

**Windows Task Scheduler:** Create Task → run whether user is logged on or not →
Action: **Start a program** → `python.exe` with argument the full path to
`capture.py` and **Start in** = the `email-intel` directory (so it finds
`config.py`/`.env`). Trigger: daily/nightly. Ensure the account it runs as has
the `AZURE_*` env vars (set them as machine/user environment variables, or use a
small wrapper `.cmd` that exports them then calls python).

### 3e. Verify

Same checks as 2c, but you should see one summary block per mailbox and the
`sync_state` table should now have one row per PM mailbox:

```sql
select mailbox, last_processed_at from public.sync_state order by mailbox;
```

---

## 4. Reading the results

```bash
python analyze.py "Fish"     # by job name
python analyze.py "fish"     # or by slug (jobs.id)
```

Produces a master-PM review (state of play, open commitments, risks/gaps, next
actions) from the captured intel for that job. Unrouted rows (no `job_id`) can
still be reviewed by passing the inferred project name.

---

## Config reference

Every variable, its default, and where it's read is documented in
`config.example.py`. Behavior knobs: `DAYS_BACK_ON_FIRST_RUN` (7),
`MAX_EMAILS_PER_RUN` (200, per mailbox — the cost guard). Model names resolve
**Supabase `app_config` → env → prototype default**, so an operator can retune
`INTEL_EXTRACT_MODEL` / `INTEL_ANALYZE_MODEL` centrally without a redeploy.

## Offline sanity check

The routing logic is pure and testable without any network/credentials:

```bash
python routing.py     # runs the word-boundary + resolver self-tests
```
