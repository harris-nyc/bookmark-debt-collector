"""Offline smoke test: runs the full pipeline on the synthetic sample with no
network (freshness falls back to X's unfurl hints) and checks the outputs."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
    out = Path(d) / "out"
    cmd = [sys.executable, "-m", "bdc", "run", "--input", str(ROOT / "examples/sample_bookmarks.json"), "--out", str(out),
           "--me", "demo_you", "--offline", "--cluster-backend", "tfidf", "--now", "2026-10-18T12:00:00Z",
           "--state", str(Path(d) / "state.json")] + (["--no-png"] if "--no-png" in sys.argv else [])
    subprocess.run(cmd, check=True, cwd=ROOT)
    recs = json.loads((out / "bookmarks.normalized.json").read_text())
    tri = json.loads((out / "triage.json").read_text())
    stats = json.loads((out / "wrapped.json").read_text())
    assert len(recs) == 32, len(recs)
    assert set(tri) == {r["id"] for r in recs}
    assert sum(stats["categories"].values()) == 32
    assert stats["self_bookmarks"] == 1
    assert any(q["status"] == "not_found" for r in recs for q in r["quoted"]), "deleted quote not detected"
    assert "Follow up" in {v["category"] for v in tri.values()}
    assert (out / "actions.md").read_text().count("- [ ]") == 32
    assert (out / "resurface.md").read_text().count("Next action:") == 3
    # decide flow
    st = Path(d) / "state.json"
    subprocess.run([sys.executable, "-m", "bdc", "decide", "--state", str(st), "1", "snooze"], check=True, cwd=ROOT)
    assert len(json.loads(st.read_text())["decisions"]) == 1
    if "--no-png" not in sys.argv:
        assert (out / "card.png").stat().st_size > 50_000

    # Grok Bot path: plugin-shaped pages -> bdc ingest -> same records as the one-file sample
    pulls, arch = Path(d) / "pulls", Path(d) / "archive.json"
    subprocess.run([sys.executable, "examples/simulate_mcp_pull.py", str(pulls)], check=True, cwd=ROOT, capture_output=True)
    pages = sorted(pulls.glob("page-*.txt"), key=lambda p: int(p.stem.split("-")[1]))
    nxt = ""
    for pg in pages:
        nxt = subprocess.run([sys.executable, "-m", "bdc", "ingest", str(pg), "--archive", str(arch)], check=True, cwd=ROOT,
                             capture_output=True, text=True).stdout
    assert "NEXT: done" in nxt, nxt
    again = subprocess.run([sys.executable, "-m", "bdc", "ingest", str(pages[0]), "--archive", str(arch)], check=True,
                           cwd=ROOT, capture_output=True, text=True).stdout
    assert "NEXT: stop" in again and "0 new" in again, again
    sys.path.insert(0, str(ROOT / "src"))
    from bdc import normalize  # noqa: E402
    assert [r["id"] for r in normalize.load(arch)] == [r["id"] for r in recs]

# privacy filter: keyword, deleted-quote siblings, sensitive themes
sys.path.insert(0, str(ROOT / "src"))
from bdc.privacy import PrivacyFilter  # noqa: E402
gone = {"id": "q1", "type": "quoted", "status": "not_found", "text": ""}
recs = [
    {"id": "a", "text": "you never really get over her", "quoted": [gone], "links": []},
    {"id": "b", "text": "a smell, a song, there it is again", "quoted": [gone], "links": []},
    {"id": "c", "text": "new inference kernel, 2x faster", "quoted": [], "links": []},
    {"id": "d", "text": "morning skin routine", "quoted": [], "links": []},
]
themes = [{"id": 0, "terms": ["inference"], "members": ["c"]}, {"id": 1, "terms": ["skin", "routine"], "members": ["d"]}]
pf = PrivacyFilter(recs, clusters=themes, names={"0": "Inference", "1": "Health & self-improvement"})
assert pf(recs[0]) and pf(recs[1]), "deleted-quote sibling not flagged"
assert not pf(recs[2]) and pf(recs[3]), pf.reasons
assert set(pf.hidden_themes) == {"1"}, pf.hidden_themes
print("selftest OK")
