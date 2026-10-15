STAGES = ("BannerNexus", "IISTransform", "RabbitMQ", "IISDispatcher", "SAP CPI", "SAP S/4HANA")


def build_trace(run: dict, events: list[dict]) -> list[dict]:
    stages = []
    for stage in STAGES:
        matches = []
        for event in events:
            label = " ".join(str(event.get(key) or "") for key in ("service_name", "worker_name", "queue_name", "stage", "component"))
            if stage.lower() in label.lower():
                matches.append(event)
        stages.append({"name": stage, "status": "sin evidencia" if not matches else "repetida" if len(matches) > 1 else "observada", "events": matches, "count": len(matches)})
    return stages
