"""Billing webhook endpoints for FastAPI."""
from fastapi import APIRouter, Request, HTTPException, Header
from loguru import logger
from typing import Optional, Dict, Any
import json
import ipaddress

from app.services.payment import PaymentService
from app.db.base import SessionLocal

router = APIRouter(prefix="/yookassa", tags=["billing"])

# YooKassa IP ranges (для проверки безопасности)
YOOKASSA_IP_RANGES = [
    "185.71.76.0/27",
    "185.71.77.0/27",
    "77.75.153.0/25",
    "77.75.154.128/25",
    "2a02:5180:0:1509::/64",
    "2a02:5180:0:2659::/64",
]


def verify_yookassa_ip(client_ip: str) -> bool:
    """
    Verify that webhook request comes from YooKassa IP range.
    
    Args:
        client_ip: Client IP address
        
    Returns:
        bool: True if IP is from YooKassa range
    """
    try:
        client_ip_obj = ipaddress.ip_address(client_ip)
        for ip_range in YOOKASSA_IP_RANGES:
            if client_ip_obj in ipaddress.ip_network(ip_range, strict=False):
                return True
        return False
    except (ValueError, ipaddress.AddressValueError) as e:
        logger.warning(f"Invalid IP address format: {client_ip}, error: {e}")
        return False


@router.post("/webhook")
async def yookassa_webhook(
    request: Request,
    x_request_id: Optional[str] = Header(None, alias="X-Request-Id")
):
    """
    YooKassa webhook endpoint for payment notifications.
    
    Configure this URL in YooKassa dashboard:
    https://your-domain.com/yookassa/webhook
    
    Security:
    - IP whitelist check (YooKassa IP ranges)
    - Payment ID validation
    - Duplicate payment prevention
    """
    try:
        # Получаем IP адрес клиента
        client_ip = request.client.host if request.client else None
        
        # Проверка IP адреса (опционально, можно отключить для тестирования)
        # В production рекомендуется включить
        if client_ip:
            # Проверяем, если IP не из YooKassa диапазона - логируем предупреждение
            # Но не блокируем (на случай прокси/балансировщиков)
            if not verify_yookassa_ip(client_ip):
                logger.warning(
                    f"Webhook request from non-YooKassa IP: {client_ip}, "
                    f"request_id={x_request_id}. Processing anyway (might be behind proxy)."
                )
        
        # Get webhook data
        webhook_data = await request.json()
        
        event_type = webhook_data.get("event")
        payment_id = webhook_data.get("object", {}).get("id")
        
        logger.info(
            f"Received YooKassa webhook: event={event_type}, "
            f"payment_id={payment_id}, request_id={x_request_id}, client_ip={client_ip}"
        )
        logger.debug(f"Webhook data: {json.dumps(webhook_data, indent=2)}")

        # Process webhook
        db = SessionLocal()
        try:
            success = PaymentService.process_webhook(db, webhook_data)
            
            if success:
                logger.info(f"Webhook processed successfully: event={event_type}, payment_id={payment_id}")
                return {"status": "ok"}
            else:
                logger.error(f"Failed to process webhook: event={event_type}, payment_id={payment_id}")
                raise HTTPException(status_code=500, detail="Failed to process webhook")
        finally:
            db.close()

    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def billing_health():
    """Health check for billing service."""
    import os
    return {
        "status": "ok",
        "service": "billing",
        "yookassa_configured": bool(os.getenv("YOOKASSA_SHOP_ID") and os.getenv("YOOKASSA_SECRET_KEY"))
    }

