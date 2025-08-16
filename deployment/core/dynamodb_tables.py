"""Constants for DynamoDB table configurations."""

# Table configurations based on schema.md
TABLE_CONFIGS = [
    {
        "name": "players",
        "partition_key": {"name": "PlayerID", "type": "S"},
    },
    {
        "name": "characters",
        "partition_key": {"name": "CharacterID", "type": "S"},
        "gsi": [{"name": "CharacterNameIndex", "partition_key": {"name": "CharacterName", "type": "S"}, "projection": "KEYS_ONLY"}],
    },
    {
        "name": "rooms",
        "partition_key": {"name": "RoomID", "type": "N"},
    },
    {
        "name": "exits",
        "partition_key": {"name": "ExitID", "type": "S"},
    },
    {
        "name": "items",
        "partition_key": {"name": "ItemID", "type": "S"},
    },
    {
        "name": "prototypes",
        "partition_key": {"name": "PrototypeID", "type": "S"},
    },
    {
        "name": "archetypes",
        "partition_key": {"name": "ArchetypeName", "type": "S"},
    },
    {
        "name": "motd",
        "partition_key": {"name": "MotdID", "type": "S"},
    },
    {
        "name": "story",
        "partition_key": {"name": "StoryID", "type": "S"},
    },
    {
        "name": "segments",
        "partition_key": {"name": "StoryID", "type": "S"},
        "sort_key": {"name": "SegmentID", "type": "S"},
    },
    {
        "name": "active_segments",
        "partition_key": {"name": "ActiveSegmentID", "type": "S"},
        "gsi": [
            {"name": "CharacterID-index", "partition_key": {"name": "CharacterID", "type": "S"}, "projection": "ALL"},
            {
                "name": "EndTimeIndex",
                "partition_key": {"name": "Status", "type": "S"},
                "sort_key": {"name": "EndTime", "type": "N"},
                "projection": "ALL",
            },
        ],
    },
    {
        "name": "story_history",
        "partition_key": {"name": "CharacterID", "type": "S"},
        "sort_key": {"name": "StoryID", "type": "S"},
    },
    {
        "name": "segment_history",
        "partition_key": {"name": "CharacterID", "type": "S"},
        "sort_key": {"name": "ActiveSegmentID", "type": "S"},
    },
    {
        "name": "opponents",
        "partition_key": {"name": "OpponentID", "type": "S"},
    },
]
