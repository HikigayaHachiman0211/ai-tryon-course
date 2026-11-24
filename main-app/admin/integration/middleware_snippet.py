"""
Middleware snippet for the main site FastAPI app.
Add this to the main site to log requests to the admin database.

Usage in main site's main.py:
    from admin.integration.middleware_snippet import RequestLoggingMiddleware
    app.add_middleware(RequestLoggingMiddleware)
"""
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = int((time.time() - start) * 1000)

        # Only log API requests
        if request.url.path.startswith("/api/"):
            try:
                from app.database import SessionLocal
                from admin.backend.app.database import RequestLog
                db = SessionLocal()
                log = RequestLog(
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    user_agent=request.headers.get("user-agent", ""),
                    ip_address=request.client.host if request.client else "",
                )
                db.add(log)
                db.commit()
                db.close()
            except Exception:
                pass  # Don't break main site if logging fails

        return response
