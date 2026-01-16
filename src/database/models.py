"""SQLAlchemy database models."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, Boolean, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class Torrent(Base):
    """Torrent model for tracking download state."""

    __tablename__ = "torrents"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Torrent identification
    hash: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(512))
    magnet_uri: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    # AllDebrid info
    alldebrid_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    download_link: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    # Size info
    size: Mapped[int] = mapped_column(Integer, default=0)  # Total size in bytes
    downloaded: Mapped[int] = mapped_column(Integer, default=0)  # Downloaded bytes
    uploaded: Mapped[int] = mapped_column(Integer, default=0)  # Uploaded bytes (always 0)

    # Progress
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0.0 to 1.0

    # Speeds
    dlspeed: Mapped[int] = mapped_column(Integer, default=0)  # Download speed B/s
    upspeed: Mapped[int] = mapped_column(Integer, default=0)  # Upload speed B/s (always 0)

    # State
    state: Mapped[str] = mapped_column(
        String(32), default="queued", index=True
    )  # queued, downloading, completed, paused, error
    error_message: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # Category (for Sonarr/Radarr)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    # Paths
    save_path: Mapped[str] = mapped_column(String(512))

    # aria2 GID (for tracking)
    aria2_gid: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # Timestamps
    added_on: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completion_on: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Ratio (always 0 for AllDebrid)
    ratio: Mapped[float] = mapped_column(Float, default=0.0)

    # ETA in seconds
    eta: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        """String representation."""
        return f"<Torrent(hash={self.hash}, name={self.name}, state={self.state})>"

    def to_qbittorrent_dict(self) -> dict:
        """
        Convert to qBittorrent API format.

        Returns:
            Dictionary matching qBittorrent API response
        """
        return {
            "hash": self.hash,
            "name": self.name,
            "size": self.size,
            "progress": self.progress,
            "dlspeed": self.dlspeed,
            "upspeed": self.upspeed,
            "eta": self.eta,
            "state": self.state,
            "category": self.category or "",
            "save_path": self.save_path,
            "completion_on": int(self.completion_on.timestamp()) if self.completion_on else 0,
            "added_on": int(self.added_on.timestamp()),
            "completed": self.downloaded,
            "downloaded": self.downloaded,
            "uploaded": self.uploaded,
            "ratio": self.ratio,
        }
