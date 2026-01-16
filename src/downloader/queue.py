"""Intelligent download queue manager."""

import asyncio
from typing import List, Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..database import crud
from ..database.models import Torrent
from ..utils.logger import logger
from ..utils.config import settings
from .aria2 import Aria2Manager
from ..alldebrid.client import AllDebridClient


class DownloadQueue:
    """
    Intelligent download queue manager.

    Manages download priorities based on file size and storage type:
    - HDD: 1 large file (>20GB) at a time, or 3 small files
    - SSD: Up to 5 concurrent downloads
    """

    def __init__(self, aria2: Aria2Manager, alldebrid: AllDebridClient):
        """
        Initialize queue manager.

        Args:
            aria2: Aria2 manager instance
            alldebrid: AllDebrid client instance
        """
        self.aria2 = aria2
        self.alldebrid = alldebrid
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the queue processor."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._process_queue())
        logger.info("Download queue processor started")

    async def stop(self):
        """Stop the queue processor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Download queue processor stopped")

    async def _process_queue(self):
        """Main queue processing loop."""
        while self._running:
            try:
                async for session in crud.get_session():
                    await self._process_queued_torrents(session)
                    await self._update_downloading_torrents(session)

                # Wait before next iteration
                await asyncio.sleep(5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in queue processor: {e}", exc_info=True)
                await asyncio.sleep(10)

    async def _process_queued_torrents(self, session: AsyncSession):
        """Process torrents in queued state."""
        # Get queued torrents
        queued = await crud.get_torrents_by_state(session, "queued")
        if not queued:
            return

        # Get currently downloading torrents
        downloading = await crud.get_torrents_by_state(session, "downloading")

        # Check if we can start new downloads
        can_start = await self._can_start_download(downloading)
        if not can_start:
            return

        # Start the first queued torrent
        torrent = queued[0]
        await self._start_torrent_download(session, torrent)

    async def _can_start_download(self, downloading: List[Torrent]) -> bool:
        """
        Check if we can start a new download based on current downloads.

        Args:
            downloading: List of currently downloading torrents

        Returns:
            True if we can start a new download
        """
        if not downloading:
            return True

        storage_type = self.aria2.storage_type

        if storage_type == "hdd":
            # Check if any large file is downloading
            large_files = [
                t for t in downloading if t.size > settings.size_threshold_gb * 1024**3
            ]
            if large_files:
                # Only 1 large file at a time on HDD
                return False

            # Allow up to 3 small files
            return len(downloading) < settings.simultaneous_small_files

        else:  # SSD
            # Allow up to 5 concurrent downloads on SSD
            return len(downloading) < 5

    async def _start_torrent_download(self, session: AsyncSession, torrent: Torrent):
        """
        Start downloading a torrent.

        Args:
            session: Database session
            torrent: Torrent to download
        """
        try:
            logger.info(f"Starting download for torrent {torrent.hash}")

            # Upload magnet to AllDebrid
            upload_result = await self.alldebrid.upload_magnet(torrent.magnet_uri)

            # Update torrent with AllDebrid ID
            await crud.update_torrent(
                session,
                torrent.hash,
                alldebrid_id=upload_result.id,
                size=upload_result.size,
            )

            # Wait for AllDebrid to process the torrent
            try:
                status = await self.alldebrid.wait_for_magnet_ready(
                    upload_result.id, timeout=300
                )
            except TimeoutError:
                await crud.mark_torrent_error(
                    session, torrent.hash, "AllDebrid processing timeout"
                )
                return

            # Get download link
            if not status.links:
                await crud.mark_torrent_error(
                    session, torrent.hash, "No download links available"
                )
                return

            download_link = status.links[0]

            # Unlock the link
            unlock_result = await self.alldebrid.unlock_link(download_link)

            # Start aria2 download
            filename = unlock_result.filename or torrent.name
            gid = await self.aria2.add_download(
                unlock_result.link,
                filename=filename,
                path=torrent.save_path,
            )

            # Update torrent state
            await crud.update_torrent(
                session,
                torrent.hash,
                state="downloading",
                aria2_gid=gid,
                download_link=unlock_result.link,
                name=filename,
                size=unlock_result.filesize,
            )

            logger.info(f"Started downloading {filename} (GID: {gid})")

        except Exception as e:
            logger.error(f"Failed to start download for {torrent.hash}: {e}")
            await crud.mark_torrent_error(session, torrent.hash, str(e))

    async def _update_downloading_torrents(self, session: AsyncSession):
        """Update status of downloading torrents."""
        downloading = await crud.get_torrents_by_state(session, "downloading")

        for torrent in downloading:
            if not torrent.aria2_gid:
                continue

            try:
                # Get aria2 status
                status = await self.aria2.get_download_status(torrent.aria2_gid)
                if not status:
                    continue

                # Calculate progress and ETA
                progress = status["progress"] / 100.0
                dlspeed = status["download_speed"]
                downloaded = status["completed_length"]
                total = status["total_length"]

                eta = 0
                if dlspeed > 0:
                    remaining = total - downloaded
                    eta = int(remaining / dlspeed)

                # Update torrent
                update_data = {
                    "progress": progress,
                    "dlspeed": dlspeed,
                    "downloaded": downloaded,
                    "size": total,
                    "eta": eta,
                }

                # Check if completed
                if status["status"] == "complete":
                    update_data["state"] = "completed"
                    update_data["completion_on"] = datetime.utcnow()
                    update_data["progress"] = 1.0
                    update_data["dlspeed"] = 0
                    update_data["eta"] = 0
                    logger.info(f"Download completed: {torrent.name}")

                # Check for errors
                elif status["status"] == "error":
                    error_msg = status.get("error_message", "Unknown error")
                    await crud.mark_torrent_error(session, torrent.hash, error_msg)
                    continue

                await crud.update_torrent(session, torrent.hash, **update_data)

            except Exception as e:
                logger.error(f"Failed to update torrent {torrent.hash}: {e}")
