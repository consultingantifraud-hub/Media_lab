"""Billing health check endpoint for FastAPI."""
from fastapi import APIRouter
import os

router = APIRouter(prefix="/yookassa", tags=["billing"])


@router.get("/health")
async def billing_health():
    """Health check for billing service."""
    return {
        "status": "ok",
        "service": "billing",
        "yookassa_configured": bool(os.getenv("YOOKASSA_SHOP_ID") and os.getenv("YOOKASSA_SECRET_KEY"))
    }

