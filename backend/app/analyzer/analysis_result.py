from dataclasses import dataclass
from typing import Optional


@dataclass
class AnalysisResult:
    build_info: dict
    structure_warnings: list
    fatal_error: Optional[str]
    source_stats: dict
    test_coverage: Optional[float]
    version_warnings: list
    secrets_found: list
