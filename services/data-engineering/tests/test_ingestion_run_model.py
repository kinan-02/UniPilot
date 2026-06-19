from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.ingestion_run import IngestionRun


def test_ingestion_run_accepts_required_fields():
    run = IngestionRun(
        sourceName="synthetic-dds-sample",
        sourceType="manual_sample",
        status="running",
        startedAt=datetime.now(timezone.utc),
    )

    assert run.itemsRead == 0
    assert run.errors == []


def test_ingestion_run_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        IngestionRun.model_validate(
            {
                "sourceName": "sample",
                "sourceType": "manual_sample",
                "status": "running",
                "startedAt": datetime.now(timezone.utc).isoformat(),
                "unexpected": True,
            }
        )
