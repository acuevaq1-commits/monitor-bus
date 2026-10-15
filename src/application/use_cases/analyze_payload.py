from src.domain.services.payload_validator import DEFAULT_RULES, validate


def analyze_payload(pi_id: str, payload: object, configured_rules: list[dict]):
    if pi_id not in {"00021", "00022", "00023"}:
        raise ValueError("pi_id no admitido")
    return [vars(x) if hasattr(x, "__dict__") else {f: getattr(x, f) for f in x.__dataclass_fields__} for x in validate(payload, pi_id, DEFAULT_RULES + configured_rules)]
