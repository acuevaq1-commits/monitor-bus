from datetime import datetime, timedelta
from src.infrastructure.database.repositories.source import runs, events, dq_issues
from src.domain.services.trace_builder import build_trace
from src.infrastructure.database.queries.sap_inconsistencies import find_cpi_text, find_sent_payload, RESULT_QUEUE, INLINE_QUEUE


def get_run_trace(ts: datetime, run_id: str, detail: bool = False):
    run = runs.get_run(ts, run_id, detail=detail)
    if not run:
        return None
    filters = {"run_id": run_id}
    ev, _ = events.search(ts - timedelta(days=1), ts + timedelta(days=1), filters, 100, 0, detail=detail)
    dq, _ = dq_issues.search(ts - timedelta(days=1), ts + timedelta(days=1), filters, 100, 0, detail=detail)
    summary = run.get("summary_json") or {}
    sent = find_sent_payload(ts, run_id, detail=detail) if run.get("queue_name") == RESULT_QUEUE else None
    if run.get("queue_name") == INLINE_QUEUE:
        sent = {"run_ts": run.get("ts"), "run_id": run_id, "payload": summary.get("payload"), "match": "registro actual"}
    return {"run": run, "events": ev, "dq_issues": dq, "stages": build_trace(run, ev), "sent": sent, "sap_response": summary if run.get("queue_name") == RESULT_QUEUE else None, "cpi": find_cpi_text(ts, run_id) if detail and run.get("queue_name") == RESULT_QUEUE else None}
