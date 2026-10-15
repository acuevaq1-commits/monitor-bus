from src.domain.services.payload_validator import DEFAULT_RULES, validate


def test_independent_rules_for_three_integrations():
    assert validate({}, "00021", DEFAULT_RULES)[0].path == "data.person.wnrodoc"
    assert validate({}, "00022", DEFAULT_RULES)[0].path == "BSTKD"
    assert not validate({"ZVIAPAG": "p1", "WRBTR": 10}, "00023", DEFAULT_RULES)
    assert validate({"ZVIAPAG": "p1", "WRBTR": 0}, "00023", DEFAULT_RULES)


def test_alternative_nested_payload():
    rule = {"pi_id": "00021", "name": "BP", "json_path": "data.partner.id", "validation_type": "required", "severity": "alta"}
    assert validate({"data": {"partner": {}}}, "00021", [rule])
    assert not validate({"data": {"partner": {"id": "123"}}}, "00021", [rule])
