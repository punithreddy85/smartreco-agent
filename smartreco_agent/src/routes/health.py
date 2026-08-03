"""Health check route for the SmartReco Agent API.

This module provides health check endpoints to monitor the status
and availability of the SmartReco Agent service.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
async def health_check() -> JSONResponse:
    """Perform a health check on the SmartReco Agent service.

    This endpoint is used to verify that the service is running and
    responding to requests. It returns a simple JSON response indicating
    the service status.

    Returns:
        A JSONResponse containing the service status and name.
    """
    return JSONResponse(content={"status": "healthy", "service": "SmartReco Agent"})
