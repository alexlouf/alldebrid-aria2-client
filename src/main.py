"""Main application entry point."""

import asyncio
import signal
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
import uvicorn

from .utils.logger import logger
from .utils.config import settings
from .database import crud
from .downloader.aria2 import Aria2Manager
from .downloader.queue import DownloadQueue
from .alldebrid.client import AllDebridClient
from .api.routes import router


# Global instances
aria2_manager: Aria2Manager = None
download_queue: DownloadQueue = None
alldebrid_client: AllDebridClient = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown of services.
    """
    global aria2_manager, download_queue, alldebrid_client

    # Startup
    logger.info("Starting AllDebrid Client")
    logger.info(f"Version: 1.0.0")
    logger.info(f"Download path: {settings.download_path}")
    logger.info(f"Storage type: {settings.storage_type}")

    try:
        # Initialize database
        await crud.init_db()

        # Start aria2 manager
        aria2_manager = Aria2Manager()
        await aria2_manager.start()

        # Initialize AllDebrid client
        alldebrid_client = AllDebridClient()

        # Verify AllDebrid API key
        try:
            user_info = await alldebrid_client.get_user_info()
            logger.info(f"AllDebrid user: {user_info.username}")
            if not user_info.isPremium:
                logger.warning("AllDebrid account is not premium!")
        except Exception as e:
            logger.error(f"Failed to verify AllDebrid API key: {e}")
            sys.exit(1)

        # Start download queue processor
        download_queue = DownloadQueue(aria2_manager, alldebrid_client)
        await download_queue.start()

        logger.info("AllDebrid Client started successfully")

        yield

    except Exception as e:
        logger.error(f"Failed to start application: {e}", exc_info=True)
        sys.exit(1)

    finally:
        # Shutdown
        logger.info("Shutting down AllDebrid Client")

        if download_queue:
            await download_queue.stop()

        if aria2_manager:
            await aria2_manager.stop()

        if alldebrid_client:
            await alldebrid_client.close()

        logger.info("AllDebrid Client stopped")


# Create FastAPI app
app = FastAPI(
    title="AllDebrid Client",
    description="Optimized AllDebrid client with qBittorrent API compatibility",
    version="1.0.0",
    lifespan=lifespan,
)

# Include API routes
app.include_router(router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "AllDebrid Client",
        "version": "1.0.0",
        "status": "running",
        "storage_type": aria2_manager.storage_type if aria2_manager else "unknown",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "aria2": "running" if aria2_manager and aria2_manager.aria2 else "stopped",
        "queue": "running" if download_queue and download_queue._running else "stopped",
    }


@app.get("/metrics")
async def metrics():
    """
    Metrics endpoint for monitoring.

    Returns:
        Dictionary with metrics
    """
    if not aria2_manager or not aria2_manager.aria2:
        return {"error": "aria2 not running"}

    try:
        # Get aria2 stats
        stats = await aria2_manager.get_global_stats()

        # Get torrent counts
        async for session in crud.get_session():
            queued = await crud.get_torrents_by_state(session, "queued")
            downloading = await crud.get_torrents_by_state(session, "downloading")
            completed = await crud.get_torrents_by_state(session, "completed")
            errored = await crud.get_torrents_by_state(session, "error")

            return {
                "download_speed_mbps": stats["download_speed"] / (1024 * 1024),
                "active_downloads": stats["num_active"],
                "storage_type": aria2_manager.storage_type,
                "torrents_queued": len(queued),
                "torrents_downloading": len(downloading),
                "torrents_completed": len(completed),
                "torrents_errored": len(errored),
            }

    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        return {"error": str(e)}


def handle_signal(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, shutting down...")
    sys.exit(0)


def main():
    """Main entry point."""
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Run FastAPI app
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
