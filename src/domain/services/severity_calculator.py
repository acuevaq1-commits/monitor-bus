from src.domain.enums.severity import Severity


def severity_for(status: str | None, error_count: int | None = None) -> Severity:
    if (status or "").upper() in {"FAILED", "ERROR"}:
        return Severity.CRITICAL
    if error_count and error_count > 0:
        return Severity.HIGH
    if (status or "").upper() in {"PARTIAL", "WARNING"}:
        return Severity.MEDIUM
    return Severity.INFO
