"""Configuration management using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # AllDebrid API
    alldebrid_api_key: str

    # Storage optimization
    storage_type: Literal["auto", "hdd", "ssd"] = "auto"
    aria2_connections: int = 16
    aria2_split: int = 1
    aria2_disk_cache: str = "128M"
    ram_buffer_per_download: str = "512M"
    max_concurrent_downloads: int = 2

    # Write optimization
    file_allocation: Literal["none", "prealloc", "falloc"] = "prealloc"
    write_batch_size: str = "64M"
    enable_mmap: bool = True

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Optional features
    enable_dashboard: bool = False
    auto_extract: bool = False

    # Paths
    download_path: str = "/downloads"
    config_path: str = "/config"

    # API Server
    api_host: str = "0.0.0.0"
    api_port: int = 6500

    # Queue strategy
    simultaneous_on_hdd: int = 1
    simultaneous_small_files: int = 3
    size_threshold_gb: int = 20


settings = Settings()
