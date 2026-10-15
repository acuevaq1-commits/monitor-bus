"""Safe connectivity check: never prints DSNs or credentials."""
from sqlalchemy import create_engine, text
from src.infrastructure.settings import get_settings


def check(label: str, url: str | None) -> bool:
    if not url:
        print(f"{label}: SIN_CONFIGURAR")
        return False
    engine = None
    try:
        engine = create_engine(url, connect_args={"connect_timeout": 3}, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            print(f"{label}: CONEXION_OK")
            if label == "origen":
                for name in ("iislog.iis_run", "iislog.iis_event", "iislog.dq_issue", "iisupao.plantilla_integracion"):
                    exists = connection.execute(text("SELECT to_regclass(:name)"), {"name": name}).scalar() is not None
                    print(f"{name}: {'EXISTE' if exists else 'NO_DISPONIBLE'}")
            else:
                exists = connection.execute(text("SELECT to_regnamespace('iismonitor')")).scalar() is not None
                print(f"iismonitor: {'EXISTE' if exists else 'NO_EXISTE'}")
        return True
    except Exception as exc:
        detail = str(exc).lower()
        if "connection refused" in detail or "conexión rechazada" in detail:
            reason = "SERVIDOR_NO_ESCUCHA"
        elif "password authentication failed" in detail or "autenticación por contraseña falló" in detail:
            reason = "CREDENCIALES_INVALIDAS"
        elif "could not translate host name" in detail:
            reason = "HOST_NO_RESUELTO"
        elif "timeout" in detail or "timed out" in detail:
            reason = "TIEMPO_AGOTADO"
        elif "does not exist" in detail:
            reason = "BASE_NO_EXISTE"
        else:
            reason = type(exc).__name__
        print(f"{label}: ERROR_{reason}")
        return False
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    settings = get_settings()
    ok_source = check("origen", settings.source_database_url)
    ok_monitor = check("monitor", settings.database_url)
    raise SystemExit(0 if ok_source and ok_monitor else 1)
