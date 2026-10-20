---
name: bookmark-triage
description: >
  Pull my X bookmarks (credit-aware), sort every one into Install/Try, Read, Learn,
  Follow up or Archive with one concrete next action, and write my action list.
  Use when I say "triage my bookmarks", "bookmark debt", "first pass", or run /bookmark-triage.
metadata:
  short-description: "X bookmarks -> action list"
  author: "@harris_p10"
---

# Bookmark triage

Turn my X bookmarks into a to-do list. Every bookmark gets exactly one bucket and
one next action I could finish in under 30 minutes.

## Required access
- The official **X plugin** (connector), signed in as me. Read-only use only.
- This repo on the bot's computer at `~/bookmark-debt-collector`
  (install: step 3 of `BOT.md`). Run every command from that folder.
  If the repo or Python is unavailable, do the triage yourself following the rules below and say so.

## Hard rules (never break)
- **Read-only on X.** Never post, reply, like, repost, follow, bookmark, unbookmark, delete or DM. If an action
  needs X (e.g. "unbookmark", "DM @x"), put it in the action list for *me* to do.
- Never invent numbers. Every count comes from `wrapped.json` / `freshness.json` produced by the scripts.
- Raw bookmark data stays in `~/bookmark-debt-collector/private/` (gitignored). Never commit, upload or share it.

## Steps
1. **Who am I.** Call the X connector `get_users_me`. Keep `id` and `username`.
2. **Pull, credit-aware** (X API reads cost credits per returned post):
   - Read `private/state.json` if it exists. Its `known_ids` are bookmarks we already have.
   - **First run** (no state): `get_users_bookmarks` with `max_results=100`, follow `meta.next_token` until it is absent.
   - **Later runs**: first call `max_results=10`. If any returned id is already in `known_ids`, stop: there's nothing
     older to fetch. Only page further (100 at a time) while every id on the page is new.
   - Always request these fields so the scripts get everything in one pass:
     `expansions=author_id,attachments.media_keys,referenced_tweets.id`,
     `post.fields=created_at,author_id,public_metrics,entities,lang,conversation_id,note_tweet,referenced_tweets,context_annotations`,
     `user.fields=username,name,public_metrics,verified,description`, `media.fields=type,url,preview_image_url`.
   - Save each raw response to a file (the tool's write-to-file option, or the JSON exactly as returned), then merge it:
     `.venv/bin/bdc ingest <saved file>`. It prints `NEXT:` (next pagination_token, or stop) and the cost so far.
   - Report how many posts were returned vs. new, and the estimated cost (returned × $0.001 at Owned-Read pricing).
3. **Rules pass.** Run
   `.venv/bin/bdc run --input private/archive.json --out private/out --me <username> --state private/state.json --overrides private/triage_overrides.json --theme-names private/theme_names.json`
   (the overrides/names files may not exist yet; that's fine).
4. **Review pass (this is where you add value).** Read `private/out/triage.json` and
   `private/out/bookmarks.normalized.json`. For every bookmark whose rule-based action is generic or wrong, write an entry
   to `private/triage_overrides.json`: `{"<post id>": {"category": "...", "next_action": "...", "skill": "..."}}`.
   - `category` is one of `Install/Try`, `Read`, `Learn`, `Follow up`, `Archive`.
   - `next_action` starts with a verb, names the specific thing (repo, paper, person, tip), and has a time box.
   - `skill` only for `Learn`: a 2-4 word label of the skill (used on the Wrapped card).
   - Use the bucket rules in `docs/triage.md`. When unsure between Read and Archive, choose Archive: the point is to
     shrink the pile.
   - Signals worth using: I already quoted/replied to it (→ Archive, "done already"); it quotes or mentions me
     (→ Follow up); several bookmarks quote the same post (keep one); time-boxed content that has expired.
5. **Name the themes.** Read `private/out/themes.json`. Write `private/theme_names.json` with a 2-4 word human name per
   theme, keyed `"term:<one of its top 4 terms>"` (stable across re-runs). Prefix a name with `_` to keep that theme off
   the shareable card (use it for anything personal: dating, health, politics). Themes whose name or top terms look
   personal (health, dating, looks, ...) or that are mostly private-topic posts are hidden automatically; to hide one
   by hand without renaming it, add `"_hide": ["<name or term:word>"]`. Check `private/out/privacy.json` for what got
   hidden and why.
6. Re-run step 3 so overrides and names apply.
7. **Reply** with: totals per bucket, the 5 highest-value open actions, anything broken (from `freshness.md`), and the
   paths to `actions.md`, `freshness.md` and `card.png`. Attach `card.png`.

## Validate before replying
- Bucket counts in your reply equal the counts in `private/out/wrapped.json`.
- Every bookmark id appears exactly once in `triage.json`.
- No private-topic text appears in anything you're about to show outside this chat (use `actions.public.md`).

## Needs my approval
Anything that leaves the bot: posting the card, sharing the action list, pushing to GitHub, emailing.
