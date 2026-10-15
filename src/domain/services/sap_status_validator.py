"""Interpret the outer run status and the nested SAP execution result."""

SUCCESS = {"OK", "SUCCESS", "COMPLETED", "FINISHED"}
FAILURE = {"ERROR", "FAILED"}


def classify_status(run_status: str | None, json_status: str | None, http_status: str | int | None, failed_items: int = 0, error_count: int | None = None, failed_status_code: str | int | None = None) -> dict | None:
    outer = str(run_status or "").upper()
    inner = str(json_status or "").upper()
    try:
        http = int(http_status) if http_status is not None else None
    except (ValueError, TypeError):
        http = None
    try:
        inner_code = int(inner)
    except ValueError:
        inner_code = None
    try:
        item_code = int(failed_status_code) if failed_status_code is not None else None
    except (ValueError, TypeError):
        item_code = None
    item_severity = "critica" if item_code is not None and item_code >= 500 else "alta"
    if failed_items > 0:
        return {"kind": "Ítems rechazados por SAP", "severity": item_severity, "explanation": "El transporte terminó, pero failed_items contiene un rechazo de SAP. Los estados de ejecución y HTTP no indican el resultado del BP."}
    if outer in SUCCESS and (inner in FAILURE or (inner_code is not None and inner_code >= 400) or (http is not None and http >= 400)):
        return {"kind": "Run exitoso con respuesta SAP fallida", "severity": "critica", "explanation": "El estado de la ejecución indica éxito, pero el resultado interno o HTTP indica error."}
    if outer in FAILURE and (inner in SUCCESS or (inner_code is not None and 200 <= inner_code < 300) or (http is not None and 200 <= http < 300)):
        if (error_count or 0) > 0:
            return {"kind": "HTTP exitoso con errores funcionales", "severity": item_severity, "explanation": "La llamada respondió correctamente, pero hay registros rechazados o errores funcionales."}
        return {"kind": "Run fallido con respuesta SAP exitosa", "severity": "alta", "explanation": "El estado de la ejecución indica error y la respuesta interna indica éxito, sin fallos de ítems registrados."}
    return None
