"""Storage type detection (HDD vs SSD)."""

import os
import re
import subprocess
from pathlib import Path
from typing import Literal

import psutil

from .logger import logger


def detect_storage_type(path: str = "/downloads") -> Literal["hdd", "ssd"]:
    """
    Detect if the storage path is on HDD or SSD.

    Args:
        path: Path to check

    Returns:
        "hdd" or "ssd"
    """
    try:
        # Resolve the absolute path
        abs_path = Path(path).resolve()

        # Find the mount point
        mount_point = _find_mount_point(abs_path)
        if not mount_point:
            logger.warning(f"Could not find mount point for {path}, assuming HDD")
            return "hdd"

        # Get the device name
        device = _get_device_for_mount(mount_point)
        if not device:
            logger.warning(f"Could not find device for {mount_point}, assuming HDD")
            return "hdd"

        # Check if it's a rotational device (HDD)
        is_rotational = _is_rotational_device(device)

        storage_type = "hdd" if is_rotational else "ssd"
        logger.info(f"Detected storage type for {path}: {storage_type} (device: {device})")

        return storage_type

    except Exception as e:
        logger.error(f"Error detecting storage type: {e}", extra={"exception": str(e)})
        # Default to HDD for safety (more conservative settings)
        return "hdd"


def _find_mount_point(path: Path) -> str:
    """Find the mount point for a given path."""
    partitions = psutil.disk_partitions()

    # Sort by mount point length (longest first) to get the most specific mount
    partitions_sorted = sorted(partitions, key=lambda p: len(p.mountpoint), reverse=True)

    for partition in partitions_sorted:
        try:
            if str(path).startswith(partition.mountpoint):
                return partition.mountpoint
        except (OSError, PermissionError):
            continue

    return ""


def _get_device_for_mount(mount_point: str) -> str:
    """Get the device name for a mount point."""
    partitions = psutil.disk_partitions()

    for partition in partitions:
        if partition.mountpoint == mount_point:
            # Extract base device name (e.g., /dev/sda1 -> sda)
            device = partition.device
            # Remove /dev/ prefix
            device = device.replace("/dev/", "")
            # Remove partition number (sda1 -> sda, nvme0n1p1 -> nvme0n1)
            device = re.sub(r'\d+$', '', device)  # Remove trailing digits
            device = re.sub(r'p\d+$', '', device)  # Remove p<digit> for nvme
            return device

    return ""


def _is_rotational_device(device: str) -> bool:
    """
    Check if a device is rotational (HDD) or not (SSD).

    Args:
        device: Device name (e.g., "sda", "nvme0n1")

    Returns:
        True if HDD (rotational), False if SSD (non-rotational)
    """
    # Check /sys/block/<device>/queue/rotational
    rotational_file = f"/sys/block/{device}/queue/rotational"

    try:
        if os.path.exists(rotational_file):
            with open(rotational_file, "r") as f:
                value = f.read().strip()
                # 1 = rotational (HDD), 0 = non-rotational (SSD)
                return value == "1"
    except (OSError, PermissionError) as e:
        logger.warning(f"Could not read {rotational_file}: {e}")

    # Fallback: try lsblk command
    try:
        result = subprocess.run(
            ["lsblk", "-d", "-o", "NAME,ROTA", "-n"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == device:
                    # 1 = rotational, 0 = non-rotational
                    return parts[1] == "1"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Default to HDD (conservative approach)
    logger.warning(f"Could not determine rotation status for {device}, assuming HDD")
    return True


def get_optimal_aria2_config(storage_type: Literal["hdd", "ssd"]) -> dict:
    """
    Get optimal aria2 configuration based on storage type.

    Args:
        storage_type: "hdd" or "ssd"

    Returns:
        Dictionary of aria2 configuration options
    """
    if storage_type == "hdd":
        return {
            "max-connection-per-server": 16,
            "split": 1,
            "min-split-size": "1G",
            "file-allocation": "prealloc",
            "disk-cache": "128M",
            "max-concurrent-downloads": 2,
            "enable-mmap": True,
            "max-overall-download-limit": "0",
            "continue": True,
            "auto-file-renaming": False,
            "allow-overwrite": False,
        }
    else:  # SSD
        return {
            "max-connection-per-server": 32,
            "split": 16,
            "min-split-size": "20M",
            "file-allocation": "falloc",
            "disk-cache": "64M",
            "max-concurrent-downloads": 5,
            "enable-mmap": False,
            "max-overall-download-limit": "0",
            "continue": True,
            "auto-file-renaming": False,
            "allow-overwrite": False,
        }
