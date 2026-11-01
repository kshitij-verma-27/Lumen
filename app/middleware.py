import os
import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class PublicSafetyMiddleware(BaseHTTPMiddleware):
    """
    Public safety middleware providing:
    1. Maximum request payload size cap (5MB).
    2. Per-IP rate limiting:
       - 20 requests per minute on /api/ endpoints (exempting /api/health).
       - 5 investigations per hour (e.g. POST /api/sessions, /extract, /detect).
    3. Test-suite awareness (bypass if TESTING=true or LUMEN_DISABLE_RATE_LIMIT=true).
    """

    def __init__(self, app, max_content_length: int = 5 * 1024 * 1024):
        super().__init__(app)
        self.max_content_length = max_content_length
        self.api_requests = defaultdict(list)
        self.investigation_requests = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # Allow OPTIONS requests for CORS pre-flight without rate limits
        if request.method == "OPTIONS":
            return await call_next(request)

        # 1. Request size cap check
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_content_length:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Payload too large. Maximum allowed size is 5MB."}
                    )
            except ValueError:
                pass

        # Check if rate limits should be enforced
        bypass = os.environ.get("TESTING") == "true" or os.environ.get("LUMEN_DISABLE_RATE_LIMIT") == "true"
        path = request.url.path

        # 2. Rate limiting on /api/ endpoints (always exempt /api/health for probes)
        if not bypass and path.startswith("/api/") and path != "/api/health":
            client_ip = request.client.host if request.client else "unknown"
            now = time.time()

            # Clean window (60s)
            self.api_requests[client_ip] = [t for t in self.api_requests[client_ip] if now - t < 60]
            if len(self.api_requests[client_ip]) >= 20:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded (max 20 requests per minute). Please try again shortly."}
                )
            self.api_requests[client_ip].append(now)

            # Investigations limit: 5 per hour
            is_investigation = (
                (path == "/api/sessions" and request.method == "POST") or
                "/extract" in path or
                "/detect" in path
            )
            if is_investigation:
                self.investigation_requests[client_ip] = [
                    t for t in self.investigation_requests[client_ip] if now - t < 3600
                ]
                if len(self.investigation_requests[client_ip]) >= 5:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Investigation limit exceeded (max 5 investigations per hour)."}
                    )
                self.investigation_requests[client_ip].append(now)

        return await call_next(request)
