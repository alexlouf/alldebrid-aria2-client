"""aria2 wrapper with optimizations for HDD storage."""

import asyncio
import os
from pathlib import Path
from typing import Optional, Dict, Any

import aria2p

from ..utils.logger import logger
from ..utils.config import settings
from ..utils.storage import detect_storage_type, get_optimal_aria2_config


class Aria2Manager:
    """Manager for aria2c downloads with HDD optimizations."""

    def __init__(self):
        """Initialize aria2 manager."""
        self.aria2: Optional[aria2p.API] = None
        self.client: Optional[aria2p.Client] = None
        self.storage_type = None
        self._aria2_process: Optional[asyncio.subprocess.Process] = None

    async def start(self):
        """Start aria2c daemon with optimized configuration."""
        # Detect storage type
        if settings.storage_type == "auto":
            self.storage_type = detect_storage_type(settings.download_path)
        else:
            self.storage_type = settings.storage_type

        logger.info(f"Starting aria2 with {self.storage_type.upper()} optimizations")

        # Get optimal configuration
        config = get_optimal_aria2_config(self.storage_type)

        # Override with user settings if provided
        if settings.aria2_connections:
            config["max-connection-per-server"] = settings.aria2_connections
        if settings.aria2_split:
            config["split"] = settings.aria2_split
        if settings.aria2_disk_cache:
            config["disk-cache"] = settings.aria2_disk_cache
        if settings.max_concurrent_downloads:
            config["max-concurrent-downloads"] = settings.max_concurrent_downloads

        # Build aria2c command
        aria2_cmd = [
            "aria2c",
            "--enable-rpc",
            "--rpc-listen-all=false",
            "--rpc-listen-port=6800",
            "--rpc-secret=",
            f"--dir={settings.download_path}",
            f"--log-level={settings.log_level.lower()}",
            "--console-log-level=warn",
            "--summary-interval=0",
        ]

        # Add configuration options
        for key, value in config.items():
            if isinstance(value, bool):
                if value:
                    aria2_cmd.append(f"--{key}=true")
                else:
                    aria2_cmd.append(f"--{key}=false")
            else:
                aria2_cmd.append(f"--{key}={value}")

        # Start aria2c process
        try:
            self._aria2_process = await asyncio.create_subprocess_exec(
                *aria2_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Wait for aria2 to start
            await asyncio.sleep(2)

            # Connect to aria2 RPC
            self.client = aria2p.Client(
                host="http://localhost",
                port=6800,
                secret="",
            )
            self.aria2 = aria2p.API(self.client)

            logger.info("aria2 daemon started successfully")

        except Exception as e:
            logger.error(f"Failed to start aria2: {e}")
            raise

    async def stop(self):
        """Stop aria2c daemon."""
        if self._aria2_process:
            logger.info("Stopping aria2 daemon")
            self._aria2_process.terminate()
            try:
                await asyncio.wait_for(self._aria2_process.wait(), timeout=10)
            except asyncio.TimeoutError:
                self._aria2_process.kill()
                await self._aria2_process.wait()

            logger.info("aria2 daemon stopped")

    async def add_download(
        self,
        url: str,
        filename: Optional[str] = None,
        path: Optional[str] = None,
    ) -> str:
        """
        Add a download to aria2.

        Args:
            url: Download URL
            filename: Custom filename (optional)
            path: Custom download path (optional)

        Returns:
            aria2 GID (download identifier)
        """
        if not self.aria2:
            raise RuntimeError("aria2 not started")

        options = {}
        if filename:
            options["out"] = filename
        if path:
            options["dir"] = path

        logger.info(f"Adding download: {filename or url}")

        download = self.aria2.add_uris([url], options=options)
        return download.gid

    async def get_download_status(self, gid: str) -> Optional[Dict[str, Any]]:
        """
        Get download status.

        Args:
            gid: aria2 GID

        Returns:
            Dictionary with download status or None if not found
        """
        if not self.aria2:
            raise RuntimeError("aria2 not started")

        try:
            download = self.aria2.get_download(gid)

            return {
                "gid": download.gid,
                "status": download.status,  # active, waiting, paused, error, complete, removed
                "total_length": download.total_length,
                "completed_length": download.completed_length,
                "download_speed": download.download_speed,
                "upload_speed": 0,  # Always 0 for direct downloads
                "progress": download.progress,
                "error_code": download.error_code,
                "error_message": download.error_message,
                "files": [
                    {
                        "path": f.path,
                        "length": f.length,
                        "completed_length": f.completed_length,
                    }
                    for f in download.files
                ],
            }
        except Exception as e:
            logger.warning(f"Failed to get status for GID {gid}: {e}")
            return None

    async def pause_download(self, gid: str) -> bool:
        """
        Pause a download.

        Args:
            gid: aria2 GID

        Returns:
            True if successful
        """
        if not self.aria2:
            raise RuntimeError("aria2 not started")

        try:
            download = self.aria2.get_download(gid)
            download.pause()
            logger.info(f"Paused download {gid}")
            return True
        except Exception as e:
            logger.error(f"Failed to pause download {gid}: {e}")
            return False

    async def resume_download(self, gid: str) -> bool:
        """
        Resume a paused download.

        Args:
            gid: aria2 GID

        Returns:
            True if successful
        """
        if not self.aria2:
            raise RuntimeError("aria2 not started")

        try:
            download = self.aria2.get_download(gid)
            download.resume()
            logger.info(f"Resumed download {gid}")
            return True
        except Exception as e:
            logger.error(f"Failed to resume download {gid}: {e}")
            return False

    async def remove_download(self, gid: str, delete_files: bool = False) -> bool:
        """
        Remove a download.

        Args:
            gid: aria2 GID
            delete_files: Whether to delete downloaded files

        Returns:
            True if successful
        """
        if not self.aria2:
            raise RuntimeError("aria2 not started")

        try:
            download = self.aria2.get_download(gid)

            # Get file path before removal
            file_paths = [f.path for f in download.files] if delete_files else []

            # Remove from aria2
            download.remove()

            # Delete files if requested
            if delete_files:
                for file_path in file_paths:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            logger.info(f"Deleted file {file_path}")
                    except Exception as e:
                        logger.warning(f"Failed to delete file {file_path}: {e}")

            logger.info(f"Removed download {gid}")
            return True

        except Exception as e:
            logger.error(f"Failed to remove download {gid}: {e}")
            return False

    async def get_global_stats(self) -> Dict[str, Any]:
        """
        Get global aria2 statistics.

        Returns:
            Dictionary with global stats
        """
        if not self.aria2:
            raise RuntimeError("aria2 not started")

        stats = self.aria2.get_global_stat()

        return {
            "download_speed": stats.download_speed,
            "upload_speed": 0,  # Always 0
            "num_active": stats.num_active,
            "num_waiting": stats.num_waiting,
            "num_stopped": stats.num_stopped,
        }
