"""
Authentication Middleware for AgenticSeek

This module implements API key-based authentication to secure all endpoints.

Usage:
    1. Add to api.py:
        from security.patches.auth_middleware import verify_api_key, setup_auth
        setup_auth(api)

    2. Protect endpoints:
        @api.post("/query")
        async def process_query(
            request: Request,
            query_req: QueryRequest,
            api_key: str = Depends(verify_api_key)
        ):
            ...

    3. Set environment variable:
        AGENTICSEEK_API_KEYS="key1,key2,key3"
"""

import os
import secrets
import hashlib
from typing import Set, Optional
from fastapi import Security, HTTPException, Depends, Request
from fastapi.security import APIKeyHeader
from datetime import datetime
import logging

# Configure logging
logger = logging.getLogger("auth")

# API Key header name
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Load valid API keys from environment
def load_api_keys() -> Set[str]:
    """Load and hash API keys from environment variable"""
    keys_env = os.getenv("AGENTICSEEK_API_KEYS", "")

    if not keys_env:
        logger.warning("No API keys configured! Set AGENTICSEEK_API_KEYS environment variable")
        logger.warning("Generating temporary API key for development...")

        # Generate a temporary key for development
        temp_key = secrets.token_urlsafe(32)
        print("\n" + "=" * 70)
        print("⚠️  DEVELOPMENT MODE - Temporary API Key Generated:")
        print(f"    {temp_key}")
        print("=" * 70)
        print("Add to .env file:")
        print(f'AGENTICSEEK_API_KEYS="{temp_key}"')
        print("=" * 70 + "\n")

        return {hashlib.sha256(temp_key.encode()).hexdigest()}

    # Hash all keys for secure storage
    keys = keys_env.split(",")
    hashed_keys = {hashlib.sha256(key.strip().encode()).hexdigest() for key in keys if key.strip()}

    logger.info(f"Loaded {len(hashed_keys)} API keys")
    return hashed_keys

# Global set of valid API key hashes
VALID_API_KEY_HASHES = load_api_keys()

async def verify_api_key(
    api_key: Optional[str] = Security(api_key_header),
    request: Request = None
) -> str:
    """
    Verify API key from request header

    Args:
        api_key: API key from X-API-Key header
        request: FastAPI request object for logging

    Returns:
        str: The validated API key

    Raises:
        HTTPException: 403 if API key is invalid or missing
    """
    if not api_key:
        logger.warning(
            f"Missing API key - IP: {request.client.host if request else 'unknown'}"
        )
        raise HTTPException(
            status_code=403,
            detail="Missing API Key. Include 'X-API-Key' header in your request."
        )

    # Hash the provided key and compare
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    if key_hash not in VALID_API_KEY_HASHES:
        logger.warning(
            f"Invalid API key attempted - IP: {request.client.host if request else 'unknown'}, "
            f"Key prefix: {api_key[:8]}..."
        )
        raise HTTPException(
            status_code=403,
            detail="Invalid API Key"
        )

    # Log successful authentication
    logger.info(
        f"Authenticated request - IP: {request.client.host if request else 'unknown'}, "
        f"Key prefix: {api_key[:8]}..., "
        f"Path: {request.url.path if request else 'unknown'}"
    )

    return api_key

def setup_auth(app):
    """
    Setup authentication middleware for FastAPI app

    Args:
        app: FastAPI application instance

    Example:
        >>> from fastapi import FastAPI
        >>> api = FastAPI()
        >>> setup_auth(api)
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('.logs/auth.log'),
            logging.StreamHandler()
        ]
    )

    logger.info("Authentication middleware initialized")
    logger.info(f"API key header: {API_KEY_NAME}")

    # Add startup event
    @app.on_event("startup")
    async def startup_event():
        if not os.getenv("AGENTICSEEK_API_KEYS"):
            logger.warning("⚠️  Running without configured API keys!")
            logger.warning("This is ONLY acceptable for local development")
            logger.warning("Set AGENTICSEEK_API_KEYS for production use")

def generate_api_key() -> str:
    """
    Generate a new secure API key

    Returns:
        str: URL-safe random API key

    Example:
        >>> key = generate_api_key()
        >>> print(f"New API key: {key}")
    """
    key = secrets.token_urlsafe(32)
    logger.info(f"Generated new API key: {key[:8]}...")
    return key

# Optional: Rate limiting per API key
from collections import defaultdict
from datetime import timedelta

class APIKeyRateLimiter:
    """Rate limiter based on API key"""

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)

    def check_rate_limit(self, api_key: str) -> bool:
        """
        Check if API key has exceeded rate limit

        Args:
            api_key: The API key to check

        Returns:
            bool: True if within limit, False if exceeded

        Example:
            >>> limiter = APIKeyRateLimiter(requests_per_minute=10)
            >>> if not limiter.check_rate_limit(api_key):
            ...     raise HTTPException(status_code=429, detail="Rate limit exceeded")
        """
        now = datetime.now()
        one_minute_ago = now - timedelta(minutes=1)

        # Clean old requests
        self.requests[api_key] = [
            req_time for req_time in self.requests[api_key]
            if req_time > one_minute_ago
        ]

        # Check limit
        if len(self.requests[api_key]) >= self.requests_per_minute:
            return False

        # Add current request
        self.requests[api_key].append(now)
        return True

# Global rate limiter instance
rate_limiter = APIKeyRateLimiter(requests_per_minute=60)

async def check_rate_limit(
    api_key: str = Depends(verify_api_key)
):
    """
    Dependency to check rate limit

    Usage:
        @api.post("/query")
        async def process_query(
            request: QueryRequest,
            _: None = Depends(check_rate_limit)
        ):
            ...
    """
    if not rate_limiter.check_rate_limit(api_key):
        logger.warning(f"Rate limit exceeded for key: {api_key[:8]}...")
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later."
        )

if __name__ == "__main__":
    # Generate sample API keys
    print("Generating 3 sample API keys:\n")
    for i in range(3):
        key = generate_api_key()
        print(f"API Key {i+1}: {key}")

    print("\nAdd these to your .env file:")
    print(f'AGENTICSEEK_API_KEYS="key1,key2,key3"')
