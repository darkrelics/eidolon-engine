"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

Utility to load game data from JSON files and store it in DynamoDB tables.

This script loads test data for rooms, exits, archetypes, item prototypes, and stories
from JSON files and stores them in the corresponding DynamoDB tables. It also provides
functionality to read the data back from DynamoDB and display it for verification.
"""

import argparse
import json
import logging
import os
import sys

# Add parent directory to path to import eidolon modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from botocore.exceptions import ClientError

from eidolon.dynamo import dynamo  # noqa: E402
from eidolon.dynamo import TableName
from eidolon.validation import validate_character_name  # noqa: E402


def load_json(file_path):
    """
    Loads JSON data from a file.

    Args:
        file_path (str): The path to the JSON file.

    Returns:
        dict: The data loaded from the JSON file.
    """
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def store_exits(exits_data):
    """
    Stores exit data into the 'exits' DynamoDB table using update operations.

    Args:
        exits_data (dict): The exits data to store.
    """
    try:
        for exit_data in exits_data.get("exits", []):
            exit_item = {
                "ExitID": exit_data["ExitID"],
                "Direction": exit_data["Direction"],
                "Description": exit_data.get("Description", ""),
                "TargetRoom": exit_data["TargetRoom"],
                "ArrivalText": exit_data.get("ArrivalText", ""),
                "Visible": exit_data["Visible"],
                "ScriptID": exit_data.get("ScriptID", ""),
            }

            # Build update expression dynamically
            update_expression = "SET "
            expression_attribute_values = {}
            expression_parts = []

            for key, value in exit_item.items():
                if key != "ExitID":  # Skip the key
                    expression_parts.append(f"{key} = :{key.lower()}")
                    expression_attribute_values[f":{key.lower()}"] = value

            update_expression += ", ".join(expression_parts)

            dynamo.update_item(
                TableName.EXITS,
                Key={"ExitID": exit_data["ExitID"]},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_attribute_values,
            )
        print("Exit data stored in DynamoDB successfully")
    except ClientError as err:
        logging.error(f"Failed to store exits in DynamoDB: {str(err)}")
        raise
    except Exception as err:
        logging.error(f"An unexpected error occurred while storing exits: {str(err)}")
        raise


def store_rooms(rooms_data):
    """
    Stores room data into the 'rooms' DynamoDB table using update operations.

    Args:
        rooms_data (dict): The rooms data to store.
    """
    try:
        for room in rooms_data.get("rooms", []):
            room_item = {
                "RoomID": room["RoomID"],
                "Area": room["Area"],
                "Title": room["Title"],
                "Description": room["Description"],
                "ExitID": room["ExitID"],
                "Persistent": room.get("Persistent", False),
                "ScriptID": room.get("ScriptID", ""),
            }

            # Build update expression dynamically
            update_expression = "SET "
            expression_attribute_values = {}
            expression_parts = []

            for key, value in room_item.items():
                if key != "RoomID":  # Skip the key
                    expression_parts.append(f"{key} = :{key.lower()}")
                    expression_attribute_values[f":{key.lower()}"] = value

            update_expression += ", ".join(expression_parts)

            dynamo.update_item(
                TableName.ROOMS,
                Key={"RoomID": room["RoomID"]},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_attribute_values,
            )
        print("Room data stored in DynamoDB successfully")
    except ClientError as err:
        logging.error(f"Failed to store rooms in DynamoDB: {str(err)}")
        raise
    except Exception as err:
        logging.error(f"An unexpected error occurred while storing rooms: {str(err)}")
        raise


def store_archetypes(archetypes_data):
    """
    Stores archetype data into the 'archetypes' DynamoDB table using update operations.

    Args:
        archetypes_data (dict): The archetypes data to store.
    """
    try:
        for name, archetype in archetypes_data.get("archetypes", {}).items():
            try:
                validate_character_name(name)
            except ValueError as err:
                logging.error(f"Invalid archetype name '{name}': {err}")
                continue

            # Convert attributes to lowercase
            attributes = {k.lower(): v for k, v in archetype.get("Attributes", {}).items()}
            # Convert skills to lowercase
            skills = {k.lower(): v for k, v in archetype.get("Skills", {}).items()}

            archetype_item = {
                "ArchetypeName": name,
                "Description": archetype.get("Description", ""),
                "Attributes": attributes,
                "Skills": skills,
                "StartRoom": archetype.get("StartRoom", 0),
                "StartingItems": archetype.get("StartingItems", []),
                "Player": archetype.get("Player", False),
            }

            # Add optional Health and Essence fields if present
            if "Health" in archetype:
                archetype_item["Health"] = archetype["Health"]
            if "Essence" in archetype:
                archetype_item["Essence"] = archetype["Essence"]

            # Add optional AvailableStories field if present
            if "AvailableStories" in archetype:
                archetype_item["AvailableStories"] = archetype["AvailableStories"]

            # Build update expression dynamically
            update_expression = "SET "
            expression_attribute_values = {}
            expression_parts = []

            for key, value in archetype_item.items():
                if key != "ArchetypeName":  # Skip the key
                    expression_parts.append(f"{key} = :{key.lower()}")
                    expression_attribute_values[f":{key.lower()}"] = value

            update_expression += ", ".join(expression_parts)

            dynamo.update_item(
                TableName.ARCHETYPES,
                Key={"ArchetypeName": name},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_attribute_values,
            )
        print("Archetype data stored in DynamoDB successfully")
    except ClientError as err:
        logging.error(f"Failed to store archetypes in DynamoDB: {str(err)}")
        raise
    except Exception as err:
        logging.error(f"An unexpected error occurred while storing archetypes: {str(err)}")
        raise


def store_item_prototypes(prototypes_data):
    """
    Stores item prototype data into the 'prototypes' DynamoDB table using update operations.

    Args:
        prototypes_data (dict): The item prototypes data to store.
    """
    try:
        for prototype in prototypes_data.get("itemPrototypes", []):
            prototype_id = prototype["PrototypeID"]
            prototype_data = prototype.copy()

            # Build update expression dynamically
            update_expression = "SET "
            expression_attribute_values = {}
            expression_attribute_names = {}
            expression_parts = []

            for key, value in prototype_data.items():
                if key != "PrototypeID":  # Skip the key
                    # Always use expression attribute names to avoid reserved keyword issues
                    attr_name_placeholder = f"#{key}"
                    expression_attribute_names[attr_name_placeholder] = key
                    expression_parts.append(f"{attr_name_placeholder} = :{key.lower()}")
                    expression_attribute_values[f":{key.lower()}"] = value

            update_expression += ", ".join(expression_parts)

            dynamo.update_item(
                TableName.PROTOTYPES,
                Key={"PrototypeID": prototype_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values,
            )
        print("Item prototype data stored in DynamoDB successfully")
    except ClientError as err:
        logging.error(f"Failed to store item prototypes in DynamoDB: {str(err)}")
        raise
    except Exception as err:
        logging.error(f"An unexpected error occurred while storing item prototypes: {str(err)}")
        raise


def load_exits():
    """
    Loads exit data from the 'exits' DynamoDB table.

    Returns:
        dict: A dictionary of exit data.
    """
    try:
        result: dict = dynamo.scan(TableName.EXITS)  # type: ignore
        items = result.get("items", [])
        exits = {item["ExitID"]: item for item in items}
        print("Exit data loaded from DynamoDB successfully")
        return exits
    except ClientError as err:
        logging.error(f"Failed to load exits from DynamoDB: {str(err)}")
        return {}
    except Exception as err:
        logging.error(f"An unexpected error occurred while loading exits: {str(err)}")
        return {}


def load_rooms():
    """
    Loads room data from the 'rooms' DynamoDB table.

    Returns:
        dict: A dictionary of room data.
    """
    try:
        result: dict = dynamo.scan(TableName.ROOMS)  # type: ignore
        items = result.get("items", [])
        rooms = {item["RoomID"]: item for item in items}  # type: ignore
        print("Room data loaded from DynamoDB successfully")
        return rooms
    except ClientError as err:
        logging.error(f"Failed to load rooms from DynamoDB: {str(err)}")
        return {}
    except Exception as err:
        logging.error(f"An unexpected error occurred while loading rooms: {str(err)}")
        return {}


def load_archetypes():
    """
    Loads archetype data from the 'archetypes' DynamoDB table.

    Returns:
        dict: A dictionary containing the archetypes.
    """
    try:
        result: dict = dynamo.scan(TableName.ARCHETYPES)  # type: ignore
        items = result.get("items", [])
        archetypes = {"archetypes": {item["ArchetypeName"]: item for item in items}}  # type: ignore
        print("Archetype data loaded from DynamoDB successfully")
        return archetypes
    except ClientError as err:
        logging.error(f"Failed to load archetypes from DynamoDB: {str(err)}")
        return {}
    except Exception as err:
        logging.error(f"An unexpected error occurred while loading archetypes: {str(err)}")
        return {}


def load_item_prototypes():
    """
    Loads item prototype data from the 'prototypes' DynamoDB table.

    Returns:
        dict: A dictionary containing the item prototypes.
    """
    try:
        result: dict = dynamo.scan(TableName.PROTOTYPES)  # type: ignore
        items = result.get("items", [])
        prototypes = {"itemPrototypes": items}
        print("Item prototype data loaded from DynamoDB successfully")
        return prototypes
    except ClientError as err:
        logging.error(f"Failed to load item prototypes from DynamoDB: {str(err)}")
        return {}
    except Exception as err:
        logging.error(f"An unexpected error occurred while loading item prototypes: {str(err)}")
        return {}


def store_opponents(opponents_data):
    """
    Stores opponent data into the 'opponents' DynamoDB table using update operations.
    
    Supports both MUD-style opponents (with CombatRating, DefenseRating, etc.) and
    Incremental-style opponents (with Attributes and Skills).

    Args:
        opponents_data (dict): The opponents data to store.
    """
    try:
        for opponent in opponents_data.get("opponents", []):
            # Check if this is incremental game format (has Attributes/Skills)
            if "Attributes" in opponent and "Skills" in opponent:
                # Incremental game format
                opponent_item = {
                    "OpponentID": opponent["OpponentID"],
                    "Name": opponent["Name"],
                    "Description": opponent.get("Description", ""),
                    "Health": opponent["Health"],
                    "MaxHealth": opponent.get("MaxHealth", opponent["Health"]),
                    "Attributes": opponent["Attributes"],
                    "Skills": opponent["Skills"],
                    "Level": opponent.get("Level", 1),
                    "XPReward": opponent.get("XPReward", 10),
                    "LootTable": opponent.get("LootTable", []),
                    "Tags": opponent.get("Tags", []),
                    "CreatedAt": opponent.get("CreatedAt", ""),
                }
            else:
                # MUD format (legacy)
                opponent_item = {
                    "OpponentID": opponent["OpponentID"],
                    "Name": opponent["Name"],
                    "Description": opponent.get("Description", ""),
                    "CombatRating": opponent["CombatRating"],
                    "DefenseRating": opponent["DefenseRating"],
                    "DamageRating": opponent["DamageRating"],
                    "Toughness": opponent["Toughness"],
                    "ArmorRating": opponent.get("ArmorRating", 0),
                    "Health": opponent["Health"],
                    "WeaponType": opponent.get("WeaponType", "bashing"),
                    "WeaponDamage": opponent["WeaponDamage"],
                    "LootTable": opponent.get("LootTable", []),
                    "Tags": opponent.get("Tags", []),
                    "CreatedAt": opponent.get("CreatedAt", ""),
                }

            # Build update expression dynamically
            update_expression = "SET "
            expression_attribute_values = {}
            expression_attribute_names = {}
            expression_parts = []

            for key, value in opponent_item.items():
                if key != "OpponentID":  # Skip the key
                    # Use expression attribute names to avoid reserved keyword issues
                    attr_name_placeholder = f"#{key}"
                    expression_attribute_names[attr_name_placeholder] = key
                    expression_parts.append(f"{attr_name_placeholder} = :{key.lower()}")
                    expression_attribute_values[f":{key.lower()}"] = value

            update_expression += ", ".join(expression_parts)

            dynamo.update_item(
                TableName.OPPONENTS,
                Key={"OpponentID": opponent["OpponentID"]},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values,
            )
        print("Opponent data stored in DynamoDB successfully")
    except ClientError as err:
        logging.error(f"Failed to store opponents in DynamoDB: {str(err)}")
        raise
    except Exception as err:
        logging.error(f"An unexpected error occurred while storing opponents: {str(err)}")
        raise


def store_story(story_data):
    """
    Stores story and segments data into DynamoDB tables.

    Args:
        story_data (dict): The story data containing story definition and segments.
    """
    try:
        # Store the main story
        story = story_data.get("story", {})
        if story:
            story_item = {
                "StoryID": story["StoryID"],
                "Title": story["Title"],
                "Description": story["Description"],
                "NarrativeText": story["NarrativeText"],
                "StoryType": story["StoryType"],
                "EstimatedDuration": story["EstimatedDuration"],
                "Prerequisites": story.get("Prerequisites", {}),
                "DifficultyMap": story.get("DifficultyMap", {}),
                "RewardTiers": story.get("RewardTiers", {}),
                "BaseXPMultiplier": story.get("BaseXPMultiplier", 0.5),
                "FirstSegmentID": story["FirstSegmentID"],
                "CreatedAt": story["CreatedAt"],
                "Version": story.get("Version", 1),
            }

            # Build update expression
            update_expression = "SET "
            expression_attribute_values = {}
            expression_parts = []

            for key, value in story_item.items():
                if key != "StoryID":  # Skip the key
                    expression_parts.append(f"{key} = :{key.lower()}")
                    expression_attribute_values[f":{key.lower()}"] = value

            update_expression += ", ".join(expression_parts)

            dynamo.update_item(
                TableName.STORY,
                Key={"StoryID": story["StoryID"]},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_attribute_values,
            )
            print(f"Story '{story['Title']}' stored successfully")

        # Store all segments
        segments = story_data.get("segments", [])
        for segment in segments:
            segment_item = {
                "StoryID": segment["StoryID"],
                "SegmentID": segment["SegmentID"],
                "SegmentType": segment["SegmentType"],
                "ShortStatus": segment["ShortStatus"],
                "DefaultStatus": segment.get("DefaultStatus", ""),
                "SegmentDuration": segment["SegmentDuration"],
            }

            # Add optional fields based on segment type
            if segment["SegmentType"] == "decision":
                segment_item["DecisionText"] = segment.get("DecisionText", "")
                segment_item["DecisionOptions"] = segment.get("DecisionOptions", {})
                segment_item["DefaultDecision"] = segment.get("DefaultDecision", "")
            elif segment["SegmentType"] == "mechanical":
                segment_item["NextSegmentID"] = segment.get("NextSegmentID")
                segment_item["Challenges"] = segment.get("Challenges", [])
                segment_item["Combat"] = segment.get("Combat", {})
            elif segment["SegmentType"] == "rest":
                segment_item["NextSegmentID"] = segment.get("NextSegmentID")
                segment_item["RestBenefit"] = segment.get("RestBenefit", {})
            else:
                print(f"Unknown segment type: {segment['SegmentType']}")

            # Build update expression
            update_expression = "SET "
            expression_attribute_values = {}
            expression_parts = []

            for key, value in segment_item.items():
                if key not in ["StoryID", "SegmentID"]:  # Skip the keys
                    expression_parts.append(f"{key} = :{key.lower()}")
                    expression_attribute_values[f":{key.lower()}"] = value

            update_expression += ", ".join(expression_parts)

            dynamo.update_item(
                TableName.SEGMENTS,
                Key={"StoryID": segment["StoryID"], "SegmentID": segment["SegmentID"]},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_attribute_values,
            )

        print(f"Stored {len(segments)} segments successfully")

    except ClientError as err:
        logging.error(f"Failed to store story in DynamoDB: {str(err)}")
        raise
    except Exception as err:
        logging.error(f"An unexpected error occurred while storing story: {str(err)}")
        raise


def load_opponents():
    """
    Loads opponent data from the 'opponents' DynamoDB table.

    Returns:
        dict: A dictionary containing the opponents.
    """
    try:
        result: dict = dynamo.scan(TableName.OPPONENTS)  # type: ignore
        items = result.get("items", [])
        opponents = {"opponents": items}
        print("Opponent data loaded from DynamoDB successfully")
        return opponents
    except ClientError as err:
        logging.error(f"Failed to load opponents from DynamoDB: {str(err)}")
        return {}
    except Exception as err:
        logging.error(f"An unexpected error occurred while loading opponents: {str(err)}")
        return {}


def load_story():
    """
    Loads story data from the 'story' and 'segments' DynamoDB tables.

    Returns:
        dict: A dictionary containing the story and segments data.
    """
    try:
        # Load all stories
        stories_result: dict = dynamo.scan(TableName.STORY)  # type: ignore
        stories = stories_result.get("items", [])

        # Load all segments
        segments_result: dict = dynamo.scan(TableName.SEGMENTS)  # type: ignore
        segments = segments_result.get("items", [])

        print("Story data loaded from DynamoDB successfully")
        return {"stories": stories, "segments": segments}
    except ClientError as err:
        logging.error(f"Failed to load story data from DynamoDB: {str(err)}")
        return {}
    except Exception as err:
        logging.error(f"An unexpected error occurred while loading story: {str(err)}")
        return {}


def display_exits(exits):
    """
    Displays exit information.

    Args:
        exits (dict): The exits data to display.
    """
    print("Exits:")
    for exit_id, exit_data in exits.items():
        print(f"Exit ID: {exit_id}")
        print(f"  Direction: {exit_data['Direction']}")
        if exit_data.get("Description"):
            print(f"  Description: {exit_data['Description']}")
        print(f"  Target Room: {exit_data['TargetRoom']}")
        if exit_data.get("ArrivalText"):
            print(f"  Arrival Text: {exit_data['ArrivalText']}")
        print(f"  Visible: {exit_data['Visible']}")
        if exit_data.get("ScriptID"):
            print(f"  Script ID: {exit_data['ScriptID']}")
        print()


def display_rooms(rooms):
    """
    Displays room information.

    Args:
        rooms (dict): The rooms data to display.
    """
    print("Rooms:")
    for room_id, room in rooms.items():
        print(f"Room {room_id}: {room.get('Title', 'No Title')}")
        print(f"  Area: {room.get('Area', 'Unknown')}")
        print(f"  Description: {room.get('Description', 'No description')}")
        print(f"  Exits: {', '.join(room.get('ExitID', []))}")
        print(f"  Persistent: {room.get('Persistent', False)}")
        print(f"  ScriptID: {room.get('ScriptID', '')}")
        print()


def display_archetypes(archetypes):
    """
    Displays archetype information.

    Args:
        archetypes (dict): The archetypes data to display.
    """
    print("Archetypes:")
    for name, archetype in archetypes.get("archetypes", {}).items():
        print(f"Name: {name}")
        print(f"  Description: {archetype.get('Description', 'No description')}")
        print("  Attributes:")
        for attr, value in archetype.get("Attributes", {}).items():
            print(f"    {attr}: {value}")
        print("  Skills:")
        for skill, value in archetype.get("Skills", {}).items():
            print(f"    {skill}: {value}")

        # Add starting items information
        starting_items = archetype.get("StartingItems", [])
        if starting_items:
            print("  Starting Items:")
            for item in starting_items:
                print(f"    Prototype: {item.get('PrototypeID', 'Unknown')}")
                print(f"      Slot: {item.get('Slot', 'Unspecified')}")
                print(f"      Worn: {item.get('IsWorn', False)}")

        # Add available stories information
        available_stories = archetype.get("AvailableStories", [])
        if available_stories:
            print("  Available Stories:")
            for story_id in available_stories:
                print(f"    {story_id}")
        print()


def display_item_prototypes(prototypes):
    """
    Displays item prototype information.

    Args:
        prototypes (dict): The item prototypes data to display.
    """
    print("Item Prototypes:")
    for prototype in prototypes.get("itemPrototypes", []):
        print(f"ID: {prototype.get('PrototypeID', 'No ID')}")
        print(f"  Name: {prototype.get('prototype_name', prototype.get('Name', 'No Name'))}")
        print(f"  Description: {prototype.get('Description', 'No description')}")
        print(f"  Mass: {prototype.get('Mass', 'Unknown')}")
        print(f"  Value: {prototype.get('Value', 'Unknown')}")
        print(f"  Wearable: {prototype.get('Wearable', False)}")
        if prototype.get("Wearable"):
            print(f"  Worn on: {', '.join(prototype.get('WornOn', []))}")
        print()


def display_opponents(opponents_data):
    """
    Displays opponent information.

    Args:
        opponents_data (dict): The opponents data to display.
    """
    print("Opponents:")
    for opponent in opponents_data.get("opponents", []):
        print(f"Opponent ID: {opponent.get('OpponentID', 'No ID')}")
        print(f"  Name: {opponent.get('Name', 'No Name')}")
        print(f"  Description: {opponent.get('Description', 'No description')}")
        
        # Check if this is incremental format (has Attributes/Skills)
        if "Attributes" in opponent and "Skills" in opponent:
            # Incremental format
            print(f"  Health: {opponent.get('Health', 0)} / {opponent.get('MaxHealth', opponent.get('Health', 0))}")
            print(f"  Level: {opponent.get('Level', 1)}")
            print(f"  XP Reward: {opponent.get('XPReward', 0)}")
            
            print("  Attributes:")
            for attr, value in opponent.get("Attributes", {}).items():
                print(f"    {attr}: {value}")
                
            print("  Skills:")
            for skill, value in opponent.get("Skills", {}).items():
                print(f"    {skill}: {value}")
        else:
            # MUD format (legacy)
            print(f"  Combat Rating: {opponent.get('CombatRating', 0)}")
            print(f"  Defense Rating: {opponent.get('DefenseRating', 0)}")
            print(f"  Damage Rating: {opponent.get('DamageRating', 0)}")
            print(f"  Toughness: {opponent.get('Toughness', 0)}")
            print(f"  Armor Rating: {opponent.get('ArmorRating', 0)}")
            print(f"  Health: {opponent.get('Health', 0)}")
            print(f"  Weapon Type: {opponent.get('WeaponType', 'Unknown')}")
            print(f"  Weapon Damage: {opponent.get('WeaponDamage', 0)}")

        loot_table = opponent.get("LootTable", [])
        if loot_table:
            print("  Loot Table:")
            for loot in loot_table:
                if isinstance(loot, dict):
                    print(f"    Item: {loot.get('itemID', 'Unknown')} (chance: {loot.get('chance', 0)}")")
                else:
                    # Simple string format
                    print(f"    {loot}")

        tags = opponent.get("Tags", [])
        if tags:
            print(f"  Tags: {', '.join(tags)}")
        print()


def display_story(story_data):
    """
    Displays story and segments information.

    Args:
        story_data (dict): The story data to display.
    """
    # Display stories
    print("Stories:")
    for story in story_data.get("stories", []):
        print(f"Story ID: {story.get('StoryID', 'No ID')}")
        print(f"  Title: {story.get('Title', 'No Title')}")
        print(f"  Description: {story.get('Description', 'No description')}")
        print(f"  Type: {story.get('StoryType', 'Unknown')}")
        print(f"  Duration: {story.get('EstimatedDuration', 0)} seconds")
        print(f"  First Segment: {story.get('FirstSegmentID', 'None')}")
        print(f"  Version: {story.get('Version', 1)}")
        print()

    # Display segments grouped by story
    print("Segments:")
    segments_by_story = {}
    for segment in story_data.get("segments", []):
        story_id = segment.get("StoryID")
        if story_id not in segments_by_story:
            segments_by_story[story_id] = []
        segments_by_story[story_id].append(segment)

    for story_id, segments in segments_by_story.items():
        print(f"\nSegments for Story {story_id}:")
        for segment in segments:
            print(f"  Segment ID: {segment.get('SegmentID')}")
            print(f"    Type: {segment.get('SegmentType')}")
            print(f"    Status: {segment.get('ShortStatus')}")
            print(f"    Duration: {segment.get('SegmentDuration')} seconds")

            if segment.get("SegmentType") == "decision":
                print(f"    Decision Text: {segment.get('DecisionText', 'None')}")
                options = segment.get("DecisionOptions", {})
                if options:
                    print("    Options:")
                    for opt_key, opt_value in options.items():
                        print(f"      {opt_key}: -> {opt_value}")
            elif segment.get("SegmentType") == "mechanical":
                print(f"    Next Segment: {segment.get('NextSegmentID', 'None')}")
                challenges = segment.get("Challenges", [])
                if challenges:
                    print(f"    Challenges: {len(challenges)}")
                combat = segment.get("Combat", {})
                if combat:
                    print(f"    Combat: Opponent ID: {combat.get('OpponentID', 'None')}, Max Rounds: {combat.get('maxRounds', 0)}")
            elif segment.get("SegmentType") == "rest":
                print(f"    Next Segment: {segment.get('NextSegmentID', 'None')}")
                rest_benefit = segment.get("RestBenefit", {})
                if rest_benefit:
                    print(f"    Rest Benefit: {rest_benefit}")
            else:
                print(f"    Unknown segment type: {segment.get('SegmentType')}")
                print(f"    Next Segment: {segment.get('NextSegmentID', 'None')}")
            print()


def main():
    """
    Main function to load game data from JSON files and store it in DynamoDB.

    - Parses command-line arguments for file paths and AWS region.
    - Loads data from JSON files.
    - Stores data into DynamoDB tables.
    - Loads data back from DynamoDB and displays it.
    """
    parser = argparse.ArgumentParser(description="Load and store game data in DynamoDB.")
    parser.add_argument(
        "-r",
        "--rooms",
        default="../data/test_rooms.json",
        help="Path to the Rooms JSON file.",
    )
    parser.add_argument(
        "-e",
        "--exits",
        default="../data/test_exits.json",
        help="Path to the Exits JSON file.",
    )
    parser.add_argument(
        "-a",
        "--archetypes",
        default="../data/test_archetypes.json",
        help="Path to the Archetypes JSON file.",
    )
    parser.add_argument(
        "-p",
        "--prototypes",
        default="../data/test_prototypes.json",
        help="Path to the Prototypes JSON file.",
    )
    parser.add_argument(
        "-s",
        "--story",
        default="../data/test_story.json",
        help="Path to the Story JSON file.",
    )
    parser.add_argument(
        "-o",
        "--opponents",
        default="../data/test_opponents.json",
        help="Path to the Opponents JSON file.",
    )
    parser.add_argument("-region", default="us-east-1", help="AWS region for DynamoDB.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    try:
        # Load and store exits
        exits_data = load_json(args.exits)
        store_exits(exits_data)

        # Load and store rooms
        rooms_data = load_json(args.rooms)
        store_rooms(rooms_data)

        # Load and store archetypes
        archetypes_data = load_json(args.archetypes)
        store_archetypes(archetypes_data)

        # Load and store item prototypes
        prototypes_data = load_json(args.prototypes)
        store_item_prototypes(prototypes_data)

        # Load and store story
        story_data = load_json(args.story)
        store_story(story_data)

        # Load and store opponents
        opponents_data = load_json(args.opponents)
        store_opponents(opponents_data)

        # Load data from DynamoDB and display
        loaded_exits = load_exits()
        display_exits(loaded_exits)

        loaded_rooms = load_rooms()
        display_rooms(loaded_rooms)

        loaded_archetypes = load_archetypes()
        display_archetypes(loaded_archetypes)

        loaded_prototypes = load_item_prototypes()
        display_item_prototypes(loaded_prototypes)

        loaded_story = load_story()
        display_story(loaded_story)

        loaded_opponents = load_opponents()
        display_opponents(loaded_opponents)

    except Exception as err:
        logging.error(f"An unexpected error occurred: {str(err)}")


if __name__ == "__main__":
    main()
