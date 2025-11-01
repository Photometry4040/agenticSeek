"""
Secure CORS Configuration for AgenticSeek

Replaces the insecure allow_origins=["*"] with a whitelist-based approach.

Usage:
    from security.patches.secure_cors import setup_secure_cors

    # In api.py, replace:
    # api.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

    # With:
    setup_secure_cors(api)
"""

import os
from typing import List
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

logger = logging.getLogger("cors")

def get_allowed_origins() -> List[str]:
    """
    Get allowed origins from environment variable

    Returns:
        List[str]: List of allowed origins

    Environment:
        ALLOWED_ORIGINS: Comma-separated list of allowed origins
        Example: "https://app.company.com,https://admin.company.com"
    """
    origins_env = os.getenv("ALLOWED_ORIGINS", "")

    if not origins_env:
        logger.warning("No ALLOWED_ORIGINS configured!")
        logger.warning("Defaulting to localhost for development")

        # Default to localhost for development
        return [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000"
        ]

    origins = [origin.strip() for origin in origins_env.split(",") if origin.strip()]
    logger.info(f"Loaded {len(origins)} allowed origins")

    return origins

def setup_secure_cors(app: FastAPI):
    """
    Setup secure CORS configuration

    Args:
        app: FastAPI application instance

    Security features:
    - Whitelist-based origins (no wildcards)
    - Restricted HTTP methods
    - Limited headers
    - Max age for preflight caching
    - Credentials support with specific origins

    Example:
        >>> from fastapi import FastAPI
        >>> api = FastAPI()
        >>> setup_secure_cors(api)
    """
    allowed_origins = get_allowed_origins()

    # Validate origins (should be HTTPS in production)
    for origin in allowed_origins:
        if not origin.startswith(('http://', 'https://')):
            logger.error(f"Invalid origin format: {origin}")
            raise ValueError(f"Origin must start with http:// or https://: {origin}")

        # Warn about HTTP in production
        if origin.startswith('http://') and 'localhost' not in origin and '127.0.0.1' not in origin:
            logger.warning(f"⚠️  Non-HTTPS origin in production: {origin}")

    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,  # ✓ Whitelist only
        allow_credentials=True,          # Allow cookies/auth headers
        allow_methods=[                  # ✓ Specific methods only
            "GET",
            "POST",
            "PUT",
            "DELETE",
            "OPTIONS"
        ],
        allow_headers=[                  # ✓ Specific headers only
            "Content-Type",
            "Authorization",
            "X-API-Key",
            "Accept",
            "Accept-Language",
            "Content-Language"
        ],
        expose_headers=[                 # Headers accessible to browser
            "X-Total-Count",
            "X-Page-Count"
        ],
        max_age=3600                     # Cache preflight for 1 hour
    )

    logger.info("Secure CORS middleware configured")
    logger.info(f"Allowed origins: {allowed_origins}")

def validate_origin(origin: str, allowed_origins: List[str]) -> bool:
    """
    Validate if origin is allowed

    Args:
        origin: The origin to validate
        allowed_origins: List of allowed origins

    Returns:
        bool: True if origin is allowed

    Example:
        >>> allowed = ["https://app.company.com"]
        >>> validate_origin("https://app.company.com", allowed)
        True
        >>> validate_origin("https://evil.com", allowed)
        False
    """
    if not origin:
        return False

    # Exact match only (no wildcards)
    return origin in allowed_origins

# Example configuration for different environments
EXAMPLE_CONFIGS = {
    "development": """
# .env for development
ALLOWED_ORIGINS="http://localhost:3000,http://localhost:8000"
""",

    "staging": """
# .env for staging
ALLOWED_ORIGINS="https://staging.company.com,https://staging-admin.company.com"
""",

    "production": """
# .env for production
ALLOWED_ORIGINS="https://app.company.com,https://admin.company.com"
"""
}

def print_example_configs():
    """Print example configurations for different environments"""
    print("\n" + "=" * 70)
    print("CORS Configuration Examples")
    print("=" * 70)

    for env, config in EXAMPLE_CONFIGS.items():
        print(f"\n{env.upper()}:")
        print(config)

    print("=" * 70 + "\n")

if __name__ == "__main__":
    # Print example configurations
    print_example_configs()

    # Test origin validation
    allowed = ["https://app.company.com", "https://admin.company.com"]

    test_cases = [
        ("https://app.company.com", True),
        ("https://admin.company.com", True),
        ("https://evil.com", False),
        ("http://app.company.com", False),  # Wrong protocol
        ("https://app.company.com:8080", False),  # Different port
    ]

    print("Origin Validation Tests:")
    for origin, expected in test_cases:
        result = validate_origin(origin, allowed)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {origin}: {'Allowed' if result else 'Blocked'}")
