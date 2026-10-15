import os
os.environ.setdefault("MONITOR_ADMIN_PASSWORD", "test-password")
os.environ.setdefault("MONITOR_SESSION_SECRET", "test-secret")

from fastapi.testclient import TestClient
from src.main import app
from html import unescape
from io import BytesIO
from zipfile import ZipFile
import re
from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlsplit

from src.presentation.web.routes import pages


def test_failed_attempt_cards_and_detail(monkeypatch):
    monkeypatch.setattr(pages, "failed_attempts_summary", lambda *args: {
        "00021": {"pi_id": "00021", "name": "Nuevos BP fallidos", "attempts": 7, "identifiers": 3, "identifier_label": "ID BANNER"},
        "00022": {"pi_id": "00022", "name": "Cargos", "attempts": 5, "identifiers": 2, "identifier_label": "ID BANNER"},
        "00023": {"pi_id": "00023", "name": "Pagos", "attempts": 3, "identifiers": 1, "identifier_label": "ID BANNER"},
    })
    calls = []

    def fake_detail(pi_id, page, min_attempts, start, end):
        calls.append((pi_id, page, min_attempts, start, end))
        return {"source_available": True, "has_next": True, "items": [{
            "identifier": "BP-7" if pi_id == "00021" else "SUR-7", "total_intentos_fallidos": 2, "total_por_identificador": 5,
            "fecha_error": date(2026, 10, 8),
            "error_body": "Pedido rechazado",
        }]}

    monkeypatch.setattr(pages, "failed_attempts_detail", fake_detail)
    monkeypatch.setattr(pages, "export_failed_attempt_rows", lambda *args: iter(fake_detail(args[0], 1, args[1], args[2], args[3])["items"]))
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        incidents = client.get("/incidents?date_from=2026-10-08&date_to=2026-10-08")
        assert incidents.status_code == 200
        assert "Intentos fallidos" in incidents.text
        assert 'Monitor de Integraciones Banner–SAP<span class="fw-normal text-muted"> / Intentos fallidos</span>' in incidents.text
        assert '<h1 class="h3 m-0">Intentos fallidos</h1>' not in incidents.text
        assert '<h2 class="h5 mb-3">Intentos fallidos</h2>' not in incidents.text
        assert 'href="/incidents/failed-attempts/00021?date_from=2026-10-08&amp;date_to=2026-10-08"' in incidents.text
        assert 'href="/incidents/failed-attempts/00022?date_from=2026-10-08&amp;date_to=2026-10-08"' in incidents.text
        assert 'href="/incidents/failed-attempts/00023?date_from=2026-10-08&amp;date_to=2026-10-08"' in incidents.text
        assert "Incidentes de reglas" not in incidents.text
        detail = client.get("/incidents/failed-attempts/00022?page=2&min_attempts=5&date_from=2026-10-08&date_to=2026-10-08")
        assert detail.status_code == 200 and [call[:3] for call in calls] == [("00022", 2, 5)]
        assert "Pedido rechazado" in detail.text and "SUR-7" in detail.text
        assert 'href="/payloads?pi_id=00022&amp;bp=SUR-7&amp;date_from=2026-10-08&amp;date_to=2026-10-08&amp;view=all"' in detail.text
        assert "Veces del mismo error" in detail.text and "Intentos fallidos del día" in detail.text
        assert "Página 2" in detail.text and "min_attempts=5&amp;page=3" in detail.text
        assert 'href="/incidents/failed-attempts/00022/export?date_from=2026-10-08&amp;date_to=2026-10-08&amp;min_attempts=5"' in detail.text
        assert 'Monitor de Integraciones Banner–SAP<span class="fw-normal text-muted"> / Cargos · Intentos fallidos</span>' in detail.text
        assert '<h1 class="h3 m-0">Cargos · Intentos fallidos</h1>' not in detail.text
        assert '<div class="incident-error-message">Pedido rechazado</div>' in detail.text
        assert 'class="badge text-bg-primary"' not in detail.text
        assert 'name="min_attempts"' in detail.text
        bp_detail = client.get("/incidents/failed-attempts/00021?min_attempts=5&date_from=2026-10-08&date_to=2026-10-08")
        assert bp_detail.status_code == 200
        assert 'href="/payloads?pi_id=00021&amp;q=BP-7&amp;date_from=2026-10-08&amp;date_to=2026-10-08&amp;view=all"' in bp_detail.text
        payment_detail = client.get("/incidents/failed-attempts/00023?date_from=2026-10-08&date_to=2026-10-08")
        assert payment_detail.status_code == 200
        assert [call[:3] for call in calls] == [("00022", 2, 5), ("00021", 1, 5), ("00023", 1, 1)]
        assert all(call[3:] == (datetime(2026, 10, 8, 5, tzinfo=timezone.utc), datetime(2026, 10, 9, 5, tzinfo=timezone.utc)) for call in calls)
        exported = client.get("/incidents/failed-attempts/00021/export?date_from=2026-10-08&date_to=2026-10-08&min_attempts=5")
        assert exported.status_code == 200
        assert 'filename="intentos_fallidos_00021.xlsx"' in exported.headers["content-disposition"]
        with ZipFile(BytesIO(exported.content)) as archive:
            sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "08/10/2026" in sheet and "BP-7" in sheet and "Pedido rechazado" in sheet
        assert "Veces del mismo error" in sheet and "Intentos fallidos del día" in sheet
        assert client.get("/incidents/failed-attempts/00022?min_attempts=0").status_code == 422
        assert client.get("/incidents/failed-attempts/00024").status_code == 404
        assert client.get("/incidents?date_from=2026-10-09&date_to=2026-10-08").status_code == 422
        assert client.get("/incidents/failed-attempts/00022/export?date_from=2026-10-09&date_to=2026-10-08").status_code == 422


def test_payload_topbar_uses_integration_names(monkeypatch):
    monkeypatch.setattr(pages, "search_sap_inconsistencies", lambda *args, **kwargs: {
        "source_available": True, "items": [], "total": 0, "has_next": False,
    })
    monkeypatch.setattr(pages.runs, "latest_within", lambda *args, **kwargs: None)
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        for pi_id, label in (("00021", "Business Partner"), ("00022", "Pedidos de Venta"), ("00023", "Pagos")):
            response = client.get("/payloads", params={"pi_id": pi_id})
            assert response.status_code == 200
            assert f'Monitor de Integraciones Banner–SAP<span class="fw-normal text-muted"> / {label}</span>' in response.text


def test_common_errors_page_filters_dates_and_links_cpi(monkeypatch):
    run_ts = datetime(2026, 10, 8, 15, tzinfo=timezone.utc)
    calls = []

    def fake_search(start, end, page):
        calls.append((start, end, page))
        return {"source_available": True, "has_next": True, "items": [
            {"ts": run_ts, "run_id": 99, "message": "Revisar log de CPI"},
            {"ts": run_ts, "run_id": 100, "message": "Pedido rechazado"},
        ]}

    monkeypatch.setattr(pages, "search_common_errors", fake_search)
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        response = client.get("/common-errors?date_from=2026-10-08&date_to=2026-10-08&page=2")
        assert response.status_code == 200
        assert 'href="/common-errors"' in response.text
        assert "Fecha (Lima)" in response.text and "Mensaje de error" in response.text
        assert "Pedido rechazado" in response.text
        assert 'name="date_from" value="2026-10-08"' in response.text
        assert 'name="date_to" value="2026-10-08"' in response.text
        assert 'tab=cpi&amp;return_to=' in response.text
        assert "date_to=2026-10-08&amp;page=3" in response.text
        assert calls == [(datetime(2026, 10, 8, 5, tzinfo=timezone.utc),
                          datetime(2026, 10, 9, 5, tzinfo=timezone.utc), 2)]
        assert client.get("/common-errors?date_from=2026-10-09&date_to=2026-10-08").status_code == 422


def test_operational_incident_cards_and_details(monkeypatch):
    monkeypatch.setattr(pages, "operational_summary", lambda inactivity_hours: {
        "stuck": {"name": "Ejecuciones bloqueadas", "count": 2},
        "sap": {"name": "Errores funcionales SAP", "count": 3},
        "inactive": {"name": "Sin ejecuciones recientes", "count": 1},
    })
    monkeypatch.setattr(pages, "failed_attempts_summary", lambda *args: {
        pi_id: {"name": name, "attempts": 0, "identifiers": 0, "identifier_label": "ID BANNER"}
        for pi_id, name in pages.FAILED_ATTEMPT_PI.items()
    })
    calls = []

    def fake_detail(kind, page, inactivity_hours):
        calls.append((kind, page, inactivity_hours))
        if kind == "inactive":
            items = [{"pi_id": "00023", "flow_name": "Pagos", "last_ts": None, "hours_without_results": None}]
        elif kind == "stuck":
            items = [{"pi_id": "00022", "flow_name": "Cargos", "ts": "2026-10-08T15:00:00+00:00", "run_id": "7", "queue_name": "result", "minutes_elapsed": 42}]
        else:
            items = [{"pi_id": "00021", "flow_name": "Nuevos BP", "ts": "2026-10-08T15:00:00+00:00", "run_id": "8", "status": "OK", "json_status": "ERROR", "http_status": "400", "error_body": "Rechazo SAP"}]
        return {"source_available": True, "items": items, "has_next": kind != "inactive"}

    monkeypatch.setattr(pages, "operational_detail", fake_detail)
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        home = client.get("/incidents")
        assert home.status_code == 200
        for kind in ("stuck", "sap", "inactive"):
            assert f'href="/incidents/{kind}"' in home.text
        stuck = client.get("/incidents/stuck?page=2")
        assert stuck.status_code == 200 and "42" in stuck.text and "page=3" in stuck.text
        sap = client.get("/incidents/sap")
        assert sap.status_code == 200 and "Rechazo SAP" in sap.text
        inactive = client.get("/incidents/inactive")
        assert inactive.status_code == 200 and "Sin registros" in inactive.text
        assert [call[:2] for call in calls] == [("stuck", 2), ("sap", 1), ("inactive", 1)]
        assert client.get("/incidents/unknown").status_code == 404


def test_health_login_and_empty_source():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        redirect = client.get("/", follow_redirects=False)
        assert redirect.status_code == 303
        assert redirect.headers["location"] == "/login"
        assert "Inicie sesión" in client.get("/").text
        assert client.get("/api/v1/runs").status_code == 401
        assert client.post("/login", data={"username": "admin", "password": "test-password"}).status_code == 200
        assert "Sin fuente de datos" in client.get("/").text
        assert client.get("/api/v1/dashboard/failure-categories").json()[0]["count"] is None
        templates = client.get("/config/templates")
        assert templates.status_code == 200
        assert 'data-column-order="pi_id,pi_nombre,pi_descripcion,pi_ind_estado,pi_fecha_actividad,pi_metadata"' in templates.text
        assert 'id="template-column-options"' in templates.text
        assert 'id="sidebar-hide"' not in templates.text


def test_api_mutation_requires_csrf_and_payload_rules_are_separate():
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        assert client.post("/api/v1/payloads/analyze", json={"pi_id": "00021", "payload": {}}).status_code == 403
        html = client.get("/").text
        csrf = re.search(r'<meta name="csrf-token" content="([^"]+)"', html).group(1)
        response = client.post("/api/v1/payloads/analyze", json={"pi_id": "00021", "payload": {}}, headers={"X-CSRF-Token": csrf})
        assert response.status_code == 200
        assert response.json()["items"][0]["path"] == "data.person.wnrodoc"


def test_dashboard_date_range_and_integration_combo(monkeypatch):
    calls = []
    def fake_summary(start, end, filters):
        calls.append((start, end, filters))
        return {"source_available": True, "cards": {}, "statuses": {}, "recent": [], "no_activity_24h": False}
    monkeypatch.setattr(pages, "get_dashboard_summary", fake_summary)
    monkeypatch.setattr(pages, "summarize_categories", lambda *args, **kwargs: [])
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        calls.clear()
        response = client.get("/", params={"date_from": "2026-09-01", "date_to": "2026-09-02", "pi_id": "00022"})
        assert response.status_code == 200
        assert calls == [(datetime(2026, 9, 1, 5, tzinfo=timezone.utc), datetime(2026, 9, 3, 5, tzinfo=timezone.utc), {"pi_id": "00022", "status": None})]
        assert 'name="date_from" type="date" value="2026-09-01"' in response.text
        assert 'name="date_to" type="date" value="2026-09-02"' in response.text
        assert '<option value="00022" selected>00022 - Pedidos de venta</option>' in response.text
        assert 'class="card card-body mb-4 filterbar"' not in response.text
        assert 'name="hours"' not in response.text
        assert '/runs?date_from=2026-09-01&amp;date_to=2026-09-02&amp;pi_id=00022' in response.text
        assert client.get("/", params={"date_from": "2026-09-01"}).status_code == 422
        assert client.get("/", params={"date_from": "2026-09-03", "date_to": "2026-09-02"}).status_code == 422


def test_dashboard_range_reaches_runs_and_survives_pagination(monkeypatch):
    calls = []
    def fake_search(start, end, filters, limit, offset):
        calls.append((start, end, filters, limit, offset))
        return [], 101
    monkeypatch.setattr(pages, "search_runs", fake_search)
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        response = client.get("/runs", params={"date_from": "2026-09-01", "date_to": "2026-09-02", "pi_id": "00022", "page": 2})
        assert response.status_code == 200
        assert calls[-1] == (datetime(2026, 9, 1, 5, tzinfo=timezone.utc), datetime(2026, 9, 3, 5, tzinfo=timezone.utc), {"pi_id": "00022", "status": None, "queue_name": None}, 50, 50)
        assert 'date_from=2026-09-01&amp;date_to=2026-09-02&amp;pi_id=00022&amp;page=3' in response.text


def test_runs_and_events_hide_filters_and_payload_menu_omits_inconsistencies(monkeypatch):
    monkeypatch.setattr(pages, "search_runs", lambda *args: ([], 51))
    monkeypatch.setattr(pages.events, "search", lambda *args: ([], 51))
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        for path in ("/runs", "/events"):
            response = client.get(path)
            assert response.status_code == 200
            assert 'class="card card-body mb-3 filterbar"' not in response.text
            assert 'name="hours"' not in response.text
            assert 'name="date_from"' not in response.text
            assert "Siguiente" in response.text
            assert '<a href="/payloads">Inconsistencias</a>' not in response.text
            assert '<a href="/payloads?pi_id=00021">00021 - BP</a>' in response.text


def test_payload_date_range_filters_and_survives_navigation(monkeypatch):
    calls = []

    def fake_search(start, end, pi_id, limit, offset, **kwargs):
        calls.append((start, end, pi_id, offset, kwargs))
        return {"source_available": True, "items": [], "total": None if start is None and not kwargs.get("force_count") else 40, "has_next": start is None}

    monkeypatch.setattr(pages, "search_sap_inconsistencies", fake_search)
    monkeypatch.setattr(pages.runs, "latest_within", lambda *args, **kwargs: None)
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        params = {"pi_id": "00021", "date_from": "2026-09-01", "date_to": "2026-09-02", "q": "error"}
        response = client.get("/payloads", params=params)
        assert response.status_code == 200
        assert calls[0][:4] == (
            datetime(2026, 9, 1, 5, tzinfo=timezone.utc),
            datetime(2026, 9, 3, 5, tzinfo=timezone.utc),
            "00021",
            0,
        )
        assert 'name="date_from" type="date" class="form-control" value="2026-09-01"' in response.text
        assert 'date_from=2026-09-01&amp;date_to=2026-09-02' in response.text
        assert 'view=all' in response.text
        assert 'page=2' in response.text
        assert 'page=3">Ir al último registro</a>' in response.text

        calls.clear()
        text_only = client.get("/payloads", params={"pi_id": "00021", "q": "B123", "date_from": "", "date_to": ""})
        assert text_only.status_code == 200
        assert calls[0][0:3] == (None, None, "00021")
        assert calls[0][4]["query"] == "B123"
        assert "sin límite de fechas" in text_only.text
        assert 'page=2' in text_only.text
        assert 'last=1">Ir al último registro</a>' in text_only.text

        calls.clear()
        last_page = client.get("/payloads", params={"pi_id": "00021", "q": "B123", "last": "1"})
        assert last_page.status_code == 200
        assert calls[0][4]["force_count"] is True
        assert any(call[3] == 30 for call in calls)
        assert "Página 3 de 3" in last_page.text
        assert 'page=1">Ir al primer registro</a>' in last_page.text

        calls.clear()
        dates_only = client.get("/payloads", params={"pi_id": "00021", "date_from": "2026-09-01", "date_to": "2026-09-02", "q": ""})
        assert dates_only.status_code == 200
        assert calls[0][0:3] == (datetime(2026, 9, 1, 5, tzinfo=timezone.utc), datetime(2026, 9, 3, 5, tzinfo=timezone.utc), "00021")
        assert calls[0][4]["query"] == ""

        assert client.get("/payloads", params={"date_from": "2026-09-02", "date_to": "2026-09-01"}).status_code == 422
        assert client.get("/payloads", params={"date_from": "2026-09-01"}).status_code == 422
        assert client.get("/payloads", params={"date_from": "no-es-fecha", "date_to": "2026-09-02"}).status_code == 422


def test_payload_excel_exports_filtered_rows_beyond_first_page(monkeypatch):
    calls = []

    def fake_search(start, end, pi_id, limit, offset, **kwargs):
        calls.append((start, end, pi_id, limit, offset, kwargs))
        items = [{"run_id": str(n), "texto_mpl_id": f"MPL-{n}", "texto_legible": f"Mensaje {n}"}
                 for n in range(offset, min(offset + limit, 201))]
        return {"items": items, "has_next": offset + limit < 201}

    monkeypatch.setattr(pages, "search_sap_inconsistencies", fake_search)
    with TestClient(app) as client:
        assert client.get("/payloads/export?pi_id=00021", follow_redirects=False).status_code == 303
        client.post("/login", data={"username": "admin", "password": "test-password"})
        response = client.get("/payloads/export", params={"pi_id": "00021", "date_from": "2026-09-01", "date_to": "2026-09-02", "q": "B123"})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        assert 'filename="payloads_00021.xlsx"' in response.headers["content-disposition"]
        with ZipFile(BytesIO(response.content)) as archive:
            sheet = archive.read("xl/worksheets/sheet1.xml").decode()
        assert "MPL-ID" in sheet and "Mensaje CPI" in sheet
        assert "Interpretación" not in sheet
        assert "MPL-200" in sheet and "Mensaje 200" in sheet
        assert sheet.count("<row ") == 202
        assert [call[4] for call in calls] == [0, 200]
        assert all(call[5]["query"] == "B123" and call[5]["count_total"] is False for call in calls)
        for pi_id, expected_header in [("00022", "ZVALORTOTAL (Monto)"), ("00023", "WRBTR (Monto)")]:
            other = client.get("/payloads/export", params={"pi_id": pi_id})
            assert other.status_code == 200
            with ZipFile(BytesIO(other.content)) as archive:
                other_sheet = archive.read("xl/worksheets/sheet1.xml").decode()
                assert expected_header in other_sheet
                assert "Interpretación" not in other_sheet
            assert f'filename="payloads_{pi_id}.xlsx"' in other.headers["content-disposition"]
        assert client.get("/payloads/export", params={"pi_id": "00024"}).status_code == 422


def test_payload_excel_choice_limits_to_500_or_exports_all(monkeypatch):
    calls = []

    def fake_search(start, end, pi_id, limit, offset, **kwargs):
        calls.append((limit, offset))
        items = [{"run_id": str(n)} for n in range(offset, min(offset + limit, 501))]
        return {"items": items, "has_next": offset + limit < 501}

    monkeypatch.setattr(pages, "search_sap_inconsistencies", fake_search)
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        for scope, expected_rows, expected_calls in [
            ("first500", 501, [(200, 0), (200, 200), (100, 400)]),
            ("all", 502, [(200, 0), (200, 200), (200, 400)]),
        ]:
            calls.clear()
            response = client.get("/payloads/export", params={"pi_id": "00021", "export_scope": scope})
            assert response.status_code == 200
            with ZipFile(BytesIO(response.content)) as archive:
                sheet = archive.read("xl/worksheets/sheet1.xml").decode()
            assert sheet.count("<row ") == expected_rows
            assert calls == expected_calls
        assert client.get("/payloads/export", params={"pi_id": "00021", "export_scope": "unknown"}).status_code == 422


def test_bp_specific_filters_apply_to_page_and_excel(monkeypatch):
    calls = []

    def fake_search(start, end, pi_id, limit, offset, **kwargs):
        calls.append((start, end, pi_id, kwargs))
        return {"source_available": True, "items": [], "total": 0, "has_next": False}

    monkeypatch.setattr(pages, "search_sap_inconsistencies", fake_search)
    monkeypatch.setattr(pages.runs, "latest_within", lambda *args, **kwargs: None)
    params = {"pi_id": "00021", "bp_id": "BP7", "dni": "12345678", "mpl_id": "MPL-7"}
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        html = client.get("/payloads", params=params).text
        assert 'name="bp_id" class="form-control" value="BP7"' in html
        assert 'name="dni" class="form-control" value="12345678"' in html
        assert 'name="mpl_id" class="form-control" value="MPL-7"' in html
        assert 'bp_id=BP7&amp;dni=12345678&amp;mpl_id=MPL-7' in html
        assert all(start is None and end is None and pi_id == "00021" for start, end, pi_id, _ in calls)
        assert calls[0][3]["bp_id"] == "BP7"
        assert calls[0][3]["dni"] == "12345678"
        assert calls[0][3]["mpl_id"] == "MPL-7"
        calls.clear()
        assert client.get("/payloads/export", params=params).status_code == 200
        assert calls[0][3]["bp_id"] == "BP7" and calls[0][3]["dni"] == "12345678" and calls[0][3]["mpl_id"] == "MPL-7"


def test_trace_tabs_filters_and_dates(monkeypatch):
    calls = []

    def fake_search(flow, filters, page, start, end):
        calls.append((flow, filters, page, start, end))
        return {"source_available": True, "items": [], "has_next": True}

    monkeypatch.setattr(pages, "search_trace", fake_search)
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        for tab in ("bp", "cargos", "pagos"):
            initial = client.get("/trace", params={"tab": tab})
            assert initial.status_code == 200
            assert "Seleccione los filtros" in initial.text
            assert "<table" not in initial.text
        assert calls == []

        for tab, label in (("bp", "APELLIDOS"), ("cargos", "Cargos (Pedidos)"), ("pagos", "Pagos")):
            response = client.get("/trace", params={
                "tab": tab, "id_banner": "B123", "surrogate": "S456", "dni": "D123",
                "id_sap": "SAP789", "run_id": "99", "corr_id": "old-filter",
                "date_from": "2026-09-01", "date_to": "2026-09-02", "page": 2,
            })
            assert response.status_code == 200
            assert label in response.text
            assert 'href="/trace?tab=bp"' in response.text
            assert 'href="/trace?tab=cargos"' in response.text
            assert 'href="/trace?tab=pagos"' in response.text
            assert 'page=3' in response.text
            assert 'date_from=2026-09-01&amp;date_to=2026-09-02' in response.text
            assert 'name="run_id"' not in response.text
            assert 'name="corr_id"' not in response.text
            assert '<th>Corr ID</th>' not in response.text
            assert '<th>ID BANNER</th>' in response.text
            assert '<th>Fecha Hora</th>' in response.text
            assert '<th>Fecha (Lima)</th>' not in response.text
            if tab == "bp":
                assert 'name="dni"' in response.text
                assert 'name="surrogate"' not in response.text
                assert 'name="id_sap"' not in response.text
                assert '<th>DNI (TAXNUM)</th>' in response.text
                assert '<th>ID SAP</th>' not in response.text
            else:
                assert 'name="surrogate"' in response.text
                assert 'name="dni"' not in response.text
                assert 'name="id_sap"' in response.text
            assert calls[-1][0:3] == (tab, {
                "id_banner": "B123", "id_sap": "" if tab == "bp" else "SAP789", "apellidos": "",
                "dni": "D123" if tab == "bp" else "",
                "surrogate": "" if tab == "bp" else "S456", "status": "",
            }, 2)
            assert calls[-1][3:] == (
                datetime(2026, 9, 1, 5, tzinfo=timezone.utc),
                datetime(2026, 9, 3, 5, tzinfo=timezone.utc),
            )
        submitted = client.get("/trace", params={"tab": "bp", "submitted": "1"})
        assert submitted.status_code == 200
        assert "<table" in submitted.text
        assert "submitted=1" in submitted.text
        assert calls[-1][0] == "bp"
        assert client.get("/trace", params={"tab": "otro"}).status_code == 422
        assert client.get("/trace", params={"date_from": "2026-09-01"}).status_code == 422
        assert client.get("/trace", params={"date_from": "2026-09-02", "date_to": "2026-09-01"}).status_code == 422


def test_trace_links_banner_id_and_places_date_last(monkeypatch):
    monkeypatch.setattr(pages, "search_trace", lambda *args: {
        "source_available": True,
        "has_next": False,
        "items": [{
            "ts": datetime(2026, 9, 29, 15, tzinfo=timezone.utc), "run_id": 99,
            "id_banner": "B123", "reference": "Apellido", "dni": "12345678",
            "queue_name": "cola", "status": "OK", "error_count": 0,
        }],
    })
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        html = client.get("/trace", params={"tab": "bp", "id_banner": "B123"}).text
        assert re.search(r'<td><a href="/runs/[^"]+/99\?return_to=[^"]+">B123</a></td>', html)
        detail_url = unescape(re.search(r'<td><a href="([^"]+)">B123</a></td>', html).group(1))
        assert parse_qs(urlsplit(detail_url).query)["return_to"] == ["/trace?tab=bp&id_banner=B123"]
        assert re.search(r'<td>29/09/2026 10:00:00</td>', html)
        assert html.index("<th>ID BANNER</th>") < html.index("<th>APELLIDOS</th>") < html.index("<th>Fecha Hora</th>")
        assert html.index("<td><a href=") < html.index("<td>29/09/2026 10:00:00</td>")


def test_filtered_payload_detail_returns_to_same_results(monkeypatch):
    run_ts = datetime(2026, 9, 29, 15, tzinfo=timezone.utc)
    item = {
        "run_ts": run_ts, "run_id": "99", "ib_banner": "B123", "dni": "12345678",
        "apellidos": "Apellido", "status": "OK", "json_status": "ERROR", "http_status": 200,
        "failed_items_count": 1, "failed_status_code": 400, "failed_body": "Error SAP",
        "texto_mpl_id": "MPL de prueba", "texto_legible": "BP rechazado", "kind": "SAP", "explanation": "Rechazado",
    }
    monkeypatch.setattr(pages, "search_sap_inconsistencies", lambda *args, **kwargs: {
        "source_available": True, "items": [item], "total": 31, "has_next": True,
    })
    monkeypatch.setattr(pages.runs, "latest_within", lambda *args, **kwargs: None)
    monkeypatch.setattr(pages, "get_run_trace", lambda *args, **kwargs: {
        "run": {"ts": run_ts}, "sent": None, "sap_response": None,
        "events": [], "dq_issues": [], "stages": [],
    })
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        url = "/payloads?pi_id=00021&q=B123&date_from=2026-09-01&date_to=2026-09-29&page=2"
        response = client.get(url)
        assert response.status_code == 200
        assert "Inconsistencias de payloads" not in response.text
        assert '<h1 class="h3 m-0">' not in response.text
        assert 'id="sidebar-hide"' not in response.text
        assert "<th>Estado JSON</th>" not in response.text
        assert "<th>Integración</th>" not in response.text
        assert "<th>BP</th>" not in response.text
        assert "<th>SURROGATE</th>" not in response.text
        assert "<th>Ítems fallidos</th>" not in response.text
        assert "<th>Error SAP</th>" not in response.text
        assert "<th>HTTP</th>" in response.text
        assert "<th>MPL-ID</th><th>Mensaje CPI</th>" in response.text
        assert "<th>Interpretación</th>" not in response.text
        assert 'class="btn btn-success btn-sm" type="button" data-bs-toggle="modal" data-bs-target="#excel-export-modal"' in response.text
        assert 'name="export_scope" value="first500"' in response.text
        assert 'name="export_scope" value="all"' in response.text
        assert "puede tardar varios minutos" in response.text
        assert 'class="btn btn-danger" type="submit"' in response.text
        assert 'class="btn btn-secondary align-self-center" data-bs-dismiss="modal">Cancelar</button>' in response.text
        assert 'js/app.js?v=template-columns-1' in response.text
        assert 'name="bp_id"' in response.text
        assert 'name="dni"' in response.text
        assert 'name="mpl_id"' in response.text
        assert "MPL de prueba" in response.text
        assert "BP rechazado" in response.text
        assert "Ver mensaje SAP" not in response.text
        assert 'id="loading-overlay"' in response.text
        assert 'method="get" data-loading' in response.text
        detail_url = unescape(re.search(r'<td><a href="([^"]+)">99</a></td>', response.text).group(1))
        assert parse_qs(urlsplit(detail_url).query)["return_to"] == [url]
        detail = client.get(detail_url)
        assert detail.status_code == 200
        assert f'href="{url.replace("&", "&amp;")}"' in detail.text
        assert "Volver a resultados" in detail.text
        assert client.get(detail_url.split("?", 1)[0] + "?return_to=https%3A%2F%2Fevil.example").text.find('href="/runs"') != -1


def test_surrogate_filters_link_and_history(monkeypatch):
    run_ts = datetime(2026, 9, 29, 15, tzinfo=timezone.utc)
    calls = []

    def fake_search(*args, **kwargs):
        calls.append(kwargs)
        return {"source_available": True, "items": [{
            "run_ts": run_ts, "run_id": "99", "pi_id": "00022", "bp": "BP7", "ib_banner": "KUNNR-7",
            "surrogate": "SUR-7", "status": "OK", "json_status": "ERROR", "http_status": 400,
            "matnr": "MAT-1, MAT-2", "total_amount": "120.50", "fecha_audat": "2026-09-29", "failed_body": "Pedido rechazado",
            "failed_items_count": 1, "kind": "Rechazado", "severity": "alta", "explanation": "Error SAP",
        }], "total": 1, "has_next": False}

    monkeypatch.setattr(pages, "search_sap_inconsistencies", fake_search)
    monkeypatch.setattr(pages.runs, "latest_within", lambda *args, **kwargs: None)
    monkeypatch.setattr(pages, "surrogate_history", lambda *args, **kwargs: {
        "source_available": True, "total": 2, "sent_count": 1, "result_count": 1,
        "has_next": False, "items": [{"ts": run_ts, "run_id": "99", "queue_name": "que.upao.iisupao.result",
            "status": "OK", "json_status": "ERROR", "http_status": 400, "response": "Rechazado por SAP"}],
    })
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        response = client.get("/payloads", params={"pi_id": "00022", "bp": "BP7", "record_id": "99", "surrogate": "SUR-7"})
        assert response.status_code == 200
        assert 'class="btn btn-success btn-sm" type="button" data-bs-toggle="modal" data-bs-target="#excel-export-modal"' in response.text
        assert calls[0]["bp"] == "BP7" and calls[0]["record_id"] == "99" and calls[0]["surrogate"] == "SUR-7"
        assert 'href="/payloads?pi_id=00022&amp;surrogate=SUR-7&amp;view=all"' in response.text
        assert "<th>Integración</th>" not in response.text
        assert "<th>Estado JSON</th>" not in response.text
        for header in ("DNI", "APELLIDOS", "HTTP"):
            assert f"<th>{header}</th>" not in response.text
        assert "<th>MPL_ID</th>" not in response.text
        assert "<th>Ítems fallidos</th>" not in response.text
        assert "<th>Interpretación</th>" not in response.text
        assert "KUNNR-7" in response.text
        assert "<th>MATNR</th>" in response.text and "MAT-1, MAT-2" in response.text
        assert "<th>AUDAT (Fecha)</th>" in response.text and "2026-09-29" in response.text
        assert "<th>ZVALORTOTAL (Monto)</th>" in response.text and "120.50" in response.text
        assert "<th>Mensaje de error SAP</th>" in response.text and "Pedido rechazado" in response.text
        orders = client.get("/payloads?pi_id=00022&surrogate=SUR-7&view=all")
        assert orders.status_code == 200
        assert any(call.get("include_all") is True and call.get("surrogate") == "SUR-7" for call in calls)
        detail = client.get("/surrogate", params={"pi_id": "00022", "surrogate": "SUR-7"})
        assert detail.status_code == 200
        assert "1 envío(s)" in detail.text and "1 respuesta(s)" in detail.text
        assert "Rechazado por SAP" in detail.text


def test_payment_payload_columns_show_error_body(monkeypatch):
    calls = []

    def fake_search(*args, **kwargs):
        calls.append((args, kwargs))
        return {"source_available": True, "items": [{"run_ts": datetime(2026, 9, 29, 15, tzinfo=timezone.utc),
            "run_id": "100", "pi_id": "00023", "status": "ERROR", "http_status": 422,
            "ib_banner": "PARTNER-23", "surrogate": "BSTKD-23",
            "failed_items_count": 1, "failed_body": '{"Codigo":"400","Mensaje":"Cuenta inválida"}', "payment_message": "Cuenta inválida", "document_date": "2026-09-29",
            "payment_amount": "90.00", "account": "HK-1", "kind": "Rechazado",
            "severity": "alta", "explanation": "Error SAP"}], "total": 1, "has_next": False,
        }

    monkeypatch.setattr(pages, "search_sap_inconsistencies", fake_search)
    monkeypatch.setattr(pages.runs, "latest_within", lambda *args, **kwargs: None)
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        response = client.get("/payloads?pi_id=00023")
        assert response.status_code == 200
        assert 'payment-payload-table' in response.text
        assert "<th>Interpretación</th>" not in response.text
        table_markup = re.search(r"<thead><tr>(.*?)</tr></thead><tbody>.*?<tr>(.*?)</tr>", response.text, re.S)
        assert table_markup and table_markup.group(1).count("<th") == table_markup.group(2).count("<td") == 11
        assert 'class="btn btn-success btn-sm" type="button" data-bs-toggle="modal" data-bs-target="#excel-export-modal"' in response.text
        for header in ("Integración", "Estado JSON", "DNI", "APELLIDOS", "Ítems fallidos", "MPL_ID"):
            assert f"<th>{header}</th>" not in response.text
        for header in ("BLDAT (Fecha)", "WRBTR (Monto)", "HKONT (Cuenta)", "Mensaje de error SAP"):
            assert f"<th>{header}</th>" in response.text
        for value in ("2026-09-29", "90.00", "HK-1", "Cuenta inválida"):
            assert value in response.text
        assert "PARTNER-23" in response.text and "BSTKD-23" in response.text
        assert 'href="/payloads?pi_id=00023&amp;surrogate=BSTKD-23&amp;view=all"' in response.text
        assert "<th>HTTP</th>" in response.text and ">422</td>" in response.text
        assert "Codigo" not in response.text
        labels = ["Desde", "Hasta", "SURROGATE", "BP", "ID BANNER", "ERROR (HTTP)", "Fecha (BLDAT)"]
        positions = [response.text.index(f">{label}<input", response.text.index('<form id="payload-filter-form"')) for label in labels]
        assert positions == sorted(positions)
        assert 'name="q"' not in response.text and 'name="record_id"' not in response.text

        calls.clear()
        filtered = client.get("/payloads", params={"pi_id": "00023", "date_from": "2026-09-01", "date_to": "2026-09-30", "surrogate": "BSTKD-23", "bp": "BP-23", "id_banner": "PARTNER-23", "error_http": "422", "bldat": "2026-09-29"})
        assert filtered.status_code == 200
        assert calls[0][1] == {"include_all": False, "query": "", "bp": "BP-23", "surrogate": "BSTKD-23", "id_banner": "PARTNER-23", "error_http": "422", "bldat": "2026-09-29"}
        assert 'surrogate=BSTKD-23' in filtered.text and 'error_http=422' in filtered.text

        calls.clear()
        all_payments = client.get("/payloads?pi_id=00023&surrogate=BSTKD-23&view=all")
        assert all_payments.status_code == 200
        assert any(kwargs.get("include_all") is True and kwargs.get("surrogate") == "BSTKD-23" for _, kwargs in calls)
        assert calls[0][0][:2] == (None, None)


def test_mpl_text_is_shown_and_exported_for_error_orders_and_payments(monkeypatch):
    run_ts = datetime(2026, 9, 29, 15, tzinfo=timezone.utc)

    def fake_search(*args, **kwargs):
        pi_id = args[2]
        return {"source_available": True, "items": [{
            "run_ts": run_ts, "run_id": "5688382", "pi_id": pi_id, "status": "ERROR",
            "http_status": 400, "failed_body": "Mensaje original del pedido",
            "payment_message": "Mensaje original del pago", "sap_error_message": "Texto legible del MPL",
        }], "total": 1, "has_next": False}

    monkeypatch.setattr(pages, "search_sap_inconsistencies", fake_search)
    monkeypatch.setattr(pages.runs, "latest_within", lambda *args, **kwargs: None)
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        for pi_id in ("00022", "00023"):
            page = client.get("/payloads", params={"pi_id": pi_id})
            assert page.status_code == 200
            assert "Texto legible del MPL" in page.text
            assert "Mensaje original del pedido" not in page.text
            assert "Mensaje original del pago" not in page.text

            exported = client.get("/payloads/export", params={"pi_id": pi_id})
            assert exported.status_code == 200
            with ZipFile(BytesIO(exported.content)) as archive:
                sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
            assert "Texto legible del MPL" in sheet
            assert "Mensaje original del pedido" not in sheet
            assert "Mensaje original del pago" not in sheet


def test_failed_attempt_cpi_message_opens_run_text_tab(monkeypatch):
    run_ts = datetime(2026, 10, 8, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(pages, "failed_attempts_detail", lambda *args: {
        "source_available": True, "has_next": False, "items": [{
            "identifier": "SUR-7", "fecha_error": date(2026, 10, 8),
            "error_body": "Revisar log de CPI", "run_ts": run_ts, "run_id": 5688382,
            "total_intentos_fallidos": 2, "total_por_identificador": 5,
        }],
    })
    monkeypatch.setattr(pages, "get_run_trace", lambda *args, **kwargs: {
        "run": {"ts": run_ts}, "sent": None, "sap_response": None,
        "events": [], "dq_issues": [], "stages": [],
        "cpi": {"texto_cpi": "Detalle completo del error CPI <sin formato>"},
    })
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        listing = client.get("/incidents/failed-attempts/00022?date_from=2026-10-08&date_to=2026-10-08")
        assert listing.status_code == 200
        assert '<h1 class="h3 m-0">Cargos · Intentos fallidos</h1>' not in listing.text
        link = re.search(r'<div class="incident-error-message"><a href="([^"]+)">Revisar log de CPI</a></div>', listing.text)
        assert link
        detail = client.get(unescape(link.group(1)))
        assert detail.status_code == 200
        assert 'class="tab-pane fade show active" id="tab7"' in detail.text
        assert "Detalle completo del error CPI &lt;sin formato&gt;" in detail.text
        assert 'href="/incidents/failed-attempts/00022?date_from=2026-10-08&amp;date_to=2026-10-08"' in detail.text


def test_cpi_log_link_opens_run_text_tab(monkeypatch):
    run_ts = datetime(2026, 9, 29, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(pages, "search_sap_inconsistencies", lambda *args, **kwargs: {
        "source_available": True, "items": [{
            "run_ts": run_ts, "run_id": "5688382", "pi_id": "00022", "status": "ERROR",
            "sap_error_message": "Revisar log de CPI", "failed_body": "Error interno",
        }], "total": 1, "has_next": False,
    })
    monkeypatch.setattr(pages.runs, "latest_within", lambda *args, **kwargs: None)
    monkeypatch.setattr(pages, "get_run_trace", lambda *args, **kwargs: {
        "run": {"ts": run_ts}, "sent": None, "sap_response": None,
        "events": [], "dq_issues": [], "stages": [],
        "cpi": {"texto_cpi": "Detalle completo del error CPI <sin formato>"},
    })
    with TestClient(app) as client:
        client.post("/login", data={"username": "admin", "password": "test-password"})
        listing = client.get("/payloads?pi_id=00022")
        assert listing.status_code == 200
        link = re.search(r'<a href="([^"]+)">Revisar log de CPI</a>', listing.text)
        assert link
        detail = client.get(unescape(link.group(1)))
        assert detail.status_code == 200
        assert 'data-bs-target="#tab7">Texto CPI</button>' in detail.text
        assert 'class="tab-pane fade show active" id="tab7"' in detail.text
        assert "Detalle completo del error CPI &lt;sin formato&gt;" in detail.text
        assert 'href="/payloads?pi_id=00022"' in detail.text
