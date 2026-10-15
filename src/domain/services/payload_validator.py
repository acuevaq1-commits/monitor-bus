import re
from collections.abc import Mapping

from src.domain.entities.payload_inconsistency import PayloadInconsistency


SUPPORTED = {"required", "type", "length", "regex", "range", "catalog", "compare", "conditional"}


def value_at(payload: object, path: str):
    current = payload
    for part in path.strip("$.").split("."):
        if isinstance(current, Mapping):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def validate(payload: object, pi_id: str, rules: list[dict]) -> list[PayloadInconsistency]:
    out = []
    for rule in rules:
        if not rule.get("active", True) or rule.get("pi_id") not in (pi_id, "*", None):
            continue
        kind = rule.get("validation_type")
        if kind not in SUPPORTED:
            continue
        path = rule.get("json_path", "")
        value = value_at(payload, path)
        params = rule.get("parameters") or {}
        failed = False
        if kind == "required":
            failed = value is None or value == "" or value == []
        elif kind == "type" and value is not None:
            failed = {"string": str, "number": (int, float), "array": list, "object": dict, "boolean": bool}.get(params.get("type"), object) not in (object,) and not isinstance(value, {"string": str, "number": (int, float), "array": list, "object": dict, "boolean": bool}[params["type"]])
        elif kind == "length" and value is not None:
            failed = len(value) < params.get("min", 0) or len(value) > params.get("max", 1000000)
        elif kind == "regex" and value is not None:
            pattern = params.get("pattern", "")
            failed = len(pattern) > 256 or len(str(value)) > 4096 or re.fullmatch(pattern, str(value)) is None
        elif kind == "range" and value is not None:
            try:
                number = float(value)
                failed = number < params.get("min", float("-inf")) or number > params.get("max", float("inf"))
            except (ValueError, TypeError):
                failed = True
        elif kind == "catalog" and value is not None:
            failed = value not in params.get("values", [])
        elif kind == "compare":
            failed = value != value_at(payload, params.get("other_path", ""))
        elif kind == "conditional" and value_at(payload, params.get("when_path", "")) == params.get("equals"):
            failed = value is None or value == ""
        if failed:
            out.append(PayloadInconsistency(pi_id, path, rule.get("name", kind), rule.get("message", "Regla incumplida"), rule.get("severity", "alta"), value))
    return out


DEFAULT_RULES = [
    {"pi_id": "00021", "name": "Documento BP", "json_path": "data.person.wnrodoc", "validation_type": "required", "message": "Documento de identidad obligatorio", "severity": "critica"},
    {"pi_id": "00022", "name": "Referencia pedido", "json_path": "BSTKD", "validation_type": "required", "message": "BSTKD obligatorio", "severity": "critica"},
    {"pi_id": "00022", "name": "Posiciones pedido", "json_path": "ITEMS", "validation_type": "required", "message": "El pedido requiere posiciones", "severity": "alta"},
    {"pi_id": "00023", "name": "Referencia pago", "json_path": "ZVIAPAG", "validation_type": "required", "message": "Referencia de pago obligatoria", "severity": "critica"},
    {"pi_id": "00023", "name": "Importe pago", "json_path": "WRBTR", "validation_type": "range", "parameters": {"min": 0.01}, "message": "Importe debe ser mayor que cero", "severity": "critica"},
]
