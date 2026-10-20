# Triage buckets

Every bookmark gets exactly one bucket and one next action that starts with a verb and fits in a time box.

| Bucket | Means | Typical signals | Example next action |
|---|---|---|---|
| **Install/Try** | something runnable | GitHub repo, Hugging Face model, Grok Bot template link, "pip install", "open-sourced", a tip you can apply in a tool | "Clone and run vllm-project/vllm for 15 min; keep it or archive it." |
| **Read** | a specific piece worth the time | arXiv link, linked article, long post (> 700 chars), X Article, "deep dive", "paper" | "Read the speculative decoding paper (arXiv 2211.17192): abstract, method, eval. 25 min." |
| **Learn** | a skill you meant to pick up | "how to", "guide", "course", "N tips", numbered steps | "Block one 90-minute deep-work session this week using the routine." |
| **Follow up** (with a person) | the value is a person | mentions you, quotes you, hiring, "DM me", group chats, "accounts to follow" | "DM @demo_founder_fox to get into the founders group chat." |
| **Archive** | nothing to do | news that has moved on, hot takes, jokes, your own posts, things you already acted on, dead links | "Done already: you quoted this on 2026-09-26. Unbookmark it." |

## Rule order (`triage.triage_one`)
1. Your own post → Archive ("recycle into a thread or unbookmark")
2. Mentions you → Follow up
3. People/community signals → Follow up
4. Strong how-to signal (how to, guide, tutorial, course, N tips) and no repo/paper → Learn
5. Repo / model / bot link, or "install/launch/demo"-type wording with a link → Install/Try
6. arXiv link → Read
7. Weaker learning signal with a list or link → Learn
8. Linked article or long-form → Read
9. Everything else → Archive

Then cross-bookmark rules:
- One of **your** bookmarked posts quotes or replies to this bookmark → Archive, "done already".
- This bookmark quotes **you** and was going to be archived → Follow up.

After the freshness check, rule-based actions that point at something dead are rewritten (archived repo → "read for
reference only"; deleted target → Archive). Reviewed actions keep their text and get a "Heads up" appended.

## The review pass
The rules get the bucket right most of the time but write generic actions. In Grok Bot, the bookmark-triage skill has
the model read each bookmark and write `triage_overrides.json`:

```json
{"1900000000000079190": {"category": "Read", "next_action": "Read the speculative decoding paper (arXiv 2211.17192): abstract, method, eval. 25 min."},
 "1900000000000071271": {"category": "Learn", "skill": "Deep work", "next_action": "Block one 90-minute deep-work session this week; phone in another room."}}
```

Overrides always win. `skill` (Learn only) is the short label shown on the Wrapped card.

When unsure between Read and Archive, choose Archive. The goal is a short list you'll actually finish.
