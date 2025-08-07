"""
Bloom filter utilities for character name validation.

Provides bloom filter functionality for checking restricted character names.
When the bloom filter file is not available, it gracefully degrades to allow
all names (returning False for all restriction checks).
"""

import os
import pickle

from eidolon.logger import logger


class CharacterNameFilter:
    """Manages bloom filter for restricted character names with graceful degradation."""

    def __init__(self, filter_path: str = "character_name_filter.pkl"):
        """Initialize the character name filter.

        Args:
            filter_path: Path to the bloom filter pickle file
        """
        self.bloom_filter = None
        self.filter_path = filter_path
        self.filter_available = False
        self._load_filter()

    def _load_filter(self) -> None:
        """Load the bloom filter from disk if available.

        If the file doesn't exist or can't be loaded, the filter will be
        disabled and all names will be allowed.
        """
        # Check if file exists first to avoid unnecessary errors
        if not os.path.exists(self.filter_path):
            logger.warning(f"Bloom filter file not found at {self.filter_path} - name restrictions disabled")
            self.bloom_filter = None
            self.filter_available = False
            return

        try:
            with open(self.filter_path, "rb") as f:
                self.bloom_filter = pickle.load(f)
                self.filter_available = True
                logger.info(f"Successfully loaded character name bloom filter from {self.filter_path}")
        except pickle.UnpicklingError as err:
            logger.error(f"Failed to unpickle bloom filter from {self.filter_path}: {err} - name restrictions disabled")
            self.bloom_filter = None
            self.filter_available = False
        except Exception as err:
            logger.error(f"Unexpected error loading bloom filter: {err} - name restrictions disabled")
            self.bloom_filter = None
            self.filter_available = False

    def is_restricted(self, name: str) -> bool:
        """Check if a character name is restricted.

        Args:
            name: Character name to check

        Returns:
            True if the name is restricted, False if allowed or filter unavailable
        """
        if not self.bloom_filter or not self.filter_available:
            # If bloom filter is not available, allow all names
            return False

        try:
            return name.lower() in self.bloom_filter
        except Exception as err:
            logger.error(f"Error checking name restriction for '{name}': {err}")
            # On error, be permissive and allow the name
            return False

    def is_available(self) -> bool:
        """Check if the bloom filter is loaded and available.

        Returns:
            True if bloom filter is loaded, False otherwise
        """
        return self.filter_available


# Global instance of the filter - will gracefully handle missing file
character_name_filter = CharacterNameFilter()
