"""
Bloom filter utilities for character name validation.

Provides bloom filter functionality for checking restricted character names.
Fail-safe behavior: If the bloom filter file is missing or cannot be loaded,
or if an error occurs during checking, the module rejects names rather than
allowing them. This prevents bypassing name restrictions if the filter is
unavailable.

"""

import pickle
from functools import cache
from pathlib import Path

from eidolon.logger import logger


def load_bloom_filter(filter_path: str):
    """Load and return the bloom filter object from disk.

    Returns the loaded bloom filter object on success, or None if not
    available or failed to load. Errors are logged and treated as
    non-fatal; the caller will apply fail-safe restrictive behavior
    (reject names) when the filter is unavailable.
    """
    if not Path(filter_path).exists():
        logger.warning(f"Bloom filter file not found at {filter_path} - name restrictions disabled")
        return None

    try:
        with Path(filter_path).open("rb") as f:
            bloom = pickle.load(f)
            logger.info(f"Successfully loaded character name bloom filter from {filter_path}")
            return bloom
    except pickle.UnpicklingError as err:
        logger.error(f"Failed to unpickle bloom filter from {filter_path}: {err} - name restrictions disabled")
        return None
    except Exception as err:
        logger.error(f"Unexpected error loading bloom filter: {err} - name restrictions disabled")
        return None


class CharacterNameFilter:
    """Manages bloom filter for restricted character names with graceful degradation."""

    def __init__(self, filter_path: str = "character_name_filter.pkl"):
        """Initialize the character name filter and load the filter payload."""
        self.filter_path = filter_path
        self.bloom_filter = load_bloom_filter(filter_path)

    @cache
    def approve(self, name: str) -> bool:
        """Return True if the given name is approved (not restricted).

        The check is cached per normalized name. When the bloom filter is
        unavailable or an error occurs during checking, names are rejected
        (fail-safe).
        """
        normalized = (name or "").lower()

        if not self.bloom_filter:
            return False  # No filter means all names are rejected

        try:
            return normalized not in self.bloom_filter
        except Exception as err:
            logger.error(f"Error checking name restriction for '{normalized}': {err}")
            return False  # On error, reject the name


# Global instance of the filter - will gracefully handle missing file
character_name_filter = CharacterNameFilter()
