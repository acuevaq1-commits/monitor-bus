from src.infrastructure.database.queries.sap_inconsistencies import bp_mpl_text, material_numbers, payment_messages
from src.infrastructure.database.queries import sap_inconsistencies
from contextlib import contextmanager
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB


def test_material_numbers_collects_distinct_items():
    assert material_numbers([{"MATNR": "M1"}, {"MATNR": "M2"}, {"MATNR": "M1"}]) == "M1, M2"
    assert material_numbers({"MATNR": "M3"}) == "M3"
    assert material_numbers(None) is None


def test_payment_messages_only_uses_mensaje_field():
    failed = [{"body": '{"Codigo":"400","Mensaje":"Cuenta inválida","Detalle":"interno"}'},
        {"body": {"respuesta": {"mensaje": "Saldo insuficiente"}}}]
    assert payment_messages(failed) == "Cuenta inválida; Saldo insuficiente"
    assert payment_messages([{"body": '{"Codigo":"400"}'}]) is None


def test_bp_mpl_text_falls_back_to_run_error_when_table_row_is_missing():
    body = "The MPL ID for the failed message is : AGrJfirTsJHmejDHad1E5ROqWkR0"
    assert bp_mpl_text(None, body) == "AGrJfirTsJHmejDHad1E5ROqWkR0"
    assert bp_mpl_text({"texto_mpl_id": "Valor registrado"}, body) == "Valor registrado"
    assert bp_mpl_text(None, "Sin MPL ID") is None


def test_cargo_fields_use_requested_json_paths(monkeypatch):
    source = Table("iis_run", MetaData(), Column("ts", DateTime), Column("run_id", Integer),
        Column("queue_name", String), Column("status", String), Column("error_count", Integer),
        Column("pi_id", String), Column("summary_json", JSONB), schema="iislog")
    captured = []

    class Result:
        def mappings(self):
            return []

    class Connection:
        def scalar(self, statement):
            return 0

        def execute(self, statement):
            captured.append(statement)
            return Result()

    class Engine:
        @contextmanager
        def connect(self):
            yield Connection()

    monkeypatch.setattr(sap_inconsistencies, "table", lambda *_: source)
    monkeypatch.setattr(sap_inconsistencies, "source_engine", Engine)
    sap_inconsistencies.search(None, None, "00022")
    columns = captured[0].selected_columns
    paths = {
        "banner_00022": ["json_exec", "payload", "data", 0, "KUNNR"],
        "error_body": ["failed_items", 0, "body"],
        "fecha_audat": ["json_exec", "payload", "data", 0, "AUDAT"],
        "total_amount": ["json_exec", "payload", "data", 0, "ITEMS", 0, "ZVALORTOTAL"],
    }
    for name, expected in paths.items():
        params = columns[name].compile(dialect=postgresql.dialect()).params
        assert list(params.values()) == expected

    sap_inconsistencies.search(None, None, "00023", surrogate="SUR-23")
    payment_columns = captured[1].selected_columns
    payment_paths = {
        "banner_00023": ["json_exec", "payload", "data", 0, "PARTNER"],
        "failed_http_status": ["failed_items", 0, "status_code"],
    }
    for name, expected in payment_paths.items():
        params = payment_columns[name].compile(dialect=postgresql.dialect()).params
        assert list(params.values()) == expected
    assert "BSTKD" in payment_columns["surrogate"].compile(dialect=postgresql.dialect()).params.values()

    sap_inconsistencies.search(None, None, "00023", include_all=True, surrogate="SUR-23", bp="BP-23",
        id_banner="PARTNER-23", error_http="422", bldat="2026-09-29")
    filter_params = captured[2].whereclause.compile(dialect=postgresql.dialect()).params.values()
    for expected in ("SUR-23", "BP-23", "PARTNER-23", "422", "20260929"):
        assert expected in filter_params
