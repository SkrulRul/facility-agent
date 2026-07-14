"""Manual, one-off smoke test against the REAL Anthropic API.

Not part of `uv run poe check`. Costs real API credits. Run manually:
    uv run python scripts/smoke_test_extraction.py

Requires ANTHROPIC_API_KEY set in .env (see app/config.py).
"""
import asyncio
from pathlib import Path

from app.config import ExtractionSettings
from app.extraction_targets.covenant_waiver import CovenantWaiverNotice
from app.extraction_targets.term_sheet import TermSheetExtract
from app.services.extraction_service import build_extraction_service

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"

async def main() -> None:
    settings = ExtractionSettings()  # reads real ANTHROPIC_API_KEY from .env
    service = build_extraction_service(settings)

    term_sheet_text = (FIXTURES / "term_sheet_excerpt.txt").read_text()
    result1 = await service.extract(term_sheet_text, TermSheetExtract)
    print("TermSheetExtract:", result1)

    waiver_text = (FIXTURES / "covenant_waiver_letter.txt").read_text()
    result2 = await service.extract(waiver_text, CovenantWaiverNotice)
    print("CovenantWaiverNotice:", result2)

if __name__ == "__main__":
    asyncio.run(main())