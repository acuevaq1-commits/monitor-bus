from enum import StrEnum


class IncidentStatus(StrEnum):
    OPEN = "abierto"
    ACKNOWLEDGED = "reconocido"
    RESOLVED = "resuelto"
    SILENCED = "silenciado"
