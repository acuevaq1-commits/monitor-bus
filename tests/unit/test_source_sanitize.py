from datetime import datetime, timezone
from src.infrastructure.database.repositories.source import sanitize, sanitize_detail


def test_sensitive_fields_and_lima_timezone():
    row = sanitize({"ts": datetime(2026, 9, 24, 5, 0, tzinfo=timezone.utc), "email": "persona@example.org", "payload": {"authorization": "Bearer secret"}})
    assert row["ts"].startswith("2026-09-24T00:00:00-05:00")
    assert row["email"] == "••••"
    assert row["payload"]["authorization"] == "••••"
    assert sanitize('{"email":"persona@example.org"}')["email"] == "••••"


def test_detail_preserves_source_values_and_masks_only_credentials():
    row = sanitize_detail({"summary_json": {"json_exec": {"payload": {"data": [{"TAXNUM": "12345678", "NAME_LAST": "PÉREZ"}]}, "url": [{"auth_endpoint": {"autenticacion": {"credenciales": {"username": "api-user", "password": "api-password"}}}}]}}})
    execution = row["summary_json"]["json_exec"]
    assert execution["payload"]["data"][0] == {"TAXNUM": "12345678", "NAME_LAST": "PÉREZ"}
    assert execution["url"][0]["auth_endpoint"]["autenticacion"]["credenciales"] == {"username": "****", "password": "****"}
