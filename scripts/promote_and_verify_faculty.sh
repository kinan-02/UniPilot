#!/usr/bin/env bash
# Re-export, stage, quality-check, promote one faculty, then verify curriculum E2E.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FACULTY="${1:?Usage: promote_and_verify_faculty.sh <faculty-id>}"
API_BASE="${API_BASE:-http://localhost:8000}"

if [[ "$FACULTY" == "dds" ]]; then
  CATALOG_PATH="data/generated/technion/catalog/catalog_reviewed.json"
else
  CATALOG_PATH="data/generated/technion/${FACULTY}/catalog_reviewed.json"
fi

run_de() {
  docker compose run --rm --no-TTY data-engineering python -m app.main "$@"
}

echo "========== promote ${FACULTY} =========="
run_de export-vault-catalog --faculty "$FACULTY"
run_de import-dds-catalog-staging --catalog-path "$CATALOG_PATH"
run_de validate-dds-staging-quality --faculty "$FACULTY"
run_de promote-dds-to-production \
  --faculty "$FACULTY" \
  --i-confirm-dangerous-production-write \
  --allow-warnings

echo "========== verify faculty-${FACULTY} =========="
python3 scripts/verify_promoted_faculty_curriculum.py \
  --base-url "$API_BASE" \
  --faculty-id "faculty-${FACULTY}"
