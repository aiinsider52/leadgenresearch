"""Map service-layer error dicts to HTTP status codes."""
from __future__ import annotations

from fastapi.responses import JSONResponse


def api_from_result(result: dict, *, ok_status: int = 200) -> JSONResponse:
    err = result.get("error")
    if not err:
        if result.get("failed") and not result.get("sent"):
            return JSONResponse(result, status_code=422)
        return JSONResponse(result, status_code=ok_status)
    low = str(err).lower()
    if "not found" in low or "not pending" in low:
        return JSONResponse({"detail": err}, status_code=404)
    if "paused" in low or "limit" in low or "not authenticated" in low:
        return JSONResponse({"detail": err}, status_code=409)
    if "invalid" in low or "no email" in low:
        return JSONResponse({"detail": err}, status_code=400)
    return JSONResponse({"detail": err}, status_code=400)
