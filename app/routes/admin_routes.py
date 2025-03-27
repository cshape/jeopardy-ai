from fastapi import APIRouter, HTTPException, Request
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
)

@router.get("/status")
async def get_admin_status(request: Request):
    """Get the status of the admin API."""
    return {"status": "active"} 