"""Structural JSON differences for payload comparison."""


def compare_json(left, right, path: str = "$") -> list[dict]:
    if type(left) is not type(right):
        return [{"path": path, "change": "tipo distinto", "before": left, "after": right}]
    if isinstance(left, dict):
        out = []
        for key in sorted(left.keys() | right.keys()):
            child = f"{path}.{key}"
            if key not in left:
                out.append({"path": child, "change": "agregado", "before": None, "after": right[key]})
            elif key not in right:
                out.append({"path": child, "change": "eliminado", "before": left[key], "after": None})
            else:
                out.extend(compare_json(left[key], right[key], child))
        return out
    if isinstance(left, list):
        out = []
        for index in range(max(len(left), len(right))):
            child = f"{path}[{index}]"
            if index >= len(left):
                out.append({"path": child, "change": "agregado", "before": None, "after": right[index]})
            elif index >= len(right):
                out.append({"path": child, "change": "eliminado", "before": left[index], "after": None})
            else:
                out.extend(compare_json(left[index], right[index], child))
        return out
    return [] if left == right else [{"path": path, "change": "modificado", "before": left, "after": right}]
