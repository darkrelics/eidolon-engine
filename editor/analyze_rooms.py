#!/usr/bin/env python3
"""Analyze room and exit connections for consistency."""

import json
from collections import defaultdict


def analyze_room_exits():
    """Analyze the room and exit structure for consistency issues."""
    # Load data
    with open("../data/test_rooms.json", "r", encoding="utf-8") as f:
        rooms_data = json.load(f)

    with open("../data/test_exits.json", "r", encoding="utf-8") as f:
        exits_data = json.load(f)

    # Create lookup structures
    rooms = {room["RoomID"]: room for room in rooms_data["rooms"]}
    exits = {exit["ExitID"]: exit for exit in exits_data["exits"]}

    # Map of room connections (room_id -> {direction: target_room})
    room_connections = defaultdict(dict)

    # Build connection map
    for room in rooms_data["rooms"]:
        room_id = room["RoomID"]
        for exit_id in room["ExitID"]:
            if exit_id in exits:
                exit_info = exits[exit_id]
                direction = exit_info["Direction"]
                target = exit_info["TargetRoom"]
                room_connections[room_id][direction] = target

    print("=== ROOM-EXIT ANALYSIS ===\n")

    # 1. Check for missing rooms
    print("1. CHECKING EXIT DESTINATIONS:")
    missing_rooms = set()
    for exit_info in exits_data["exits"]:
        target = exit_info["TargetRoom"]
        if target not in rooms:
            missing_rooms.add(target)
            print(f"   ERROR: Exit {exit_info['ExitID']} points to non-existent room {target}")

    if not missing_rooms:
        print("   OK: All exit destinations exist")

    # 2. Check for orphaned exits
    print("\n2. CHECKING FOR ORPHANED EXITS:")
    used_exits = set()
    for room in rooms_data["rooms"]:
        used_exits.update(room["ExitID"])

    all_exits = set(exits.keys())
    orphaned = all_exits - used_exits

    if orphaned:
        for exit_id in orphaned:
            exit_info = exits[exit_id]
            print(f"   ERROR: Exit {exit_id} ({exit_info['Direction']} to room {exit_info['TargetRoom']}) is not used by any room")
    else:
        print("   OK: All exits are used")

    # 3. Check for missing reverse connections
    print("\n3. CHECKING BIDIRECTIONAL CONNECTIONS:")
    opposite_dirs = {
        "north": "south",
        "south": "north",
        "east": "west",
        "west": "east",
        "northeast": "southwest",
        "southwest": "northeast",
        "northwest": "southeast",
        "southeast": "northwest",
        "up": "down",
        "down": "up",
        "in": "out",
        "out": "in",
    }

    missing_reverse = []

    for room_id, connections in room_connections.items():
        room_name = rooms[room_id]["Title"]
        for direction, target_id in connections.items():
            if target_id in rooms:
                target_name = rooms[target_id]["Title"]
                opposite = opposite_dirs.get(direction)

                if opposite:
                    # Check if target has reverse connection
                    target_connections = room_connections.get(target_id, {})
                    if opposite not in target_connections:
                        missing_reverse.append((room_id, room_name, direction, target_id, target_name, opposite))
                    elif target_connections[opposite] != room_id:
                        print(
                            f"   ERROR: Mismatched connection: Room {room_id} ({room_name}) -{direction}-> Room {target_id} ({target_name})"
                        )
                        print(f"          but Room {target_id} -{opposite}-> Room {target_connections[opposite]}")

    if missing_reverse:
        for room_id, room_name, direction, target_id, target_name, opposite in missing_reverse:
            print(f"   WARNING: Room {room_id} ({room_name}) has {direction} exit to Room {target_id} ({target_name})")
            print(f"            but Room {target_id} has no {opposite} exit back")
    else:
        print("   OK: All standard directional connections have matching reverse exits")

    # 4. Display room connection map
    print("\n4. ROOM CONNECTION MAP:")
    for room_id in sorted(rooms.keys()):
        room = rooms[room_id]
        print(f"\nRoom {room_id}: {room['Title']}")
        connections = room_connections.get(room_id, {})
        if connections:
            for direction, target_id in sorted(connections.items()):
                if target_id in rooms:
                    print(f"   {direction:10} -> Room {target_id} ({rooms[target_id]['Title']})")
                else:
                    print(f"   {direction:10} -> Room {target_id} (MISSING!)")
        else:
            print("   No exits")

    # 5. Check for isolated rooms
    print("\n5. CHECKING FOR ISOLATED ROOMS:")
    connected_rooms = set()

    # Mark all rooms that have exits
    for room_id in room_connections:
        if room_connections[room_id]:
            connected_rooms.add(room_id)

    # Mark all rooms that are targets of exits
    for exit_info in exits_data["exits"]:
        connected_rooms.add(exit_info["TargetRoom"])

    isolated = set(rooms.keys()) - connected_rooms
    if isolated:
        for room_id in isolated:
            print(f"   ERROR: Room {room_id} ({rooms[room_id]['Title']}) has no connections")
    else:
        print("   OK: All rooms are connected")


if __name__ == "__main__":
    analyze_room_exits()
