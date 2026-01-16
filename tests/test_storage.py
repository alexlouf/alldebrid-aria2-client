"""Tests for storage detection module."""

import pytest
from src.utils.storage import detect_storage_type, get_optimal_aria2_config


def test_detect_storage_type():
    """Test storage type detection."""
    # This will detect the actual storage type
    storage_type = detect_storage_type("/tmp")
    assert storage_type in ["hdd", "ssd"]


def test_get_optimal_aria2_config_hdd():
    """Test HDD configuration."""
    config = get_optimal_aria2_config("hdd")

    assert config["max-connection-per-server"] == 16
    assert config["split"] == 1
    assert config["min-split-size"] == "1G"
    assert config["file-allocation"] == "prealloc"
    assert config["max-concurrent-downloads"] == 2


def test_get_optimal_aria2_config_ssd():
    """Test SSD configuration."""
    config = get_optimal_aria2_config("ssd")

    assert config["max-connection-per-server"] == 32
    assert config["split"] == 16
    assert config["min-split-size"] == "20M"
    assert config["file-allocation"] == "falloc"
    assert config["max-concurrent-downloads"] == 5
