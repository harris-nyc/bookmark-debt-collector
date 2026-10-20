#!/usr/bin/env bash
# Regenerate examples/sample-run from the synthetic bookmarks (safe to publish).
set -euo pipefail
cd "$(dirname "$0")/.."
python examples/make_synthetic.py
python -m bdc run \
  --input examples/sample_bookmarks.json \
  --out examples/sample-run \
  --me demo_you \
  --theme-names examples/theme_names.json \
  --state /tmp/bdc-sample-state.json \
  --cache /tmp/bdc-sample-cache.json \
  --now 2026-10-18T12:00:00Z "$@"
rm -f examples/sample-run/.cache.json examples/sample-run/state.json
