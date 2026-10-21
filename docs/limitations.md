# Limitations

- **The API only returns your recent bookmarks.** X's bookmarks endpoint only exposes your most recent bookmarks (X's
  docs say up to 800), and it can stop early with no next page. Older bookmarks are invisible to it. If you have an
  older export (e.g. from a browser extension), convert it to the simple JSON format
  (`[{"url", "text", "author", "created_at"}]`) and pass it with `--input`.
- **No bookmark timestamps.** X doesn't say *when* you bookmarked something. Ages, the date range and "oldest untouched"
  use the post's creation date. The API order (most recently bookmarked first) is kept as `rank`.
- **Un-bookmarks aren't seen by incremental pulls** (see [pulls.md](pulls.md)).
- **Media is not analysed.** Posts that are only a video or image ("this 🤯") have little text, so triage and themes
  rely on the quoted post and X's topic annotations. Most of these end up in Archive.
- **x.com links can't be verified** without a login: X Articles and profiles are reported as unverifiable.
- **Heuristic triage is a baseline.** Without the Grok Bot review pass, next actions are generic ("Read it (2 min)").
  The bot's overrides are what make the list useful.
- **Theme quality depends on the backend.** TF-IDF fallback clusters short posts poorly; install `fastembed`.
  English-first embeddings group non-English posts together.
- **Freshness "fresh %" is a definition, not a fact of nature**: alive and within a bucket-specific shelf life
  ([freshness.md](freshness.md)). Change the half-lives in `freshness.HALF_LIFE_DAYS` if you disagree.
- **Privacy filter is keyword-based** and will miss things. Look before you post.
