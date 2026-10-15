from src.domain.services.sap_status_validator import classify_status


def test_ok_run_with_json_500_is_critical():
    finding = classify_status("OK", "500", None)
    assert finding and finding["severity"] == "critica"


def test_error_run_with_http_200_and_failed_items_prioritizes_sap_rejection():
    finding = classify_status("ERROR", "OK", 200, failed_items=1, error_count=1, failed_status_code=500)
    assert finding and finding["kind"] == "Ítems rechazados por SAP"
    assert finding["severity"] == "critica"


def test_consistent_success_is_not_a_finding():
    assert classify_status("OK", "OK", 200) is None


def test_ok_run_with_http_200_and_failed_item_is_a_finding():
    finding = classify_status("OK", "OK", 200, failed_items=1, failed_status_code=500)
    assert finding and finding["kind"] == "Ítems rechazados por SAP"
    assert finding["severity"] == "critica"
