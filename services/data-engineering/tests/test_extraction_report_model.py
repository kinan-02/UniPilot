from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.extraction_report import ExtractionReport


def test_extraction_report_accepts_required_fields():
    report = ExtractionReport(
        sourceFile="/tmp/sample.pdf",
        sourceType="technion_dds_catalog_pdf",
        pageCount=13,
        extractedPageCount=13,
        totalCharacters=56000,
        averageCharactersPerPage=4307.69,
        lowTextPages=[],
        extractionWarnings=[],
        extractorName="pypdf",
        createdAt=datetime.now(timezone.utc),
        outputDirectory="data/generated/technion/dds_catalog",
    )

    assert report.pageCount == 13


def test_extraction_report_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ExtractionReport.model_validate(
            {
                "sourceFile": "/tmp/sample.pdf",
                "sourceType": "technion_dds_catalog_pdf",
                "pageCount": 1,
                "extractedPageCount": 1,
                "totalCharacters": 10,
                "averageCharactersPerPage": 10.0,
                "extractorName": "pypdf",
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "outputDirectory": "data/generated/technion/dds_catalog",
                "unexpected": True,
            }
        )
