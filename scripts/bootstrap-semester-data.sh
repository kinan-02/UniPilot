#!/usr/bin/env bash
# Copy minimal semester JSON fixtures into the local Technion raw data folder when
# the full gitignored exports are not present (fresh clone / new teammate setup).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$ROOT/services/data-engineering/data/raw/technion"
FIXTURES="$ROOT/services/data-engineering/tests/fixtures"

for name in courses_2025_200.json courses_2025_201.json courses_2025_202.json; do
  dest="$TARGET/$name"
  if [[ -f "$dest" ]]; then
    echo "OK  $name already exists"
    continue
  fi
  src="$FIXTURES/$name"
  if [[ ! -f "$src" ]]; then
    echo "SKIP $name — fixture missing at $src" >&2
    continue
  fi
  cp "$src" "$dest"
  echo "ADD $name (dev fixture — replace with full Technion export for production)"
done
