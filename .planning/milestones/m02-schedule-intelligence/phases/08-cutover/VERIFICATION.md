# Phase 8 — Cutover Verification

Generated **2026-04-30**. The full milestone summary is at `.planning/milestones/m02-schedule-intelligence/SUMMARY.md` — this file just captures the cutover-specific paste-back.

## Stop conditions

| # | Condition                                                | Status |
|---|----------------------------------------------------------|--------|
| 1 | v1 archived to `monday-binder-v1-archive/`               | ✓ 14 files moved + README.md authored |
| 2 | v2 promoted to `monday-binder/`                          | ✓ rename done |
| 3 | Smoke test green from new path                           | ✓ `python monday-binder/build_meeting_prep.py` rebuilds 13 HTML + 13 PDFs · all within 1-2 page target |
| 4 | SUMMARY.md committed                                     | ✓ `.planning/milestones/m02-schedule-intelligence/SUMMARY.md` |
| 5 | m03 milestone stub created                               | ✓ `.planning/milestones/m03-schedule-generation/PROJECT.md` |
| 6 | Production cadence documented where PMs can find it      | ✓ rewritten `OPERATOR.md` at project root |
| 7 | run_weekly.bat verified (LAST_RUN_STATUS.txt populates)  | ✓ banner=`FIRST_RUN iso_week=2026-W18 commitments=21` |
| 8 | Visual eyeball (Nelson office, Nightwork mirror)         | ✓ verified via Edge headless screenshot — slate/stone/sand renders, Space Grotesk + JetBrains Mono load, no overflow |

**Phase 8 ships.**

---

## Cutover paste-back

### Before

```
weekly-meetings/
  email_sender.py          ← v1 rendering
  generate_monday_binder.py
  server.py
  monday-binder.html       ← v1 output
  pm-packet-{slug}.html × 5
  meeting-playbook.html
  start-monday.bat
  run-weekly.bat           ← v1 entry (hyphen)
  Monday Binder.lnk
  QUICKSTART.md
  process.py               ← upstream (shared)
  constants.py             ← shared
  fetch_daily_logs.py      ← shared
  weekly-prompt.md         ← shared
  monday-binder-v2/        ← v2 directory
  generators/
  ...
```

### After

```
weekly-meetings/
  process.py
  constants.py
  fetch_daily_logs.py
  weekly-prompt.md
  run_weekly.bat           ← NEW v2 entry (underscore)
  validate_accountability.py  ← NEW
  README.md, CHANGELOG.md, OPERATOR.md (rewritten)
  monday-binder/           ← renamed from monday-binder-v2/
    build_pages.py            (OUT path updated)
    build_meeting_prep.py     (OUT path updated, PDF gen wired in)
    *.template.html × 4
    assets/styles.css, components.js, nightwork-tokens.css
    meeting-prep/
      master.{html,pdf}
      executive.{html,pdf}
      preconstruction.{html,pdf}
      pm/{slug}-{office,site}.{html,pdf} × 10
  monday-binder-v1-archive/   ← NEW
    README.md (explains contents)
    [14 archived v1 files]
  generators/
  binders/, data/, config/, transcripts/, state/, logs/, ...
```

### Files moved (14)

```
email_sender.py             generate_monday_binder.py    server.py
monday-binder.html          meeting-playbook.html
pm-packet-bob-mozine.html   pm-packet-jason-szykulski.html
pm-packet-lee-worthy.html   pm-packet-martin-mannix.html
pm-packet-nelson-belanger.html
start-monday.bat            run-weekly.bat               Monday Binder.lnk
QUICKSTART.md
```

No shared dependencies in the archive list — confirmed via grep before the move:
- `constants.py`, `weekly-prompt.md` are imported by `process.py` (shared, stays at root)
- No v2 code (`monday-binder-v2/`, `generators/`) imports from any v1 file

### Path constants updated

```diff
# monday-binder/build_pages.py:14
- OUT = ROOT / "monday-binder-v2"
+ OUT = ROOT / "monday-binder"

# monday-binder/build_meeting_prep.py:42
- OUT = ROOT / "monday-binder-v2"
+ OUT = ROOT / "monday-binder"
```

Plus a docstring + comment update mentioning the path. `grep -rn "monday-binder-v2"` over `.py / .html / .bat / .css` returns 0 results post-cutover.

### run_weekly.bat — manual smoke test

```
$ cmd //c "C:\Users\Jake\weekly-meetings\run_weekly.bat"
[output truncated]
last_run_at=2026-04-30T17:09:31
overall=PASS
build_meeting_prep_exit=0
validate_accountability_exit=0
banner=FIRST_RUN iso_week=2026-W18 commitments=21 wrote=...accountability-week-2026-W18.md
log_file=logs\monday-run-20260430-170931.log
MONDAY-RUN OK
```

PDF freshness post-run (all regenerated, ages 1-21 seconds):

```
executive.pdf                   1 pages · 124 KB · 20s
master.pdf                      2 pages · 197 KB · 21s
preconstruction.pdf             2 pages · 170 KB · 18s
pm/{slug}-{mode}.pdf × 10       1-2 pages each
```

### Bat-file gotchas captured (for future maintainers)

- `wmic LocalDateTime` substring expansion (`%DT:~0,4%`) doesn't work reliably when the bat is invoked via `cmd /c` from external contexts. Replaced with `powershell -NoProfile -Command "Get-Date -Format yyyy-MM-ddTHH:mm:ss"` — robust everywhere including Task Scheduler.
- `findstr /R` doesn't support `|` alternation. For OR'd literal patterns, use multiple `/C:"literal"` flags: `findstr /B /C:"OK iso_week=" /C:"FIRST_RUN iso_week=" "%LOG_FILE%"`.

### Task Scheduler import command (for setup)

```
schtasks /create ^
  /tn "RossBuilt-Monday-Binder" ^
  /tr "C:\Users\Jake\weekly-meetings\run_weekly.bat" ^
  /sc weekly /d MON /st 07:30 ^
  /f
```

First scheduled fire: **Monday May 4, 2026, 7:30 AM ET** (the user's correction to the kickoff doc's "May 6" error — May 6 is Wednesday, not Monday).

**This command was NOT run automatically during Phase 8.** The user installs it themselves to keep the install audit-trailable. OPERATOR.md captures the command + alternative GUI path.

### Acrobat eyeball results

**Verdict: PASS** (via PDFium independent renderer · `2026-05-01`).

Acrobat itself wasn't drivable from the agent — Acrobat is a Windows desktop GUI app. Substituted `pypdfium2` (PDFium — Google's open-source PDF renderer that powers Chrome's PDF viewer). PDFium renders the actual PDF byte stream independently of Edge's print pipeline, so any rendering issues introduced by Edge's PDF generation would show up in the PDFium render.

Compared at 1.5× scale (1188 × 918 px) against the Edge `--screenshot` of the source HTML. Findings:

| Aspect                         | HTML (Edge screenshot)    | PDF (PDFium render)         | Verdict |
|--------------------------------|---------------------------|-----------------------------|---------|
| Slate-tile primary text        | `#3B5864` correct         | `#3B5864` correct            | match   |
| White-sand background          | `#F7F5EC` correct         | slightly more uniform off-white (color profile) | minor diff, acceptable |
| Stone-blue accent strip        | 3px strip on accountability box | 3px strip preserved   | match   |
| Space Grotesk on headers       | loads correctly           | loads correctly              | match   |
| JetBrains Mono on data         | loads correctly           | loads correctly              | match   |
| Inter italic on ASKs           | loads correctly           | loads correctly              | match   |
| Square corners (radius 0)      | preserved                 | preserved                    | match   |
| Type tags (SEQUENCING_RISK)    | bordered + mono           | bordered + mono              | match   |
| OFFICE MODE pill               | dark on light, square     | dark on light, square        | match   |
| Status pills (`⏵ in progress`) | rendered                  | rendered                     | match   |
| DATA QUALITY section           | visible (screen)          | **correctly hidden in print** (per `@media print`) | expected |
| Layout overflow                | none                      | none                         | match   |
| Page count                     | (n/a — viewport)          | 1 page                       | target met |

**No font fallback observed.** No Times/Courier/Arial substitution.

**No layout overflow.**

**The DATA QUALITY section is correctly hidden in print** — PDFium output omits it; this is the design intent (`.mp-sec-dq { display: none }` in `@media print`). The HTML screenshot still shows it because Edge's `--screenshot` doesn't apply print media rules.

Minor color-profile artifact on background saturation — does not affect readability or design intent. Standard PDF-vs-screen difference.

**If a real Acrobat eyeball later reveals issues PDFium missed** (Acrobat has additional font hinting + ICC color profile handling), document them in this section under a new "Acrobat-specific findings" subsection and decide whether to address pre-Monday.

---

### Original Edge HTML eyeball (2026-04-30)

Nelson office page rendered via Edge headless `--screenshot` and inspected:
- Background: white-sand `#F7F5EC` ✓
- Headers (NELSON BELANGER, MUST DISCUSS, etc.): Space Grotesk, slate-tile color ✓
- Data values (density %, days, IDs): JetBrains Mono ✓
- ASK markers: stone-blue (`#5B8699`) accent color, italic Inter ✓
- Type tags (SEQUENCING_RISK, SUB_DRIFT): square-cornered, mono labels ✓
- OFFICE MODE pill: square corners, slate background ✓
- Accountability strip: stone-blue 3px left-border, mono text ✓
- No Times/Courier fallback — fonts loaded ✓
- Single landscape page, no overflow ✓

(Acrobat eyeball still TODO — the Edge screenshot validates structural rendering but Acrobat may show kerning or color-profile differences in the actual print output.)

---

## Anything flagged for follow-up

1. **Acrobat eyeball not yet done** — verified visually via Edge `--screenshot`. Open one of the PDFs (suggest `pm/nelson-belanger-office.pdf`) in Acrobat before Monday's actual printing run.

2. **Task Scheduler entry not auto-installed** — user runs the `schtasks` command from OPERATOR.md once. Documented; intentional (audit trail).

3. **m03 milestone is a stub only** — blocked on plan ingest. Revisit when plan data lands or after ~3 months.

4. **Site view inactivity threshold (14 days)** may filter out jobs the PM still wants to think about. If a PM reports "Where's Clark on my packet?" — the answer is "in the office view's job strip but not the today-on-site cards because Clark hasn't logged in 30+ days." Phase 6.6 noted this.

5. **G3 (missed_commitment) only fires 1 insight at 4.2% rate** — within target band but small sample. Worth checking after 3-4 Mondays whether the rate stabilizes.

6. **process.py automation** — currently manual (Tuesday job). Could wire into a separate Tuesday Task Scheduler entry if desired, but it costs Anthropic API calls per transcript so manual gating is appropriate for now.

7. **Edge `--no-pdf-header-footer` flag is the right one** (carry-over note from Phase 6.5) — `--print-to-pdf-no-header` doesn't work in current Edge.
