"""
Security middleware for Suzent.

Provides rate limiting, authentication, and security headers.
"""
import time
import hashlib
import secrets
from typing import Optional, Dict, Callable
from collections import defaultdict
from datetime import datetime, timedelta
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.datastructures import Headers
from suzent.logger import get_logger

logger = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using token bucket algorithm.
    
    Configuration:
        - requests_per_minute: Maximum requests per minute per IP
        - burst: Maximum burst size
    """
    
    def __init__(self, app, requests_per_minute: int = 60, burst: int = 20):
        super().__init__(app)
        self.rate = requests_per_minute / 60.0  # tokens per second
        self.burst = burst
        self.buckets: Dict[str, Dict] = defaultdict(
            lambda: {"tokens": burst, "last_update": time.time()}
        )
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
    
    def _check_rate_limit(self, client_ip: str) -> bool:
        """Check if request is within rate limit."""
        now = time.time()
        bucket = self.buckets[client_ip]
        
        # Add tokens based on time passed
        time_passed = now - bucket["last_update"]
        bucket["tokens"] = min(
            self.burst,
            bucket["tokens"] + time_passed * self.rate
        )
        bucket["last_update"] = now
        
        # Check if we have tokens available
        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True
        
        return False
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting."""
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/ready"]:
            return await call_next(request)
        
        client_ip = self._get_client_ip(request)
        
        if not self._check_rate_limit(client_ip):
            logger.warning(f"Rate limit exceeded for {client_ip}")
            return JSONResponse(
                {
                    "error": "Rate limit exceeded",
                    "message": f"Maximum {self.burst} requests per minute"
                },
                status_code=429,
                headers={"Retry-After": "60"}
            )
        
        response = await call_next(request)
        
        # Add rate limit headers
        bucket = self.buckets[client_ip]
        response.headers["X-RateLimit-Limit"] = str(int(self.rate * 60))
        response.headers["X-RateLimit-Remaining"] = str(int(bucket["tokens"]))
        
        return response


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """
    API key authentication middleware.
    
    Checks for API key in:
    1. Authorization header: "Bearer <key>"
    2. X-API-Key header: "<key>"
    3. Query parameter: "api_key=<key>"
    
    Configuration via environment:
        SUZENT_API_KEYS=key1,key2,key3
    """
    
    def __init__(self, app, api_keys: Optional[list] = None, 
                 public_paths: Optional[list] = None):
        super().__init__(app)
        self.api_keys = set(api_keys or [])
        self.public_paths = set(public_paths or ["/health", "/ready", "/metrics"])
        
        # Hash API keys for secure comparison
        self.api_key_hashes = {
            hashlib.sha256(key.encode()).hexdigest() 
            for key in self.api_keys
        }
    
    def _extract_api_key(self, request: Request) -> Optional[str]:
        """Extract API key from request."""
        # Check Authorization header
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        
        # Check X-API-Key header
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return api_key
        
        # Check query parameter
        return request.query_params.get("api_key")
    
    def _verify_api_key(self, api_key: str) -> bool:
        """Verify API key using constant-time comparison."""
        if not self.api_keys:
            # No keys configured - allow all
            return True
        
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        return secrets.compare_digest(key_hash, next(iter(self.api_key_hashes)))
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with authentication."""
        # Allow public paths
        if request.url.path in self.public_paths:
            return await call_next(request)
        
        # Allow OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # Extract and verify API key
        api_key = self._extract_api_key(request)
        
        if not api_key:
            logger.warning(f"Missing API key for {request.url.path}")
            return JSONResponse(
                {
                    "error": "Authentication required",
                    "message": "API key required in Authorization header or X-API-Key header"
                },
                status_code=401
            )
        
        if not self._verify_api_key(api_key):
            logger.warning(f"Invalid API key for {request.url.path}")
            return JSONResponse(
                {"error": "Invalid API key"},
                status_code=403
            )
        
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses.
    
    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security: max-age=31536000
    - Content-Security-Policy: default-src 'self'
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to response."""
        response = await call_next(request)
        
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # Enable XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # HSTS (only add for HTTPS)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Content Security Policy (restrictive for API)
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        
        # Remove server header for security
        if "Server" in response.headers:
            del response.headers["Server"]
        
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Log all requests with timing information.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request and response."""
        start_time = time.time()
        
        # Log request
        logger.info(
            f"Request: {request.method} {request.url.path} "
            f"from {request.client.host if request.client else 'unknown'}"
        )
        
        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise
        
        # Log response
        duration = time.time() - start_time
        logger.info(
            f"Response: {response.status_code} "
            f"in {duration*1000:.2f}ms"
        )
        
        # Add timing header
        response.headers["X-Response-Time"] = f"{duration*1000:.2f}ms"
        
        return response


def generate_api_key() -> str:
    """Generate a secure random API key."""
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()
