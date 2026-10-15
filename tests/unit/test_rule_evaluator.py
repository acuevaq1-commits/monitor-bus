from datetime import datetime, timedelta, timezone
from src.domain.services.rule_evaluator import evaluate_run, evaluate_related


def test_failure_and_counter_findings_keep_composite_key():
    ts = datetime.now(timezone.utc) - timedelta(minutes=50)
    found = evaluate_run({"ts": ts, "run_id": "r1", "pi_id": "00021", "status": "FAILED", "executed": 4, "ok_count": 2, "error_count": 1, "total": 4, "corr_id": "no-corr-id"}, datetime.now(timezone.utc))
    assert {x.category for x in found} >= {"Ejecuciones fallidas", "Contadores inconsistentes", "Trazabilidad del log"}
    assert all(x.run_ts == ts and x.run_id == "r1" for x in found)


def test_started_threshold():
    ts = datetime.now(timezone.utc) - timedelta(minutes=31)
    found = evaluate_run({"ts": ts, "run_id": "r2", "status": "STARTED", "corr_id": "c"}, datetime.now(timezone.utc))
    assert any(x.category == "Ejecuciones bloqueadas" for x in found)


def test_sap_error_and_related_evidence():
    now = datetime.now(timezone.utc)
    run = {"ts": now - timedelta(seconds=5), "run_id": "r3", "pi_id": "00022", "status": "SUCCESS", "corr_id": "c", "http_status": 200, "response_json": {"messages": [{"type": "E"}]}}
    found = evaluate_run(run, now)
    assert any(x.category == "Errores funcionales SAP" for x in found)
    related = evaluate_related(run, [{"level": "ERROR"}], [{"severity": "critica"}], now)
    assert {x.category for x in related} == {"Trazabilidad del log", "Calidad de datos"}
