# Monday Binder — Quickstart

One-page version. For detail, see [OPERATOR.md](OPERATOR.md).

## Run a Monday

1. **Double-click `start-monday.bat`** — server starts, browser opens to `localhost:8765`.
2. **Click "Refresh everything"** — pulls fresh BT data + processes any new transcripts. Wait for status badge → `done`.
3. **Click each PM tab** — review Open Items + Heads Up + Look-Aheads.
4. **Click 📧 Email \<PM\>** on each tab — Outlook draft opens with 2 PDFs. Review, click Send.
5. **Close the console window** when done.

## Upload a transcript

Drag the `.txt` file onto the browser. Click **Process now**. Wait ~3 min.

Alternatively: drop into `transcripts/inbox/` and click Refresh.

If the upload disappeared without changes, look in `transcripts/skipped/` — likely a filename parse failure. Rename to include a date and PM name, retry.

## Ask the chat

Click the **💬** button (bottom right). Try:
- *"Which subs missed the most days last month?"*
- *"How long did Plumbing rough take on Drummond?"*
- *"What's Bob's URGENT count?"*

Cost: ~$0.30 first question, ~$0.05 each follow-up.

## When something goes wrong

- **Status stuck on `scraping`** → CAPTCHA opened in another window — solve it.
- **Email button does nothing** → Open Outlook first, then retry.
- **Transcript not picked up** → Check `transcripts/skipped/` for parse failure.
- **Anything else** → See OPERATOR.md "When something looks wrong".

## Don't

- Don't run two instances of the server.
- Don't edit binder JSON files while the server is processing.
- Don't expect in-browser status changes to persist (they're session-only).
- Don't close the console window mid-pipeline.

## Cost

Typical Monday: **$8–$15** (5 transcripts × Claude Opus). Idle refreshes are free.

## Subs tab quick tour

- Dense table — click any sub row to drill into per-job + dates.
- Click any phase to see the per-job split — days worked at each job, calendar span, fast/typical/slow badge vs. cross-job median.
- Click any job to see specific dates with the supervisor's notes that day.
- The **📖 Phase Glossary** button (top of Subs and Jobs tabs) explains every BT phase tag in plain terms.
- The **View by Phase** toggle reorganizes subs by build sequence (Foundation → Closeout) instead of the alphabetical table.
- Multi-category subs (e.g. AV+Electrical shops) appear under every section their trades overlap.

## Jobs tab quick tour

- Top panel **Phase Durations** shows median/range per phase across all jobs. Click any phase to see per-job comparison. Useful for "is Plumbing/Gas Rough In on this job slow?"
- Sort the panel by build sequence, median duration, active jobs, or total volume; filter by phase name.
- Per-PM tab auto-restricts the Phase Durations panel to that PM's jobs and recomputes medians.
- Job cards remain below for per-job narrative.
