---
name: weekly-resurface
description: >
  Once a week, pull only my new X bookmarks, re-check freshness, and resurface 3 open bookmarks with a concrete next
  action, asking me: do it, snooze, or archive. Records my answers so done items never come back.
  Use for the weekly bookmark routine, "resurface my bookmarks", or /weekly-resurface.
metadata:
  short-description: "3 bookmarks a week: do / snooze / archive"
---

# Weekly resurface

## Steps
1. **Incremental pull** exactly as in bookmark-triage step 2 (probe with `max_results=10`, stop at the first known id).
   On a typical week this is 10 post reads. If the X connector is unavailable or errors, say so and continue with the
   archive we already have; never pretend there were no new bookmarks.
2. If there are new bookmarks, triage just those (rules pass, then review pass for the new ids only) and append to
   `private/triage_overrides.json`.
3. Run `.venv/bin/bdc run --input private/archive.json --out private/out --me <username> --state private/state.json --overrides private/triage_overrides.json --theme-names private/theme_names.json`.
   It refreshes freshness (cached) and writes `private/out/resurface.md` with this week's 3 picks.
4. Send me the contents of `resurface.md` in this conversation. Keep it short. Mention how many new bookmarks came in.
5. When I answer (`do 1`, `snooze 2`, `archive 3`, or in words), record it:
   `.venv/bin/bdc decide --state private/state.json <n> <do|snooze|archive> [--days 14]`.
   - `do`: mark done. If the action is something you can do *inside the bot's own sandbox* (read a paper and summarise
     it, clone and try a repo on the bot's computer), offer to do it now.
   - `snooze`: comes back after 14 days (or what I say).
   - `archive`: never resurfaced again. Remind me to unbookmark it on X myself.

## How the 3 are picked (explain if I ask)
score = bucket weight × debt(age) × save-rate quality × alive, then MMR re-ranking so the three differ in theme,
author and bucket. Archive-bucket, done and archived items are never picked; snoozed items return when the snooze ends;
private-topic items are never picked. See `docs/how-it-works.md`.

## Rules
- Read-only on X, always. I unbookmark, DM and follow myself.
- Never send anything outside this conversation without my approval.
