# Incremental pulls

reads go through your X plugin, read-only.

## How this project keeps reads down
- **First run**: one full pull (100 per page). X only returns your 800 most recent bookmarks, so that's at most 8
  pages.
- **Every later run**: a **probe** of `max_results=10`. If any of those 10 is already known, stop. Only if all 10 are
  new do we page further, 100 at a time, stopping at the first page that contains a known id. The bookmarks endpoint
  has no `since_id`, so this is the cheapest correct way to get "just the new ones".
- A normal week is therefore **10 post reads**.
- Freshness checks hit GitHub, arXiv and the linked sites, not the X API. Quoted-post liveness comes free with the
  bookmark pull (the `errors` array).
- Everything is cached locally (`archive.json`, `.cache.json`, `state.json`).

## Trade-off
Incremental pulls can't see **un-bookmarks**: if you remove a bookmark on X it stays in the local archive. Archive it in
the weekly conversation, or do an occasional full pull (delete `known_ids` from `state.json`).
