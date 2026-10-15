from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from src.infrastructure.settings import get_settings
from src.presentation.api.routes import router as api_router
from src.presentation.web.routes.pages import router as web_router

settings = get_settings()
if settings.environment.lower() in {"produccion", "production"} and (settings.session_secret == "development-only-change-me" or not settings.admin_password):
    raise RuntimeError("Configure MONITOR_SESSION_SECRET y MONITOR_ADMIN_PASSWORD antes de iniciar en producción")

app = FastAPI(title="Monitor de Integraciones Banner–SAP", version="0.1.0")
@app.middleware("http")
async def protect_api_changes(request: Request, call_next):
    if request.url.path.startswith("/api/v1/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        from src.presentation.dependencies import check_csrf
        from fastapi import HTTPException
        try:
            check_csrf(request, request.headers.get("x-csrf-token", ""))
        except HTTPException:
            return JSONResponse({"detail": "CSRF inválido"}, status_code=403)
    return await call_next(request)


app.add_middleware(SessionMiddleware, secret_key=get_settings().session_secret, same_site="lax", https_only=get_settings().environment.lower() in {"produccion", "production"})
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "presentation" / "web" / "static"), name="static")
app.include_router(api_router)
app.include_router(web_router)


@app.get("/health")
def health():
    return {"status": "ok"}
