#!/usr/bin/env python3
"""
API Key Generation Tool

Generates secure API keys for AgenticSeek and helps manage them.

Usage:
    # Generate a single key
    python generate_api_keys.py

    # Generate multiple keys
    python generate_api_keys.py --count 5

    # Generate keys with custom length
    python generate_api_keys.py --length 48

    # Export to .env file
    python generate_api_keys.py --export
"""

import argparse
import secrets
import sys
import hashlib
from pathlib import Path
from typing import List

class APIKeyGenerator:
    """Generate and manage secure API keys"""

    def __init__(self, key_length: int = 32):
        """
        Initialize generator

        Args:
            key_length: Length of generated keys in bytes
        """
        self.key_length = key_length

    def generate_key(self) -> str:
        """
        Generate a single API key

        Returns:
            str: URL-safe random API key
        """
        return secrets.token_urlsafe(self.key_length)

    def generate_multiple(self, count: int) -> List[str]:
        """
        Generate multiple API keys

        Args:
            count: Number of keys to generate

        Returns:
            List[str]: List of API keys
        """
        return [self.generate_key() for _ in range(count)]

    def hash_key(self, key: str) -> str:
        """
        Hash API key for secure storage

        Args:
            key: API key to hash

        Returns:
            str: SHA-256 hash of key
        """
        return hashlib.sha256(key.encode()).hexdigest()

    def export_to_env(self, keys: List[str], env_file: str = ".env"):
        """
        Export keys to .env file

        Args:
            keys: List of API keys
            env_file: Path to .env file
        """
        env_path = Path(env_file)

        # Read existing .env content
        if env_path.exists():
            with open(env_path, 'r') as f:
                lines = f.readlines()

            # Remove existing AGENTICSEEK_API_KEYS line
            lines = [line for line in lines if not line.startswith('AGENTICSEEK_API_KEYS')]
        else:
            lines = []

        # Add new keys
        keys_str = ','.join(keys)
        lines.append(f'AGENTICSEEK_API_KEYS="{keys_str}"\n')

        # Write back
        with open(env_path, 'w') as f:
            f.writelines(lines)

        print(f"\n✅ Keys exported to {env_file}")

    def print_keys(self, keys: List[str], show_hashes: bool = False):
        """
        Print generated keys in a formatted way

        Args:
            keys: List of API keys
            show_hashes: Whether to show key hashes
        """
        print("\n" + "=" * 70)
        print("🔑 Generated API Keys")
        print("=" * 70)
        print()

        for i, key in enumerate(keys, 1):
            print(f"Key {i}:")
            print(f"  Plain: {key}")

            if show_hashes:
                hashed = self.hash_key(key)
                print(f"  Hash:  {hashed}")

            print()

        print("=" * 70)
        print("⚠️  IMPORTANT:")
        print("  - Store these keys securely")
        print("  - Never commit them to git")
        print("  - Share them only via secure channels")
        print("  - Rotate them regularly (every 90 days)")
        print("=" * 70)
        print()

    def create_user_guide(self, keys: List[str]) -> str:
        """
        Create user guide for API keys

        Args:
            keys: List of API keys

        Returns:
            str: User guide text
        """
        guide = f"""
API Key Usage Guide
==================

You have been assigned {len(keys)} API key(s) for AgenticSeek.

SETUP
-----
1. Add this to your .env file:

   AGENTICSEEK_API_KEYS="{','.join(keys)}"

2. Set allowed origins (for CORS):

   ALLOWED_ORIGINS="https://your-domain.com"

3. Start the secure API:

   python api_secure.py


MAKING REQUESTS
---------------
Include the API key in the X-API-Key header:

  curl -X POST http://localhost:7777/query \\
    -H "Content-Type: application/json" \\
    -H "X-API-Key: {keys[0]}" \\
    -d '{{"query": "What is 2+2?", "tts_enabled": false}}'


SECURITY BEST PRACTICES
-----------------------
✅ DO:
  - Store keys in environment variables
  - Use HTTPS in production
  - Rotate keys every 90 days
  - Use different keys for different environments
  - Revoke keys immediately if compromised

❌ DON'T:
  - Commit keys to git
  - Share keys via email or chat
  - Use the same key across multiple environments
  - Log keys in plaintext
  - Hard-code keys in your application


TROUBLESHOOTING
---------------
403 Forbidden: Your API key is invalid or missing
429 Too Many Requests: You've exceeded the rate limit (60 requests/min)
500 Internal Server Error: Contact support


SUPPORT
-------
For issues or questions, contact: security@company.com

Generated: {import_module('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return guide


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Generate secure API keys for AgenticSeek'
    )
    parser.add_argument(
        '--count', '-c',
        type=int,
        default=1,
        help='Number of keys to generate (default: 1)'
    )
    parser.add_argument(
        '--length', '-l',
        type=int,
        default=32,
        help='Key length in bytes (default: 32)'
    )
    parser.add_argument(
        '--export', '-e',
        action='store_true',
        help='Export keys to .env file'
    )
    parser.add_argument(
        '--show-hashes',
        action='store_true',
        help='Show key hashes (for verification)'
    )
    parser.add_argument(
        '--guide', '-g',
        action='store_true',
        help='Generate user guide'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.count < 1 or args.count > 100:
        print("Error: Count must be between 1 and 100")
        sys.exit(1)

    if args.length < 16 or args.length > 128:
        print("Error: Length must be between 16 and 128")
        sys.exit(1)

    # Generate keys
    generator = APIKeyGenerator(key_length=args.length)
    keys = generator.generate_multiple(args.count)

    # Print keys
    generator.print_keys(keys, show_hashes=args.show_hashes)

    # Export if requested
    if args.export:
        generator.export_to_env(keys)

    # Generate guide if requested
    if args.guide:
        guide = generator.create_user_guide(keys)
        guide_file = "API_KEY_GUIDE.txt"

        with open(guide_file, 'w') as f:
            f.write(guide)

        print(f"📖 User guide saved to: {guide_file}")

    # Show next steps
    print("\n📋 Next Steps:")
    if not args.export:
        print("  1. Copy the key(s) above to your .env file")
        print("     AGENTICSEEK_API_KEYS=\"key1,key2\"")
    print("  2. Set ALLOWED_ORIGINS in .env")
    print("  3. Start the secure API: python api_secure.py")
    print("  4. Test with: curl -H 'X-API-Key: <key>' http://localhost:7777/health")
    print()


def import_module(name):
    """Import module dynamically"""
    import importlib
    return importlib.import_module(name)


if __name__ == "__main__":
    main()
