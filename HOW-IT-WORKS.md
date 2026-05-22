# Ross Built Helper — How It All Works (the simple story)

*Explained like you're 5. Real grown-up names are in (parentheses) so it's still a real manual. A glossary is at the bottom.*

---

## 1. The big idea — what is this thing?

Ross Built builds **big fancy houses**. Building one house takes a LOT of helpers — plumbers, painters, electricians, framers (we call them **subs**). It is really, really hard to remember:
- Who is supposed to do what, and *when*
- Who actually showed up today
- What's left to finish
- What might go wrong

So we built a **helper app** — like a **magic notebook on your phone** — that remembers *everything* and shows everyone the **same picture**. The bosses (the **PMs** — project managers) use it to run their **Monday meetings**.

Think of it like a really smart teacher's helper that keeps track of every kid and every chore, and never forgets.

---

## 2. What the app eats (where it gets its info)

The helper eats **three kinds of food**:

1. **Meeting recordings** (Plaud). When the bosses talk in a meeting, a little recorder writes down everything they said. The robot reads it and turns the talking into a **to-do list**.
   *Example:* someone says "Walter needs to finish the drywall by Friday" → the app makes a to-do: **"Walter to finish drywall 2026-05-22."**

2. **Daily logs from Buildertrend.** Every day at each house, someone writes down "who came to work, what they did, the weather" and snaps **photos**. Our app grabs all of that.

3. **The big master checklist** (pay-app line items — ~220 things per house). This is the *backbone* — every single thing that must happen to finish a house. (We have the pieces; using it as the backbone is still on the wish list — see §9.)

**The clever trick:** the app checks these against each other so it tells the *truth*. If the meeting says "done" but the daily log shows nobody worked that week, the app raises its hand instead of believing it.

---

## 3. The robot brain (the AI — Claude)

There's a **smart robot** inside. It can:
- **Read** meeting talk and pull out the to-dos (always with a *real date*, never "tomorrow").
- **Write** a short summary of each house ("Drywall and stucco in progress; painting coming up").
- **Look at photos** and say what's happening ("They're painting the outside. Careful — someone's on a ladder with only a temporary rail.").

---

## 4. The rooms in the app (every page)

Like rooms in a house — each one has a job:

- 🏠 **Front page / Jobs** (`/`) — a list of *every house we're building*. The most-worried-about one (most late to-dos) sits at the top. Each row shows the boss, the address, and how many to-dos are open / late. Tap a **boss's name chip** to see just that boss's houses. Tap a house to go in.

- 🗓️ **Monday Meeting** (`/meeting`) — the **run-of-show** for the meeting. It walks the houses one at a time (most urgent first); each one shows what's **past due**, what's **due this week**, and which **subs to watch**. Tap **"mark covered"** as you finish a house — a bar up top tracks how far you've gotten. Chips filter to one boss.

- 📋 **A house's page / Job** (`/v2/job/[id]`) — this is the **"one paper" for the Monday meeting**. At the top, a **robot-written summary** of the job, **how far along the money is** (Contract Progress — e.g. "48% billed, $2.0M of $4.3M") with a tap-open cost breakdown, and **how many photos the robot analyzed**. Below it, the to-dos split into **Today · Soon · Open · Done**. Tap the circle to check something off.

- 👷 **Subs** (`/subs`) — a list of all the helper companies (subs). Each has a **colored dot**: 🔴 needs attention (a to-do is late), 🟡 keep an eye (flagged or due this week), 🟢 all clear. A **⚑ Flagged** chip filters to the ones the system flagged for a closer look (with the reason shown).

- 👷‍♂️ **A sub's page / Sub profile** (`/sub/[id]`) — *everything* about one helper:
  - their open to-dos and how late they are
  - **crew size** (how many people they bring)
  - **how long they take** for each kind of work
  - **inspections** that happened while they were there
  - a **running checklist** with two lenses: **Safety** and **Schedule**
  - **photo notes** the robot wrote from their site photos
  - a **timeline** of every day they were on site

- ⬆️ **Import** (`/import`) — two ways to feed the app:
  - drop a **meeting recording** → robot makes to-dos
  - press the big **"✨ Pull from Buildertrend"** button → grabs daily logs + photos

- ✅ **Review** (`/v2/review`) — the robot's *suggestions* wait here so a grown-up can say yes/no before they go on the real list.

- 🔧 **Setup** (`/admin/migrate`) — a one-time "turn the database on" button.

---

## 5. The 8 special wishes we built

These are the things you asked for, and they're **done**:

1. **Pick the right house for each to-do** — the dropdown that lets you move a to-do to, say, Dewberry, before it goes on the list.
2. **No fuzzy dates** — every to-do has a *real* date. "tomorrow"/"by Friday" automatically become a date like **May 22**. Vague words like "ASAP" get removed.
3. **Crew size** — how many people a sub brings for a task.
4. **No more A–F grades** for subs (you didn't like grading them).
5. **How long each sub takes** for each kind of work (T-pole, electrical rough, etc.) — with a list of standard work steps.
6. **Inspections** each sub runs into.
7. **A running checklist per sub** — Safety lens + Schedule lens.
8. **The photo robot** — AI looks at daily-log photos and describes the work + flags safety stuff.

---

## 6. The Buildertrend "grabber" (the big rebuild)

Buildertrend (where the daily logs live) **changed how their website works**, so our old grabber broke — it would log in, look around, and find *nothing* (that's the "searching the jobs but not scraping" you saw).

So we built a **brand-new grabber** (`scrape_api.py`) that talks to Buildertrend's data **directly**:
1. asks BT for your **real active houses** (not the practice/estimate ones)
2. looks up **crew names**
3. grabs **every daily log** (who, what, weather, how many workers)
4. **downloads the photos**

Then the **photo robot** looks at each photo. **One button does the whole thing.**

> Important: the grabber runs **on your laptop** (it opens a real browser + a little program — the live website can't do that). But everything it finds gets saved to the shared memory, so the results show up on **both** your laptop *and* the live website.

---

## 7. The journey of one piece of info (how it all connects)

A little story:

1. **Monday:** the bosses meet; the recorder listens.
2. The **robot** turns the talk into **to-dos with real dates** → they appear on each house's page.
3. **Every day:** Buildertrend gets a daily log + photos.
4. You press the **one button** → the **grabber** pulls the logs + photos → saves them to the **big memory** → the **photo robot** describes the photos.
5. Now everyone, on their phone, sees: **who worked, how long they take, what the photos show, what's left to do.**
6. Because the big memory is **shared**, the same picture shows on your laptop *and* the live website.

---

## 8. Where the pieces live (building blocks)

- 🧠 **The big memory = Supabase** — a database. Like a giant toy box that remembers everything forever.
- 🌐 **The live website = Vercel** — where the app lives on the internet so any phone can open it (**production-cockpit.vercel.app**).
- 🤖 **The robot = Claude AI** — reads, writes, and looks at photos.
- 🪝 **The grabber = a little program on your laptop** (`buildertrend-scraper`). It needs your Buildertrend password — typed only into the app/your computer, **never** into a chat.

---

## 9. What's DONE ✅ vs what we still WANT 🎯

**DONE (built & working):**
- ✅ The website is **live**, works great on phones, and is **Ross Built blue**.
- ✅ All **8 features** above work and were checked with real data.
- ✅ The **database** is set up.
- ✅ The **Buildertrend grabber** works — pulls logs + photos, and the AI describes the photos.
- ✅ Real daily logs are flowing in (150+ logs, real subs, real photos, AI summaries).
- ✅ Fixed hidden bugs (the database was never "turned on"; a query that quietly returned nothing; stale data) and **deployed it live**.
- ✅ **Contract Progress** on each house — the pay-app master checklist now shows "% billed" + a cost breakdown by line.
- ✅ **"By boss" view** — chips on the front page *and* the Monday Meeting filter to one PM's houses.
- ✅ **RED/YELLOW/GREEN health dots** on subs + a **⚑ Flagged** lane (with the reason shown).
- ✅ **Monday-meeting run-of-show** (`/meeting`) — walks the houses, surfaces past-due / this-week / subs-to-watch, mark each one covered.
- ✅ Fixed the **Buildertrend "Pull" button** crash (the "show browser" toggle) and pulled a full refresh.

**STILL WANT (next, in rough order):**
- 🎯 Put the robot's full **truth-checking brain** *inside* the app (read → reconcile → double-check). That part still runs on the laptop today, not in the website.
- 🎯 Later: a meeting that **forecasts** what to watch (reliability %, 2/4/8-week look-ahead) and **predicts finish dates** — not just shows today.

---

## 10. Grown-up words (simple → real)

| We said… | Really means… |
|---|---|
| Helper app / website | `production-cockpit` (a Next.js app) |
| Big memory / toy box | Supabase (a Postgres database) |
| Lives on the internet | Vercel (hosting) |
| The robot | Claude AI |
| The grabber | `buildertrend-scraper` / `scrape_api.py` |
| Daily logs | Buildertrend daily logs |
| Meeting recording | Plaud transcript |
| To-dos | the `todos` table |
| The one button | "✨ Pull from Buildertrend" |
| Turn on the database | run the migration (`/admin/migrate`) |

---

*The deepest technical handoff (every fix, every command, the exact Buildertrend API) lives in `STATE.md`. This file is the friendly version.*
