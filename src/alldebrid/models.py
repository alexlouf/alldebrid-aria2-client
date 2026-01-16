"""AllDebrid API response models."""

from typing import List, Optional
from pydantic import BaseModel, Field


class AllDebridError(BaseModel):
    """AllDebrid API error response."""

    code: str
    message: str


class MagnetUploadResponse(BaseModel):
    """Response from magnet upload endpoint."""

    id: int
    filename: str
    size: int
    hash: str
    ready: bool
    error: Optional[AllDebridError] = None


class MagnetStatusFile(BaseModel):
    """File information in magnet status."""

    n: str = Field(..., description="Filename")
    s: int = Field(..., description="Size in bytes")
    e: Optional[List[str]] = Field(default=None, description="Links")


class MagnetStatusResponse(BaseModel):
    """Response from magnet status endpoint."""

    id: int
    filename: str
    size: int
    status: str
    statusCode: int
    downloaded: int
    uploaded: int
    seeders: int
    downloadSpeed: float
    uploadSpeed: float
    uploadDate: int
    completionDate: Optional[int] = None
    links: List[str] = Field(default_factory=list)
    files: Optional[List[MagnetStatusFile]] = None
    error: Optional[AllDebridError] = None


class UnlockLinkResponse(BaseModel):
    """Response from link unlock endpoint."""

    link: str
    filename: str
    host: str
    filesize: int
    id: str
    streaming: List[dict] = Field(default_factory=list)
    error: Optional[AllDebridError] = None


class UserResponse(BaseModel):
    """Response from user endpoint."""

    username: str
    email: str
    isPremium: bool
    premiumUntil: Optional[int] = None
    lang: str
    error: Optional[AllDebridError] = None
