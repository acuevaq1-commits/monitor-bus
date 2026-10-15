from src.domain.services.payload_diff import compare_json


def test_comparison_classifies_all_change_types():
    result = compare_json({"a": 1, "b": "x", "c": [1, 2], "d": True}, {"a": "1", "b": "y", "c": [1], "e": 3})
    assert {item["change"] for item in result} == {"tipo distinto", "modificado", "eliminado", "agregado"}
