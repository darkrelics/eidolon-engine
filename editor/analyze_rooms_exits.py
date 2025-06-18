"""
Analyzes room and exit data structure for consistency.

This script checks for:
- Bidirectional exit connections
- Orphaned rooms (rooms with no exits leading to them)
- One-way exits that don't make logical sense
- Exit destinations that don't exist as rooms
"""

import json


def load_json_file(filepath: str) -> dict:
    """Load JSON data from a file.

    Args:
        filepath: Path to the JSON file

    Returns:
        Parsed JSON data as a dictionary
    """
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def get_opposite_direction(direction: str) -> str:
    """Get the opposite direction for bidirectional checking.

    Args:
        direction: The direction string

    Returns:
        The opposite direction string
    """
    opposites = {
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
    return opposites.get(direction, "")


def analyze_room_exit_structure(rooms_data: dict, exits_data: dict) -> None:
    """Analyze room and exit data for consistency issues.

    Args:
        rooms_data: Dictionary containing room data
        exits_data: Dictionary containing exit data
    """
    # Build room lookup
    rooms = {}
    room_exits = {}

    for room in rooms_data["rooms"]:
        rooms[room["RoomID"]] = room
        room_exits[room["RoomID"]] = []
        for exit_id in room.get("ExitID", []):
            room_exits[room["RoomID"]].append(exit_id)

    # Build exit lookup
    exits = {}
    for exit_obj in exits_data["exits"]:
        exits[exit_obj["ExitID"]] = exit_obj

    # Track connections
    connections = {}  # source_room -> [(target_room, direction, exit_id)]
    reverse_connections = {}  # target_room -> [(source_room, direction, exit_id)]

    print("=== ROOM AND EXIT ANALYSIS ===\n")

    # 1. Check that all exit IDs referenced by rooms actually exist
    print("1. Checking exit references...")
    missing_exits = []
    for room_id, exit_ids in room_exits.items():
        for exit_id in exit_ids:
            if exit_id not in exits:
                missing_exits.append((room_id, exit_id))

    if missing_exits:
        print("   ERROR: Missing exit definitions:")
        for room_id, exit_id in missing_exits:
            print(f"   - Room {room_id} references non-existent exit {exit_id}")
    else:
        print("   ✓ All exit references are valid")

    # 2. Check that all exit destinations exist as rooms
    print("\n2. Checking exit destinations...")
    missing_destinations = []
    for exit_id, exit_obj in exits.items():
        target_room = exit_obj["TargetRoom"]
        if target_room not in rooms:
            missing_destinations.append((exit_id, target_room))

    if missing_destinations:
        print("   ERROR: Exit destinations that don't exist:")
        for exit_id, target_room in missing_destinations:
            print(f"   - Exit {exit_id} points to non-existent room {target_room}")
    else:
        print("   ✓ All exit destinations exist")

    # 3. Build connection map
    print("\n3. Building connection map...")
    for room_id, exit_ids in room_exits.items():
        for exit_id in exit_ids:
            if exit_id in exits:
                exit_obj = exits[exit_id]
                target_room = exit_obj["TargetRoom"]
                direction = exit_obj["Direction"]
                
                # Initialize connections for room_id if not present
                if room_id not in connections:
                    connections[room_id] = []
                connections[room_id].append((target_room, direction, exit_id))
                
                # Initialize reverse_connections for target_room if not present
                if target_room not in reverse_connections:
                    reverse_connections[target_room] = []
                reverse_connections[target_room].append((room_id, direction, exit_id))

    # 4. Check for one-way exits that should be bidirectional
    print("\n4. Checking for one-way exits...")
    one_way_exits = []
    for source_room, targets in connections.items():
        for target_room, direction, exit_id in targets:
            opposite_dir = get_opposite_direction(direction)

            # Skip special directions that might naturally be one-way
            if direction in ["portal", "trapdoor", "tunnel", "ladder"]:
                continue

            # Check if there's a return path
            has_return = False
            if target_room in connections:
                for ret_target, ret_dir, _ in connections[target_room]:
                    if ret_target == source_room and (ret_dir == opposite_dir or ret_dir in ["portal", "trapdoor"]):
                        has_return = True
                        break

            if not has_return and opposite_dir:
                one_way_exits.append((source_room, target_room, direction, exit_id))

    if one_way_exits:
        print("   WARNING: Potentially problematic one-way exits:")
        for source, target, direction, exit_id in one_way_exits:
            source_name = rooms[source]["Title"]
            target_name = rooms[target]["Title"] if target in rooms else f"Unknown({target})"
            print(f"   - Room {source} '{source_name}' -> Room {target} '{target_name}' ({direction})")
    else:
        print("   ✓ No problematic one-way exits found")

    # 5. Check for orphaned rooms
    print("\n5. Checking for orphaned rooms...")
    all_rooms = set(rooms.keys())
    rooms_with_exits_to = set(reverse_connections.keys())
    rooms_with_exits_from = set(connections.keys())

    # Room 1 is typically the starting room, so it's OK if nothing leads to it
    orphaned = all_rooms - rooms_with_exits_to - {1}

    if orphaned:
        print("   WARNING: Rooms with no entrances (orphaned):")
        for room_id in sorted(orphaned):
            room_name = rooms[room_id]["Title"]
            print(f"   - Room {room_id}: '{room_name}'")
    else:
        print("   ✓ All rooms are accessible")

    # 6. Check for rooms with no exits (dead ends are OK, just informational)
    print("\n6. Checking for dead-end rooms...")
    dead_ends = all_rooms - rooms_with_exits_from
    if dead_ends:
        print("   INFO: Rooms with no exits (dead ends):")
        for room_id in sorted(dead_ends):
            room_name = rooms[room_id]["Title"]
            print(f"   - Room {room_id}: '{room_name}'")
    else:
        print("   ✓ No dead-end rooms found")

    # 7. Summary of connections
    print("\n7. Connection Summary:")
    for room_id in sorted(rooms.keys()):
        room = rooms[room_id]
        print(f"\n   Room {room_id}: {room['Title']}")

        if room_id in connections:
            print("   Exits to:")
            for target, direction, exit_id in connections[room_id]:
                target_name = rooms[target]["Title"] if target in rooms else f"Unknown({target})"
                exit_desc = exits[exit_id].get("Description", "")
                desc_str = f" ({exit_desc})" if exit_desc else ""
                print(f"     - {direction}: Room {target} '{target_name}'{desc_str}")
        else:
            print("   No exits")

        if room_id in reverse_connections:
            print("   Entrances from:")
            for source, direction, exit_id in reverse_connections[room_id]:
                source_name = rooms[source]["Title"] if source in rooms else f"Unknown({source})"
                print(f"     - Room {source} '{source_name}' ({direction})")


def main():
    """Main function to run the analysis."""
    # Load all data files
    print("Loading data files...")

    # Load main files
    rooms_data = load_json_file("/Users/voideng/eidolon-engine/data/test_rooms.json")
    exits_data = load_json_file("/Users/voideng/eidolon-engine/data/test_exits.json")

    # Load update files
    rooms_update = load_json_file("/Users/voideng/eidolon-engine/data/test_rooms_update.json")
    exits_update = load_json_file("/Users/voideng/eidolon-engine/data/test_exits_update.json")

    # Merge the data (updates would typically override or add to main data)
    all_rooms = rooms_data.copy()
    all_rooms["rooms"].extend(rooms_update["rooms"])

    all_exits = exits_data.copy()
    all_exits["exits"].extend(exits_update["exits"])

    print(f"Loaded {len(all_rooms['rooms'])} rooms and {len(all_exits['exits'])} exits\n")

    # Run analysis
    analyze_room_exit_structure(all_rooms, all_exits)


if __name__ == "__main__":
    main()
