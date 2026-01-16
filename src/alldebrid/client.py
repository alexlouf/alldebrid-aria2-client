"""AllDebrid API client with async httpx."""

import asyncio
from typing import Optional, List
from urllib.parse import quote

import httpx

from .models import (
    MagnetUploadResponse,
    MagnetStatusResponse,
    UnlockLinkResponse,
    UserResponse,
)
from ..utils.logger import logger
from ..utils.config import settings


class AllDebridClient:
    """Async client for AllDebrid API v4."""

    BASE_URL = "https://api.alldebrid.com/v4"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize AllDebrid client.

        Args:
            api_key: AllDebrid API key (uses settings if not provided)
        """
        self.api_key = api_key or settings.alldebrid_api_key
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=10),
        )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
        retries: int = 3,
    ) -> dict:
        """
        Make an API request with retry logic.

        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            data: Form data
            retries: Number of retries on failure

        Returns:
            JSON response as dictionary

        Raises:
            httpx.HTTPError: On request failure after retries
        """
        url = f"{self.BASE_URL}/{endpoint}"
        params = params or {}
        params["agent"] = "alldebrid-client"
        params["apikey"] = self.api_key

        for attempt in range(retries):
            try:
                if method == "GET":
                    response = await self.client.get(url, params=params)
                elif method == "POST":
                    response = await self.client.post(url, params=params, data=data)
                else:
                    raise ValueError(f"Unsupported method: {method}")

                response.raise_for_status()
                result = response.json()

                # Check for API errors
                if result.get("status") == "error":
                    error_msg = result.get("error", {}).get("message", "Unknown error")
                    logger.error(f"AllDebrid API error: {error_msg}")
                    raise httpx.HTTPError(error_msg)

                return result.get("data", result)

            except httpx.HTTPError as e:
                logger.warning(
                    f"AllDebrid API request failed (attempt {attempt + 1}/{retries}): {e}"
                )
                if attempt == retries - 1:
                    raise

                # Exponential backoff
                await asyncio.sleep(2 ** attempt)

        raise httpx.HTTPError("All retries failed")

    async def upload_magnet(self, magnet_uri: str) -> MagnetUploadResponse:
        """
        Upload a magnet link to AllDebrid.

        Args:
            magnet_uri: Magnet link

        Returns:
            MagnetUploadResponse with magnet ID and status
        """
        logger.info(f"Uploading magnet to AllDebrid")

        data = {"magnets[]": magnet_uri}
        result = await self._request("POST", "magnet/upload", data=data)

        # API returns data.magnets array
        magnets = result.get("magnets", [])
        if not magnets:
            raise ValueError("No magnet returned from AllDebrid")

        magnet_data = magnets[0]
        return MagnetUploadResponse(**magnet_data)

    async def get_magnet_status(self, magnet_id: int) -> MagnetStatusResponse:
        """
        Get the status of a magnet.

        Args:
            magnet_id: Magnet ID from upload

        Returns:
            MagnetStatusResponse with current status
        """
        result = await self._request("GET", "magnet/status", params={"id": magnet_id})

        # API returns data.magnets object
        magnet_data = result.get("magnets", {})
        return MagnetStatusResponse(**magnet_data)

    async def wait_for_magnet_ready(
        self, magnet_id: int, timeout: int = 300, poll_interval: int = 5
    ) -> MagnetStatusResponse:
        """
        Wait for a magnet to be ready for download.

        Args:
            magnet_id: Magnet ID
            timeout: Maximum wait time in seconds
            poll_interval: Polling interval in seconds

        Returns:
            MagnetStatusResponse when ready

        Raises:
            TimeoutError: If magnet is not ready within timeout
        """
        logger.info(f"Waiting for magnet {magnet_id} to be ready")

        elapsed = 0
        while elapsed < timeout:
            status = await self.get_magnet_status(magnet_id)

            if status.statusCode == 4:  # Ready
                logger.info(f"Magnet {magnet_id} is ready")
                return status
            elif status.statusCode in [5, 6, 7, 8, 11]:  # Error states
                error_msg = f"Magnet failed with status code {status.statusCode}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            logger.debug(
                f"Magnet {magnet_id} status: {status.status} "
                f"({status.downloaded}/{status.size} bytes)"
            )

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"Magnet {magnet_id} not ready after {timeout}s")

    async def unlock_link(self, link: str) -> UnlockLinkResponse:
        """
        Unlock a download link from AllDebrid.

        Args:
            link: Link to unlock (from magnet status)

        Returns:
            UnlockLinkResponse with direct download link
        """
        logger.info(f"Unlocking link from AllDebrid")

        result = await self._request("GET", "link/unlock", params={"link": link})
        return UnlockLinkResponse(**result)

    async def get_user_info(self) -> UserResponse:
        """
        Get user information.

        Returns:
            UserResponse with user details
        """
        result = await self._request("GET", "user")
        return UserResponse(**result.get("user", result))

    async def delete_magnet(self, magnet_id: int) -> bool:
        """
        Delete a magnet from AllDebrid.

        Args:
            magnet_id: Magnet ID to delete

        Returns:
            True if successful
        """
        logger.info(f"Deleting magnet {magnet_id} from AllDebrid")

        try:
            await self._request("GET", "magnet/delete", params={"id": magnet_id})
            return True
        except Exception as e:
            logger.error(f"Failed to delete magnet {magnet_id}: {e}")
            return False
