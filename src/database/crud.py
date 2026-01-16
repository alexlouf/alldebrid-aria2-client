"""CRUD operations for database models."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.exc import IntegrityError

from .models import Base, Torrent
from ..utils.logger import logger
from ..utils.config import settings


# Database engine and session factory
engine = create_async_engine(
    f"sqlite+aiosqlite:///{settings.config_path}/torrents.db",
    echo=settings.log_level == "DEBUG",
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")


async def get_session() -> AsyncSession:
    """Get a database session."""
    async with async_session_maker() as session:
        yield session


# Torrent CRUD operations


async def create_torrent(
    session: AsyncSession,
    hash: str,
    name: str,
    magnet_uri: str,
    category: Optional[str] = None,
    save_path: Optional[str] = None,
) -> Torrent:
    """
    Create a new torrent entry.

    Args:
        session: Database session
        hash: Torrent hash
        name: Torrent name
        magnet_uri: Magnet URI
        category: Category (sonarr/radarr)
        save_path: Save path

    Returns:
        Created Torrent object

    Raises:
        IntegrityError: If torrent with hash already exists
    """
    save_path = save_path or f"{settings.download_path}/complete"

    torrent = Torrent(
        hash=hash,
        name=name,
        magnet_uri=magnet_uri,
        category=category,
        save_path=save_path,
        state="queued",
    )

    session.add(torrent)
    try:
        await session.commit()
        await session.refresh(torrent)
        logger.info(f"Created torrent {hash} - {name}")
        return torrent
    except IntegrityError:
        await session.rollback()
        logger.warning(f"Torrent {hash} already exists")
        raise


async def get_torrent_by_hash(session: AsyncSession, hash: str) -> Optional[Torrent]:
    """
    Get a torrent by hash.

    Args:
        session: Database session
        hash: Torrent hash

    Returns:
        Torrent object or None
    """
    result = await session.execute(select(Torrent).where(Torrent.hash == hash))
    return result.scalar_one_or_none()


async def get_all_torrents(session: AsyncSession) -> List[Torrent]:
    """
    Get all torrents.

    Args:
        session: Database session

    Returns:
        List of Torrent objects
    """
    result = await session.execute(select(Torrent))
    return list(result.scalars().all())


async def get_torrents_by_state(session: AsyncSession, state: str) -> List[Torrent]:
    """
    Get torrents by state.

    Args:
        session: Database session
        state: State filter

    Returns:
        List of Torrent objects
    """
    result = await session.execute(select(Torrent).where(Torrent.state == state))
    return list(result.scalars().all())


async def get_torrents_by_category(
    session: AsyncSession, category: str
) -> List[Torrent]:
    """
    Get torrents by category.

    Args:
        session: Database session
        category: Category filter

    Returns:
        List of Torrent objects
    """
    result = await session.execute(select(Torrent).where(Torrent.category == category))
    return list(result.scalars().all())


async def update_torrent(
    session: AsyncSession, hash: str, **kwargs
) -> Optional[Torrent]:
    """
    Update a torrent.

    Args:
        session: Database session
        hash: Torrent hash
        **kwargs: Fields to update

    Returns:
        Updated Torrent object or None
    """
    torrent = await get_torrent_by_hash(session, hash)
    if not torrent:
        return None

    for key, value in kwargs.items():
        if hasattr(torrent, key):
            setattr(torrent, key, value)

    await session.commit()
    await session.refresh(torrent)
    return torrent


async def delete_torrent(session: AsyncSession, hash: str) -> bool:
    """
    Delete a torrent.

    Args:
        session: Database session
        hash: Torrent hash

    Returns:
        True if deleted, False if not found
    """
    result = await session.execute(delete(Torrent).where(Torrent.hash == hash))
    await session.commit()

    if result.rowcount > 0:
        logger.info(f"Deleted torrent {hash}")
        return True
    else:
        logger.warning(f"Torrent {hash} not found for deletion")
        return False


async def mark_torrent_completed(session: AsyncSession, hash: str) -> Optional[Torrent]:
    """
    Mark a torrent as completed.

    Args:
        session: Database session
        hash: Torrent hash

    Returns:
        Updated Torrent object or None
    """
    return await update_torrent(
        session,
        hash,
        state="completed",
        progress=1.0,
        completion_on=datetime.utcnow(),
        dlspeed=0,
    )


async def mark_torrent_error(
    session: AsyncSession, hash: str, error_message: str
) -> Optional[Torrent]:
    """
    Mark a torrent as error.

    Args:
        session: Database session
        hash: Torrent hash
        error_message: Error message

    Returns:
        Updated Torrent object or None
    """
    return await update_torrent(
        session,
        hash,
        state="error",
        error_message=error_message,
        dlspeed=0,
    )
