"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason Robinson

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.


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
