"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Environment variable configuration for Lambda functions.
Centralizes all environment variable access with defaults.
"""

import os

# DynamoDB Table Names
PLAYERS_TABLE = os.environ.get("PLAYERS_TABLE", "players")
CHARACTERS_TABLE = os.environ.get("CHARACTERS_TABLE", "characters")
ARCHETYPES_TABLE = os.environ.get("ARCHETYPES_TABLE", "archetypes")
ITEMS_TABLE = os.environ.get("ITEMS_TABLE", "items")
PROTOTYPES_TABLE = os.environ.get("PROTOTYPES_TABLE", "prototypes")
STORY_TABLE = os.environ.get("STORY_TABLE", "story")
SEGMENTS_TABLE = os.environ.get("SEGMENTS_TABLE", "segments")
ACTIVE_SEGMENTS_TABLE = os.environ.get("ACTIVE_SEGMENTS_TABLE", "active_segments")
HISTORY_TABLE = os.environ.get("HISTORY_TABLE", "history")
CHARACTER_HISTORY_TABLE = os.environ.get("CHARACTER_HISTORY_TABLE", "character_history")
OPPONENTS_TABLE = os.environ.get("OPPONENTS_TABLE", "opponents")
ROOMS_TABLE = os.environ.get("ROOMS_TABLE", "rooms")
EXITS_TABLE = os.environ.get("EXITS_TABLE", "exits")
MOTD_TABLE = os.environ.get("MOTD_TABLE", "motd")

# Lambda Function Names
PROCESS_SEGMENT_FUNCTION = os.environ.get("PROCESS_SEGMENT_FUNCTION", "process-segment")

# Game Configuration
DEFAULT_HEALTH = int(os.environ.get("DEFAULT_HEALTH", "10"))
DEFAULT_ESSENCE = int(os.environ.get("DEFAULT_ESSENCE", "3"))
MAX_CHARACTERS_PER_PLAYER = int(os.environ.get("MAX_CHARACTERS_PER_PLAYER", "1"))

# Logging Configuration
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# AWS Environment Detection
AWS_EXECUTION_ENV = os.environ.get("AWS_EXECUTION_ENV")

# CORS Configuration
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "")
CORS_ALLOW_CREDENTIALS = os.environ.get("CORS_ALLOW_CREDENTIALS", "true")
CORS_ALLOWED_HEADERS = os.environ.get(
    "CORS_ALLOWED_HEADERS",
    "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
)
CORS_ALLOWED_METHODS = os.environ.get("CORS_ALLOWED_METHODS", "GET,POST,PUT,DELETE,OPTIONS")
CORS_MAX_AGE = os.environ.get("CORS_MAX_AGE", "86400")  # 24 hours default

# Segment Processing Configuration
SEGMENT_BATCH_SIZE = int(os.environ.get("SEGMENT_BATCH_SIZE", "10"))
ENABLE_BATCH_PROCESSING = os.environ.get("ENABLE_BATCH_PROCESSING", "true").lower() == "true"
MAX_SEGMENTS_PER_POLL = int(os.environ.get("MAX_SEGMENTS_PER_POLL", "50"))

# SSM Parameters
SSM_POLLER_STATE_PARAMETER = os.environ.get("SSM_POLLER_STATE_PARAMETER", "/eidolon/segment-poller-state")

# SQS Configuration
SEGMENT_QUEUE_URL = os.environ.get("SEGMENT_QUEUE_URL", "")
