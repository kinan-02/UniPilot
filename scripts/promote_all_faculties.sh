#!/usr/bin/env bash
# Promote all wiki-exportable Technion faculty catalogs to production MongoDB.
# Requires: docker compose stack with mongo + data-engineering service.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FACULTIES=(
  dds
  aerospace-engineering
  architecture-town-planning
  biology
  biomedical-engineering
  biotechnology-food-engineering
  chemical-engineering
  chemistry
  civil-environmental-engineering
  computer-science
  education-science-technology
  electrical-computer-engineering
  materials-science-engineering
  mathematics
  mechanical-engineering
  medicine
  physics
)

START_FROM="${1:-${START_FROM:-dds}}"

LOG_DIR="$REPO_ROOT/services/data-engineering/data/reports/technion/promotion_runs"
mkdir -p "$LOG_DIR"
RUN_LOG="$LOG_DIR/promote_all_$(date -u +%Y%m%dT%H%M%SZ).log"

run_de() {
  docker compose run --rm --no-TTY data-engineering python -m app.main "$@"
}

started=false
for faculty in "${FACULTIES[@]}"; do
  if [[ "$started" == false ]]; then
    if [[ "$faculty" != "$START_FROM" ]]; then
      continue
    fi
    started=true
  fi
  echo "========== $faculty ==========" | tee -a "$RUN_LOG"
  if [[ "$faculty" == "dds" ]]; then
    catalog_path="data/generated/technion/catalog/catalog_reviewed.json"
  else
    catalog_path="data/generated/technion/${faculty}/catalog_reviewed.json"
  fi

  echo "[export] $faculty" | tee -a "$RUN_LOG"
  run_de export-vault-catalog --faculty "$faculty" 2>&1 | tee -a "$RUN_LOG"

  echo "[staging import] $faculty" | tee -a "$RUN_LOG"
  run_de import-dds-catalog-staging --catalog-path "$catalog_path" 2>&1 | tee -a "$RUN_LOG"

  echo "[staging quality] $faculty" | tee -a "$RUN_LOG"
  run_de validate-dds-staging-quality --faculty "$faculty" 2>&1 | tee -a "$RUN_LOG"

  echo "[production promote] $faculty" | tee -a "$RUN_LOG"
  run_de promote-dds-to-production \
    --faculty "$faculty" \
    --i-confirm-dangerous-production-write \
    --allow-warnings \
    2>&1 | tee -a "$RUN_LOG"

  echo "[ok] $faculty" | tee -a "$RUN_LOG"
done

echo "All ${#FACULTIES[@]} faculties promoted. Log: $RUN_LOG"
