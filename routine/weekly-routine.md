# Weekly routine: "Bookmark debt collector"

Paste this into the Bot that owns the skills (the one with the X plugin connected).
Grok Bot creates the routine and shows the next run; confirm the schedule and time zone it echoes back.

---

Every Sunday at 9:00 AM America/New_York, run the weekly-resurface skill.

- Input: my X bookmarks via the X plugin (read-only), plus the archive and state in
  ~/bookmark-debt-collector/private/.
- Pull only new bookmarks: probe with max_results=10 and stop at the first bookmark we already have.
- Post the 3 resurfaced bookmarks in this conversation with their next actions and ask me: do it, snooze, or archive.
  Include how many new bookmarks came in and what the pull cost.
- Record my answers with `.venv/bin/bdc decide`.
- On the first Sunday of each month, also regenerate my Bookmark Wrapped card (bookmark-wrapped skill) and attach it.
- Never post, like, follow, bookmark, unbookmark or DM on X. Never send anything outside this conversation without asking.
- If the X plugin is unavailable or errors, say so and resurface from the existing archive instead of guessing.

---

Test it once before enabling: "Run the weekly bookmark routine now as a test."
