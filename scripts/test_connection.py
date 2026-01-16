#!/usr/bin/env python3
"""Test script to verify AllDebrid connection and setup."""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.alldebrid.client import AllDebridClient
from src.utils.config import settings
from src.utils.logger import logger


async def main():
    """Test AllDebrid connection."""
    logger.info("Testing AllDebrid connection...")

    # Check if API key is set
    if not settings.alldebrid_api_key or settings.alldebrid_api_key == "your_api_key_here":
        logger.error("AllDebrid API key not set in .env file")
        sys.exit(1)

    try:
        async with AllDebridClient() as client:
            # Get user info
            logger.info("Fetching user information...")
            user_info = await client.get_user_info()

            logger.info(f"Username: {user_info.username}")
            logger.info(f"Email: {user_info.email}")
            logger.info(f"Premium: {user_info.isPremium}")

            if user_info.isPremium:
                logger.info("Account is premium - ready to use!")
            else:
                logger.warning("Account is not premium - downloads will not work")

    except Exception as e:
        logger.error(f"Connection failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
