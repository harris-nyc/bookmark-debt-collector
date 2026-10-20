"""Generate examples/sample_bookmarks.json: a fully synthetic bookmark pull in
X API v2 shape (same shape the Grok Bot X connector returns).

Every author, handle, post and number here is made up. Outbound links point at
real public resources so the freshness check has something real to check
(an alive repo, archived repos, a missing repo, an arXiv paper, a 404 page).
"""
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(7)
ME = ("100", "demo_you", "You (demo)")
USERS = {
    "201": ("demo_infra_nina", "Nina (synthetic)"), "202": ("demo_recsys_raj", "Raj (synthetic)"),
    "203": ("demo_agents_ana", "Ana (synthetic)"), "204": ("demo_founder_fox", "Fox (synthetic)"),
    "205": ("demo_coach_kim", "Kim (synthetic)"), "206": ("demo_papers_pat", "Pat (synthetic)"),
    "207": ("demo_news_ned", "Ned (synthetic)"), "208": ("demo_gpu_gus", "Gus (synthetic)"),
}
NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)

# (author_id, days_ago, text, [links], quoted_id or None)
POSTS = [
    ("201", 3, "vLLM's new chunked prefill + prefix caching cut our p99 TTFT by 38% on long prompts. Config and benchmark script in the repo, try it on your own traffic.", ["https://github.com/vllm-project/vllm"], None),
    ("208", 5, "llama.cpp now runs a 70B model at usable speed on a single workstation GPU with partial offload. Install guide in the README, takes 10 minutes.", ["https://github.com/ggml-org/llama.cpp"], None),
    ("206", 9, "Paper thread: the original Transformer paper is still the best 30-minute read on attention. Read the paper, then the illustrated guide.", ["https://arxiv.org/abs/1706.03762", "https://jalammar.github.io/illustrated-transformer/"], None),
    ("202", 12, "How we rebuilt candidate retrieval: two-tower model, ANN index in FAISS, then a light re-ranker. Long thread with the exact feature list and the offline/online metric gap we saw.", ["https://github.com/facebookresearch/faiss"], None),
    ("203", 14, "Agents guide: planning, memory and tool use explained, with the failure modes nobody mentions. Bookmark this and work through it section by section.", ["https://lilianweng.github.io/posts/2023-06-23-agent/"], None),
    ("204", 16, "We're hiring two inference engineers in NYC. DM me if you've shipped speculative decoding or KV-cache work in prod.", [], None),
    ("207", 20, "Big lab announces 2x cheaper API prices across the board, effective Monday.", [], None),
    ("100", 22, "Hot take: most recsys teams still can't put a real LLM in the online path because latency budgets are 50ms. Fast inference changes that.", [], None),
    ("202", 25, "@demo_you agree on the latency budget point. Would love to compare notes on what you'd cut first from the ranking stack.", [], "Q8"),
    ("205", 30, "7 tips for deep work: 1. one tab 2. phone in another room 3. 90-minute blocks 4. write the next step before you stop 5. same time daily 6. no meetings before noon 7. log what you shipped", [], None),
    ("206", 34, "Speculative decoding explained: a small model drafts, the big one verifies. Here's the math and a toy implementation you can run.", ["https://arxiv.org/abs/2211.17192"], None),
    ("201", 40, "Our team open-sourced the KV-cache eviction experiments. Repo is up, results table inside. pip install and run the benchmark.", ["https://github.com/demo-nonexistent-org-xyz/agent-thing"], None),
    ("208", 46, "GPU prices are down again this month. Spot H100s at record lows.", [], None),
    ("203", 52, "Long read: what actually breaks when you give an agent a browser and a credit card. Lessons from three months of evals.", [], None),
    ("204", 60, "Startup lesson: talk to users before you write code. Every single time.", [], None),
    ("207", 66, "Breaking: another frontier model launch today, benchmarks look strong.", [], None),
    ("202", 75, "Recsys course I wish I had: embeddings, retrieval, ranking, calibration, explore/exploit. Free, with notebooks.", ["https://github.com/huggingface/transformers"], None),
    ("205", 90, "Learn to cook 5 dinners this year. Here's the step-by-step guide I gave my brother.", [], None),
    ("206", 110, "BERT is old but the repo is still the cleanest reference implementation of pretraining.", ["https://github.com/google-research/bert"], None),
    ("201", 130, "Reminder: GPT-2's original code is a great way to learn how sampling works. Clone it and read sample.py.", ["https://github.com/openai/gpt-2"], None),
    ("204", 150, "Founders: write the launch post before you build. If it's boring, don't build it.", [], None),
    ("203", 170, "This thread is the best explanation of tool calling I've seen.", [], "Q_DEAD"),
    ("208", 200, "Swift for TensorFlow was a fascinating experiment. Repo still up if you want to learn from it.", ["https://github.com/tensorflow/swift"], None),
    ("205", 230, "How to run your first 10k: a 12-week plan. Save this.", [], None),
    ("207", 260, "Market reacts to chip export news, semis down 4%.", [], None),
    ("206", 300, "nanoGPT is still the fastest way to understand training a GPT from scratch. Clone it, train on Shakespeare in 5 minutes.", ["https://github.com/karpathy/nanoGPT"], None),
    ("202", 340, "Great blog post on calibration for ranking models, worth reading if you own a CTR model.", ["https://example.com/this-page-was-deleted"], None),
    ("204", 380, "Join our founders group chat for builders shipping AI products. Reply and I'll add you.", [], None),
    ("205", 420, "Morning routine that finally stuck for me: walk, water, write. That's it.", [], None),
    ("201", 470, "Quantization guide: int8 vs int4 vs fp8 for inference, explained with benchmarks.", ["https://huggingface.co/BAAI/bge-small-en-v1.5"], None),
    ("207", 520, "Viral AI photo filter trend takes over the timeline this weekend.", [], None),
    ("206", 560, "If you only read one RL paper this year, make it this one. Thread with the key figures.", [], None),
]


def sid(i):
    return str(1900000000000000000 + i * 7919)


def main():
    data, inc_posts, users = [], [], []
    users.append({"id": ME[0], "username": ME[1], "name": ME[2], "public_metrics": {"followers_count": 1200}})
    for uid, (u, n) in USERS.items():
        users.append({"id": uid, "username": u, "name": n, "public_metrics": {"followers_count": random.randint(800, 90000)},
                      "description": "Synthetic account for the Bookmark Debt Collector demo."})
    ids = {f"Q{i+1}": sid(i) for i in range(len(POSTS))}
    errors = []
    # Bookmark order: roughly most-recently-bookmarked first (we use post age as a proxy)
    for i, (uid, days, text, links, quoted) in enumerate(POSTS):
        pid = sid(i)
        uname = ME[1] if uid == ME[0] else USERS[uid][0]
        created = (NOW - timedelta(days=days, hours=random.randint(0, 20))).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        ents = {"urls": [{"url": f"https://t.co/demo{i}{j}", "expanded_url": l, "display_url": l.split('//')[1][:24]}
                         for j, l in enumerate(links)]}
        mentions = [m for m in ["demo_you"] if "@" + m in text]
        if mentions:
            ents["mentions"] = [{"username": m, "id": ME[0]} for m in mentions]
        imp = random.randint(3000, 400000)
        p = {"id": pid, "author_id": uid, "created_at": created, "text": text, "lang": "en",
             "url": f"https://x.com/{uname}/status/{pid}", "entities": ents,
             "public_metrics": {"impression_count": imp, "like_count": imp // random.randint(40, 120),
                                "bookmark_count": imp // random.randint(60, 400), "repost_count": imp // 900, "reply_count": imp // 1500, "quote_count": imp // 5000}}
        if quoted == "Q_DEAD":
            p["referenced_tweets"] = [{"type": "quoted", "id": "1899999999999999999"}]
            errors.append({"resource_id": "1899999999999999999", "title": "Not Found Error", "type": "https://api.x.com/2/problems/resource-not-found",
                           "detail": "Could not find post with referenced_tweets.id: [1899999999999999999]."})
        elif quoted:
            p["referenced_tweets"] = [{"type": "quoted", "id": ids[quoted]}]
            q = POSTS[int(quoted[1:]) - 1]
            inc_posts.append({"id": ids[quoted], "author_id": q[0], "text": q[2]})
        data.append(p)
    out = {"data": data, "includes": {"users": users, "posts": inc_posts}, "errors": errors,
           "meta": {"result_count": len(data), "note": "SYNTHETIC DATA: every account, post and metric is invented."}}
    path = Path(__file__).with_name("sample_bookmarks.json")
    path.write_text(json.dumps(out, indent=1))
    print(f"wrote {path} ({len(data)} synthetic bookmarks)")


if __name__ == "__main__":
    main()
