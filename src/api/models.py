"""Pydantic models for API requests/responses."""

from typing import Optional, List
from pydantic import BaseModel, Field


class TorrentAddRequest(BaseModel):
    """Request model for adding torrents."""

    urls: str = Field(..., description="Magnet URI or torrent URL")
    category: Optional[str] = Field(None, description="Category (sonarr/radarr)")
    savepath: Optional[str] = Field(None, description="Custom save path")


class TorrentInfo(BaseModel):
    """Torrent information model (qBittorrent format)."""

    hash: str
    name: str
    size: int
    progress: float
    dlspeed: int
    upspeed: int
    eta: int
    state: str
    category: str
    save_path: str
    completion_on: int
    added_on: int
    completed: int
    downloaded: int
    uploaded: int
    ratio: float


class AppPreferences(BaseModel):
    """Application preferences model."""

    save_path: str
    temp_path: str = ""
    max_active_downloads: int
    max_active_uploads: int = 0
    queueing_enabled: bool = True


class AppVersion(BaseModel):
    """Application version model."""

    version: str = "v4.5.0"
