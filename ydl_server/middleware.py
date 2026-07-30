from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Require a matching API key on /api/ requests.

    Intended for deployments not sitting behind a reverse proxy that already
    handles access control. Accepts the key via the X-API-Key header (used by
    fetch()) or an api_key query parameter (needed for EventSource, which
    can't set custom headers). Static assets and the SPA shell are untouched.
    """

    def __init__(self, app, api_key):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/api/"):
            provided = request.headers.get("X-API-Key") or request.query_params.get("api_key")
            if provided != self.api_key:
                return JSONResponse(
                    {"success": False, "error": "Missing or invalid API key"}, status_code=401
                )
        return await call_next(request)
