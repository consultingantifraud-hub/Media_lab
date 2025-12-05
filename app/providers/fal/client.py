from __future__ import annotations

import logging
import time
import threading

import httpx
import requests
from loguru import logger

from app.core.config import settings

DEFAULT_TIMEOUT = 60.0
DOWNLOAD_MAX_ATTEMPTS = 1  # Single attempt - if it fails, send by URL instead
DOWNLOAD_CONNECT_TIMEOUT = 10.0  # Reasonable timeout for SSL handshake
DOWNLOAD_READ_TIMEOUT = 300.0  # 5 minutes for large upscale files (15MB+)
DOWNLOAD_RETRY_BACKOFF = 1.5
RUN_BASE_URL = "https://fal.run"
RUN_CONNECT_TIMEOUT = 10.0
RUN_READ_TIMEOUT = 150.0
RUN_WRITE_TIMEOUT = 60.0
RUN_MAX_ATTEMPTS = 3
RUN_RETRY_BACKOFF = 2.0

# Global HTTP client with connection pooling for better performance
_http_client_lock = threading.Lock()
_http_client: httpx.Client | None = None
_http_client_timeout = httpx.Timeout(
    connect=30.0,  # Increased for SSL handshake timeout issues
    read=60.0,
    write=30.0,
    pool=30.0,
)
_http_client_limits = httpx.Limits(
    max_keepalive_connections=20,
    max_connections=100,
    keepalive_expiry=30.0,
)


def _get_http_client() -> httpx.Client:
    """Get or create global HTTP client with connection pooling."""
    global _http_client
    if _http_client is None:
        with _http_client_lock:
            if _http_client is None:
                _http_client = httpx.Client(
                    timeout=_http_client_timeout,
                    limits=_http_client_limits,
                )
    return _http_client


def _close_http_client() -> None:
    """Close global HTTP client (for cleanup)."""
    global _http_client
    if _http_client is not None:
        with _http_client_lock:
            if _http_client is not None:
                _http_client.close()
                _http_client = None


def _normalize_path(path: str) -> str:
    return path.strip("/")


def _build_queue_url(model: str, suffix: str | None = None) -> str:
    base = settings.fal_queue_base_url.rstrip("/")
    model_path = _normalize_path(model)
    if suffix:
        return f"{base}/{model_path}/{_normalize_path(suffix)}"
    return f"{base}/{model_path}"


QUEUE_BASE_OVERRIDES = {
    "fal-ai/recraft/upscale/crisp": "fal-ai/recraft/upscale/crisp",
    "fal-ai/recraft/upscale/creative": "fal-ai/recraft/upscale/creative",
    "fal-ai/esrgan": "fal-ai/esrgan",
    # НЕ добавляем fal-ai/nano-banana/edit, чтобы _base_model_path вернул базовый путь fal-ai/nano-banana
    # для использования в queue_status (Fal.ai использует базовый путь в URL статуса)
}

for override_candidate in (
    getattr(settings, "fal_upscale_model", None),
    getattr(settings, "fal_upscale_fallback_model", None),
):
    if override_candidate:
        normalized_candidate = override_candidate.strip("/")
        if normalized_candidate.startswith("fal-ai/recraft/upscale/") or normalized_candidate.startswith("fal-ai/esrgan"):
            QUEUE_BASE_OVERRIDES[normalized_candidate] = normalized_candidate


def _base_model_path(model: str) -> str:
    normalized = _normalize_path(model)
    override = QUEUE_BASE_OVERRIDES.get(normalized)
    if override:
        return override
    parts = normalized.split("/")
    if len(parts) > 2:
        return "/".join(parts[:-1])
    return normalized


def _get_headers(content_type: bool = True) -> dict[str, str]:
    headers = {"Authorization": f"Key {settings.fal_api_key}"}
    if content_type:
        headers["Content-Type"] = "application/json"
    return headers


def _log_request(method: str, url: str, payload: dict | None) -> None:
    logger.debug("fal request: {} {} payload={}", method, url, payload)


def _log_response(url: str, status: int, data: dict | str) -> None:
    logger.debug("fal response: {} {} -> {}", url, status, data)


def queue_submit(model: str, payload: dict) -> dict:
    url = _build_queue_url(model)
    _log_request("POST", url, payload)
    
    # Use custom timeout for queue submissions with longer connect timeout for SSL
    queue_timeout = httpx.Timeout(
        connect=30.0,  # Increased for SSL handshake
        read=60.0,
        write=30.0,
        pool=30.0,
    )
    
    last_error: Exception | None = None
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            client = _get_http_client()
            response = client.post(url, json=payload, headers=_get_headers(), timeout=queue_timeout)
            if response.is_error:
                _log_response(url, response.status_code, response.text)
                response.raise_for_status()
            data = response.json()
            _log_response(url, response.status_code, data)
            return data
        except (httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            last_error = e
            if attempt < max_attempts - 1:
                wait_time = 2.0 * (attempt + 1)
                logger.warning(
                    "Queue submit attempt {}/{} failed with timeout: {}. Retrying in {:.1f}s",
                    attempt + 1, max_attempts, e, wait_time
                )
                time.sleep(wait_time)
                continue
            raise
        except Exception as e:
            # For other errors, don't retry
            _log_response(url, 0, str(e))
            raise
    
    # Should not reach here, but just in case
    if last_error:
        raise last_error
    raise RuntimeError("Queue submit failed after retries")


def run_model(model: str, payload: dict) -> dict:
    model_path = _normalize_path(model)
    url = f"{RUN_BASE_URL}/{model_path}"
    _log_request("POST", url, payload)
    timeout = httpx.Timeout(
        connect=RUN_CONNECT_TIMEOUT,
        read=RUN_READ_TIMEOUT,
        write=RUN_WRITE_TIMEOUT,
        pool=30.0,
    )
    last_error: Exception | None = None
    for attempt in range(RUN_MAX_ATTEMPTS):
        try:
            # Use global client for connection pooling, but with custom timeout
            client = _get_http_client()
            response = client.post(url, json=payload, headers=_get_headers(), timeout=timeout)
            if response.is_error:
                _log_response(url, response.status_code, response.text)
                response.raise_for_status()
            data = response.json()
            _log_response(url, response.status_code, data)
            return data
        except (httpx.TimeoutException, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
            last_error = exc
            logger.warning(
                "Attempt {}: run_model {} timed out: {}",
                attempt + 1,
                model,
                exc,
            )
            if attempt < RUN_MAX_ATTEMPTS - 1:
                time.sleep(RUN_RETRY_BACKOFF * (attempt + 1))
        except httpx.HTTPError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("Attempt {}: run_model {} failed: {}", attempt + 1, model, exc)
            if attempt < RUN_MAX_ATTEMPTS - 1:
                time.sleep(RUN_RETRY_BACKOFF * (attempt + 1))
    if last_error:
        raise last_error
    raise RuntimeError("run_model failed without explicit error")


def queue_get(url: str) -> dict:
    _log_request("GET", url, None)
    client = _get_http_client()
    response = client.get(url, headers=_get_headers(content_type=False))
    if response.is_error:
        _log_response(url, response.status_code, response.text)
        response.raise_for_status()
    data = response.json()
    _log_response(url, response.status_code, data)
    return data


def queue_status(model: str, request_id: str) -> dict:
    base_model = _base_model_path(model)
    url = _build_queue_url(base_model, f"requests/{request_id}/status")
    logger.debug("📡 API REQUEST: queue_status GET {} (request_id: {})", url, request_id[:8])
    try:
        result = queue_get(url)
        logger.debug("📡 API RESPONSE: queue_status for {} -> status: {}", request_id[:8], result.get("status", "unknown"))
        return result
    except httpx.HTTPStatusError as exc:
        normalized = _normalize_path(model)
        if exc.response.status_code == 404 and base_model != normalized:
            fallback_url = _build_queue_url(normalized, f"requests/{request_id}/status")
            logger.debug("📡 API REQUEST: queue_status fallback GET {} (request_id: {})", fallback_url, request_id[:8])
            return queue_get(fallback_url)
        raise


def queue_result(model: str, request_id: str) -> dict:
    """
    Get result from fal.ai queue API.
    
    For Seedream v4.5/edit and similar models, fal.ai requires POST request with requestId in body:
    POST /fal-ai/bytedance/seedream/v4.5/edit
    Body: {"requestId": "..."}
    
    For other models, we try GET requests to various endpoints.
    """
    # Check if this is a Seedream model that requires POST with requestId in body
    normalized = _normalize_path(model)
    is_seedream = "seedream" in normalized.lower()
    
    if is_seedream:
        # For Seedream, use POST with requestId in body according to fal.ai documentation
        # https://fal.ai/models/fal-ai/bytedance/seedream/v4.5/edit/api
        url = _build_queue_url(model)
        payload = {"requestId": request_id}
        _log_request("POST", url, payload)
        
        max_retries = 3
        retry_delay = 1.0
        last_error: Exception | None = None
        
        for attempt in range(max_retries):
            try:
                client = _get_http_client()
                queue_timeout = httpx.Timeout(
                    connect=30.0,
                    read=60.0,
                    write=30.0,
                    pool=30.0,
                )
                response = client.post(url, json=payload, headers=_get_headers(), timeout=queue_timeout)
                if response.is_error:
                    _log_response(url, response.status_code, response.text)
                    response.raise_for_status()
                data = response.json()
                _log_response(url, response.status_code, data)
                logger.debug("queue_result {} succeeded for seedream on attempt {}", request_id, attempt + 1)
                return data
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code
                response_text = exc.response.text[:200] if hasattr(exc.response, 'text') else str(exc)
                retryable_header = exc.response.headers.get("X-Fal-Retryable", "not set")
                logger.debug("queue_result {} -> {} {} (X-Fal-Retryable: {})", 
                            url, status_code, response_text, retryable_header)
                
                # Retry on server errors (500, 502, 503) and auth errors (401)
                if status_code in (500, 502, 503, 401) and attempt < max_retries - 1:
                    logger.warning(
                        "queue_result {} attempt {} failed with {}: {} (X-Fal-Retryable: {}). Retrying in {:.1f}s",
                        request_id,
                        attempt + 1,
                        status_code,
                        response_text,
                        retryable_header,
                        retry_delay,
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    logger.error("queue_result {} failed after {} attempts with {}: {} (X-Fal-Retryable: {})", 
                                request_id, max_retries, status_code, response_text, retryable_header)
                    raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < max_retries - 1:
                    logger.warning("queue_result {} attempt {} failed: {}. Retrying in {:.1f}s", 
                                  request_id, attempt + 1, exc, retry_delay)
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                raise
        
        if last_error:
            raise last_error
        raise RuntimeError("queue_result failed without HTTP error")
    
    # For non-Seedream models, use GET requests to various endpoints (original logic)
    base_model = _base_model_path(model)
    candidate_paths: list[str] = [
        _build_queue_url(base_model, f"requests/{request_id}"),
    ]
    if base_model != normalized:
        candidate_paths.append(_build_queue_url(normalized, f"requests/{request_id}"))
    candidate_paths.append(_build_queue_url(base_model, f"requests/{request_id}/response"))
    candidate_paths.append(_build_queue_url(base_model, f"requests/{request_id}/result"))
    if base_model != normalized:
        candidate_paths.append(_build_queue_url(normalized, f"requests/{request_id}/response"))
        candidate_paths.append(_build_queue_url(normalized, f"requests/{request_id}/result"))

    # Retry logic for server errors (500, 502, 503)
    max_retries = 3
    retry_delay = 1.0
    last_error: httpx.HTTPStatusError | None = None
    
    for attempt in range(max_retries):
        last_error = None
        for candidate in candidate_paths:
            try:
                result = queue_get(candidate)
                logger.debug("queue_result {} succeeded on attempt {} with candidate {}", request_id, attempt + 1, candidate)
                return result
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code
                response_text = exc.response.text[:200] if hasattr(exc.response, 'text') else str(exc)
                
                # Log response headers for debugging
                retryable_header = exc.response.headers.get("X-Fal-Retryable", "not set")
                logger.debug("queue_result {} -> {} {} (X-Fal-Retryable: {})", 
                            candidate, status_code, response_text, retryable_header)
                
                # Retry on server errors (500, 502, 503) and auth errors (401) - may be temporary
                if status_code in (500, 502, 503, 401):
                    if attempt < max_retries - 1:
                        logger.warning(
                            "queue_result {} attempt {} failed with {}: {} (X-Fal-Retryable: {}). Retrying all candidates in {:.1f}s",
                            request_id,
                            attempt + 1,
                            status_code,
                            response_text,
                            retryable_header,
                            retry_delay,
                        )
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        break  # Retry from first candidate
                    else:
                        # Last attempt failed, raise with detailed error
                        logger.error("queue_result {} failed after {} attempts with {}: {} (X-Fal-Retryable: {})", 
                                    request_id, max_retries, status_code, response_text, retryable_header)
                        raise
                # Don't retry on client errors (404, 405, 422) - try next candidate
                elif status_code in (404, 405, 422):
                    logger.debug("queue_result {} -> {} (trying next candidate)", candidate, status_code)
                    continue  # Try next candidate
                else:
                    # Other errors - raise immediately
                    logger.error("queue_result {} -> {} (non-retryable)", candidate, status_code)
                    raise
        
        # If we got here and last_error is None, we succeeded (shouldn't happen, but just in case)
        if last_error is None:
            break
    
    if last_error:
        raise last_error
    raise RuntimeError("queue_result failed without HTTP error")


def download_file(url: str, target_path: str) -> None:
    import time as time_module
    start_time = time_module.time()
    logger.info("📥 DOWNLOAD START: {} -> {}", url[:80], target_path)
    last_error: Exception | None = None
    for attempt in range(DOWNLOAD_MAX_ATTEMPTS):
        try:
            attempt_start = time_module.time()
            logger.info("📥 DOWNLOAD attempt {}/{}: connecting to {} (timeout: connect={}s, read={}s)", 
                       attempt + 1, DOWNLOAD_MAX_ATTEMPTS, url[:80], DOWNLOAD_CONNECT_TIMEOUT, DOWNLOAD_READ_TIMEOUT)
            
            # Use requests with proper SSL configuration
            # Disable SSL verification warnings but keep verification enabled
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Connection': 'keep-alive'
            })
            
            # Use tuple (connect_timeout, read_timeout) for requests
            timeout_tuple = (DOWNLOAD_CONNECT_TIMEOUT, DOWNLOAD_READ_TIMEOUT)
            
            request_start = time_module.time()
            
            # Skip HEAD request to speed up download - go straight to GET
            # Use streaming download with larger chunk size for better performance
            logger.info("📥 DOWNLOAD attempt {}: starting streaming download...", attempt + 1)
            response = session.get(url, stream=True, timeout=timeout_tuple, allow_redirects=True)
            response.raise_for_status()
            
            # Try to get file size from Content-Length header (if available)
            content_length_header = response.headers.get("content-length")
            if content_length_header:
                file_size_mb = int(content_length_header) / (1024 * 1024)
                logger.info("📥 DOWNLOAD attempt {}: file size detected = {:.2f} MB", 
                           attempt + 1, file_size_mb)
            
            # Use larger chunk size (64KB instead of 8KB) for faster download
            chunk_size = 65536  # 64KB chunks for better performance
            content_length_downloaded = 0
            chunk_count = 0
            with open(target_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        file.write(chunk)
                        content_length_downloaded += len(chunk)
                        chunk_count += 1
                        # Логируем прогресс каждые 50 чанков (примерно каждые 3.2MB)
                        if chunk_count % 50 == 0:
                            downloaded_mb = content_length_downloaded / (1024 * 1024)
                            logger.info("📥 DOWNLOAD progress: {:.2f} MB downloaded...", downloaded_mb)
            
            content_size = content_length_downloaded
            total_time = time_module.time() - attempt_start
            logger.info("✅ DOWNLOAD COMPLETE: {} bytes ({:.2f} MB) saved to {} in {:.2f}s", 
                       content_size, content_size / (1024 * 1024), target_path, total_time)
            session.close()
            return
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.SSLError) as exc:
            last_error = exc
            logger.warning(
                "❌ DOWNLOAD attempt {} FAILED: {} -> {}",
                attempt + 1,
                url[:80],
                exc,
            )
            if attempt < DOWNLOAD_MAX_ATTEMPTS - 1:
                sleep_time = DOWNLOAD_RETRY_BACKOFF * (attempt + 1)
                logger.debug("Waiting {} seconds before retry...", sleep_time)
                time.sleep(sleep_time)
        except Exception as exc:
            last_error = exc
            logger.error("Unexpected error during download attempt {}: {}", attempt + 1, exc, exc_info=True)
            if attempt < DOWNLOAD_MAX_ATTEMPTS - 1:
                sleep_time = DOWNLOAD_RETRY_BACKOFF * (attempt + 1)
                logger.debug("Waiting {} seconds before retry...", sleep_time)
                time.sleep(sleep_time)
    if last_error:
        logger.error("All download attempts failed for {}: {}", url, last_error)
        raise last_error
