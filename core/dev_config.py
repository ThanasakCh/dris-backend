"""
Development Configuration

⚠️ WARNING: Set DEV_MODE to False before deploying to production!

This file controls development-only features.
Consider adding this file to .gitignore if you want to keep local settings.
"""

# Set to True to enable mock user (bypass authentication)
# Set to False for production or when testing real authentication
DEV_MODE = True

# Mock user ID for development (must be valid UUID format)
MOCK_USER_ID = "00000000-0000-0000-0000-000000000001"
MOCK_TOKEN = "dev-mock-token-12345"
