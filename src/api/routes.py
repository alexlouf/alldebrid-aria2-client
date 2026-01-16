"""FastAPI routes for qBittorrent API emulation."""

import re
import hashlib
from typing import List, Optional

from fastapi import APIRouter, Form, HTTPException, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import crud
from ..database.models import Torrent
from ..utils.logger import logger
from ..utils.config import settings
from .models import TorrentInfo, AppPreferences, AppVersion


router = APIRouter(prefix="/api/v2")


# Helper function to extract hash from magnet
def extract_hash_from_magnet(magnet_uri: str) -> str:
    """
    Extract torrent hash from magnet URI.

    Args:
        magnet_uri: Magnet URI

    Returns:
        40-character hex hash
    """
    # Try to extract from btih parameter
    match = re.search(r"btih:([a-fA-F0-9]{40})", magnet_uri)
    if match:
        return match.group(1).lower()

    # Try to extract from base32 encoded hash
    match = re.search(r"btih:([a-zA-Z2-7]{32})", magnet_uri)
    if match:
        # Decode base32 to hex
        import base64

        hash_bytes = base64.b32decode(match.group(1))
        return hash_bytes.hex().lower()

    # Fallback: generate hash from magnet URI
    return hashlib.sha1(magnet_uri.encode()).hexdigest()


def extract_name_from_magnet(magnet_uri: str) -> str:
    """
    Extract torrent name from magnet URI.

    Args:
        magnet_uri: Magnet URI

    Returns:
        Torrent name or "Unknown"
    """
    match = re.search(r"dn=([^&]+)", magnet_uri)
    if match:
        from urllib.parse import unquote

        return unquote(match.group(1))
    return "Unknown"


# App endpoints


@router.get("/app/version", response_class=PlainTextResponse)
async def get_app_version() -> str:
    """Get application version."""
    return "v4.5.0"


@router.get("/app/webapiVersion", response_class=PlainTextResponse)
async def get_webapi_version() -> str:
    """Get Web API version."""
    return "2.8.0"


@router.get("/app/preferences")
async def get_app_preferences() -> AppPreferences:
    """Get application preferences."""
    return AppPreferences(
        save_path=settings.download_path,
        max_active_downloads=settings.max_concurrent_downloads,
    )


# Auth endpoints (dummy for compatibility)


@router.post("/auth/login")
async def login(username: str = Form(None), password: str = Form(None)) -> str:
    """
    Dummy login endpoint for compatibility.

    Args:
        username: Username (ignored)
        password: Password (ignored)

    Returns:
        "Ok."
    """
    return "Ok."


# Torrent endpoints


@router.post("/torrents/add")
async def add_torrent(
    urls: str = Form(...),
    category: Optional[str] = Form(None),
    savepath: Optional[str] = Form(None),
    session: AsyncSession = Depends(crud.get_session),
) -> str:
    """
    Add a torrent via magnet URI.

    Args:
        urls: Magnet URI(s) (newline separated)
        category: Category (sonarr/radarr)
        savepath: Custom save path
        session: Database session

    Returns:
        "Ok." on success

    Raises:
        HTTPException: On error
    """
    try:
        # Split multiple URLs (though usually just one)
        magnet_uris = [url.strip() for url in urls.split("\n") if url.strip()]

        for magnet_uri in magnet_uris:
            # Extract hash and name
            torrent_hash = extract_hash_from_magnet(magnet_uri)
            torrent_name = extract_name_from_magnet(magnet_uri)

            # Check if already exists
            existing = await crud.get_torrent_by_hash(session, torrent_hash)
            if existing:
                logger.warning(f"Torrent {torrent_hash} already exists")
                continue

            # Create torrent entry
            save_path = savepath or f"{settings.download_path}/complete"
            await crud.create_torrent(
                session,
                hash=torrent_hash,
                name=torrent_name,
                magnet_uri=magnet_uri,
                category=category,
                save_path=save_path,
            )

            logger.info(f"Added torrent {torrent_hash} - {torrent_name}")

        return "Ok."

    except Exception as e:
        logger.error(f"Failed to add torrent: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/torrents/info")
async def get_torrents_info(
    hashes: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    session: AsyncSession = Depends(crud.get_session),
) -> List[TorrentInfo]:
    """
    Get information about torrents.

    Args:
        hashes: Filter by hash (pipe-separated)
        category: Filter by category
        session: Database session

    Returns:
        List of torrent information
    """
    try:
        # Get torrents based on filters
        if hashes:
            hash_list = hashes.split("|")
            torrents = []
            for h in hash_list:
                torrent = await crud.get_torrent_by_hash(session, h)
                if torrent:
                    torrents.append(torrent)
        elif category:
            torrents = await crud.get_torrents_by_category(session, category)
        else:
            torrents = await crud.get_all_torrents(session)

        # Convert to qBittorrent format
        return [TorrentInfo(**t.to_qbittorrent_dict()) for t in torrents]

    except Exception as e:
        logger.error(f"Failed to get torrents info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/torrents/delete")
async def delete_torrents(
    hashes: str = Form(...),
    deleteFiles: bool = Form(False),
    session: AsyncSession = Depends(crud.get_session),
) -> str:
    """
    Delete torrents.

    Args:
        hashes: Torrent hashes (pipe-separated)
        deleteFiles: Whether to delete files
        session: Database session

    Returns:
        "Ok." on success
    """
    try:
        hash_list = hashes.split("|")

        for h in hash_list:
            torrent = await crud.get_torrent_by_hash(session, h)
            if not torrent:
                continue

            # Remove from aria2 if downloading
            if torrent.aria2_gid:
                # This will be handled by the queue manager
                pass

            # Delete files if requested
            if deleteFiles and torrent.save_path:
                import os
                from pathlib import Path

                # Find and delete files
                download_path = Path(torrent.save_path) / torrent.name
                if download_path.exists():
                    try:
                        if download_path.is_file():
                            download_path.unlink()
                        else:
                            import shutil

                            shutil.rmtree(download_path)
                        logger.info(f"Deleted files for {h}")
                    except Exception as e:
                        logger.warning(f"Failed to delete files for {h}: {e}")

            # Delete from database
            await crud.delete_torrent(session, h)

        return "Ok."

    except Exception as e:
        logger.error(f"Failed to delete torrents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/torrents/pause")
async def pause_torrents(
    hashes: str = Form(...),
    session: AsyncSession = Depends(crud.get_session),
) -> str:
    """
    Pause torrents.

    Args:
        hashes: Torrent hashes (pipe-separated)
        session: Database session

    Returns:
        "Ok." on success
    """
    try:
        hash_list = hashes.split("|")

        for h in hash_list:
            await crud.update_torrent(session, h, state="paused")
            logger.info(f"Paused torrent {h}")

        return "Ok."

    except Exception as e:
        logger.error(f"Failed to pause torrents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/torrents/resume")
async def resume_torrents(
    hashes: str = Form(...),
    session: AsyncSession = Depends(crud.get_session),
) -> str:
    """
    Resume paused torrents.

    Args:
        hashes: Torrent hashes (pipe-separated)
        session: Database session

    Returns:
        "Ok." on success
    """
    try:
        hash_list = hashes.split("|")

        for h in hash_list:
            torrent = await crud.get_torrent_by_hash(session, h)
            if not torrent:
                continue

            # Change state back to queued (will be picked up by queue manager)
            if torrent.state == "paused":
                await crud.update_torrent(session, h, state="queued")
                logger.info(f"Resumed torrent {h}")

        return "Ok."

    except Exception as e:
        logger.error(f"Failed to resume torrents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/torrents/recheck")
async def recheck_torrents(hashes: str = Form(...)) -> str:
    """
    Recheck torrents (dummy for compatibility).

    Args:
        hashes: Torrent hashes (pipe-separated)

    Returns:
        "Ok."
    """
    return "Ok."


@router.get("/torrents/categories")
async def get_categories() -> dict:
    """
    Get all categories.

    Returns:
        Dictionary of categories with name and savePath
    """
    return {
        "sonarr": {
            "name": "sonarr",
            "savePath": f"{settings.download_path}/complete"
        },
        "radarr": {
            "name": "radarr",
            "savePath": f"{settings.download_path}/complete"
        }
    }


@router.get("/torrents/properties")
async def get_torrent_properties(
    hash: str = Query(...),
    session: AsyncSession = Depends(crud.get_session),
) -> dict:
    """
    Get torrent properties.

    Args:
        hash: Torrent hash
        session: Database session

    Returns:
        Torrent properties
    """
    torrent = await crud.get_torrent_by_hash(session, hash)
    if not torrent:
        raise HTTPException(status_code=404, detail="Torrent not found")

    return {
        "save_path": torrent.save_path,
        "creation_date": int(torrent.added_on.timestamp()),
        "piece_size": 0,
        "comment": "",
        "total_wasted": 0,
        "total_uploaded": 0,
        "total_downloaded": torrent.downloaded,
        "up_limit": -1,
        "dl_limit": -1,
        "time_elapsed": int((datetime.utcnow() - torrent.added_on).total_seconds()),
        "seeding_time": 0,
        "nb_connections": 0,
        "share_ratio": 0.0,
    }


@router.get("/torrents/trackers")
async def get_torrent_trackers(hash: str = Query(...)) -> List[dict]:
    """
    Get torrent trackers (dummy for compatibility).

    Args:
        hash: Torrent hash

    Returns:
        Empty list (no trackers for direct downloads)
    """
    return []


@router.get("/torrents/files")
async def get_torrent_files(
    hash: str = Query(...),
    session: AsyncSession = Depends(crud.get_session),
) -> List[dict]:
    """
    Get torrent files.

    Args:
        hash: Torrent hash
        session: Database session

    Returns:
        List of files
    """
    torrent = await crud.get_torrent_by_hash(session, hash)
    if not torrent:
        raise HTTPException(status_code=404, detail="Torrent not found")

    return [
        {
            "index": 0,
            "name": torrent.name,
            "size": torrent.size,
            "progress": torrent.progress,
            "priority": 1,
            "is_seed": torrent.state == "completed",
        }
    ]


# Import datetime for properties endpoint
from datetime import datetime
