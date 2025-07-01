[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

![GitHub](https://img.shields.io/badge/github-%23121011.svg?style=for-the-badge&logo=github&logoColor=white)
![Dependabot](https://img.shields.io/badge/dependabot-025E8C?style=for-the-badge&logo=dependabot&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/github%20actions-%232671E5.svg?style=for-the-badge&logo=githubactions&logoColor=white)

![AWS](https://img.shields.io/badge/AWS-%23FF9900.svg?style=for-the-badge&logo=amazon-aws&logoColor=white)
![AmazonDynamoDB](https://img.shields.io/badge/Amazon%20DynamoDB-4053D6?style=for-the-badge&logo=Amazon%20DynamoDB&logoColor=white)

![Go](https://img.shields.io/badge/go-%2300ADD8.svg?style=for-the-badge&logo=go&logoColor=white)
![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![Flutter](https://img.shields.io/badge/Flutter-%2302569B.svg?style=for-the-badge&logo=Flutter&logoColor=white)

![Linux](https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black)
![Windows](https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)

# Eidolon Engine

The goal of this project is to create a commercial-quality multi-user dungeon (MUD) engine that is flexible enough to be used as either a conventional MUD or an interactive fiction game.

## Project Overview

The engine is primarily written in Go (version 1.24) with an SSH server for secure authentication and communication between the player and the server. Additionally, there are database utility scripts written in Python (version 3.12) and various deployment scripts.

Key components:

- Go server (v1.24) for game logic and player interactions
- Python (v3.12) scripts for database management and deployment
- Flutter (v3.29) for the portal interface
- AWS services for database (DynamoDB), Identity Provider (Cognito), and S3 for scripts
- CloudFormation templates for AWS resource management

## Server Architecture

The Eidolon Engine system is built around three primary goroutine types - server, game, and room - which form the backbone of the architecture. The server component manages external interfaces, beginning with SSH and designed to later accommodate HTTPS and gRPC. It handles authentication through AWS Cognito, controls all external I/O operations, and tracks active interfaces. When players connect, the server creates individual player sessions through the appropriate interface, with communication managed through dedicated channels for input, output, and errors.

Each interface implements protocol-specific rate limiting and reports metrics to CloudWatch. The interfaces track their active players, with the system designed to support approximately 1000 concurrent players. Rather than using WaitGroups, the system relies on context and channels for coordinating operations and shutdowns between components.

Player sessions serve as the bridge between the interface and game world, handling essential functions like displaying messages of the day, character management, and console formatting for passwords and other sensitive input. Each session implements anti-abuse rate limiting and maintains clear communication boundaries through channels at both the interface and character layers. When a player creates or selects a character, the player session spawns a character session while maintaining tracking of its associated characters.

### Hand System

Characters have two hands (left and right) for holding items:

- **Right Hand**: Primary/dominant hand - items are picked up here first
- **Left Hand**: Secondary hand - used when right hand is full
- **Full Hands**: Cannot pick up items when both hands are occupied
- **Switch Command**: Swap items between hands when both are holding something
- **Drop/Put**: Can drop or put items directly from hands
- **Inventory Display**: Shows hand contents separately from worn/carried items
- **INFO Command**: Displays what you're holding in a natural format

### Stealth System

A comprehensive stealth mechanic allowing characters to hide and move unseen:

- **Hide/Unhide**: Characters can attempt to hide, becoming invisible to others
- **Sneak**: Move while hidden, with skill checks to remain undetected
- **Search**: Active searching to reveal hidden characters
- **Point**: Reveal a hidden character to everyone in the room
- **Detection**: Automatic perception checks when hidden characters act
- **Skill-Based**: Success depends on stealth skill vs perception

### Combat System (Basic Implementation)

Range-based combat mechanics with positioning:

- **Face**: Target another character for combat
- **Assess**: Evaluate combat situation and distances
- **Advance/Retreat**: Move closer or farther from opponents
- **Flee**: Attempt to escape combat by leaving the room
- **Range Categories**: Melee, close, near, far, distant
- **Engagement**: Combat state tracking who is fighting whom

### Death and Ghost System

Character death and revival mechanics:

- **Death State**: Characters can die from combat or other causes
- **Ghost Form**: Dead characters become ghosts with limited actions
- **Depart Command**: Ghosts can depart to designated revival points
- **State Restrictions**: Different commands available based on alive/dead state

### Experience and Skill System

XP-based progression through skill usage:

- **Skill Checks**: Opposed and static checks using skills + attributes
- **XP Rewards**: Gain experience from successful (and failed) actions
- **Variance Modifier**: More XP for challenging opponents, less for easy ones
- **Skill Progression**: Exponential XP requirements (10 × 3.5^level)
- **Attribute Growth**: Attributes gain 10% of related skill XP
- **Cryptographic RNG**: Secure random number generation for fair outcomes

### Mechanics Resolution System

Advanced dice-less resolution for all game actions:

- **Opposed Checks**: Character vs character with skill + attribute scores
- **Static Checks**: Character vs difficulty rating
- **Normal Distribution**: Results based on bell curve probability
- **Advantage System**: Higher scores shift probability of success
- **No Dice**: Pure statistical resolution without random dice
- **Secure Randomness**: Uses crypto/rand for unpredictable results

### Room System

Each active room runs in its own goroutine, handling commands and state for all characters and items within it. Rooms can be marked as persistent or non-persistent:

- **Persistent Rooms**: Remain loaded in memory even when empty
- **Non-Persistent Rooms**: Unload from memory after being empty for 10 minutes

Items in rooms follow similar persistence rules:

- Items held by characters are persistent
- Items in empty rooms will be purged if the room remains empty for 10 minutes

Room scripts are managed through a central Script system:

- Scripts are stored in S3 and cached in memory at startup
- Multiple rooms can share the same script
- Scripts control room-specific behaviors and interactions
- The same scripting system is used for both rooms and items

### Command Processing Architecture

The command system is structured in a three-tier hierarchy to efficiently handle different types of player interactions. Each tier is now implemented in a dedicated file to maintain clear separation of concerns:

1. **Character Tier (Fast, Local)** - In `character-commands.go`:
   - Status checks, inventory viewing, equipment status, and character stats
   - No wait time, providing immediate feedback to players
   - Entirely local to the character with no external dependencies
   - Implemented using direct function calls for lowest latency
   - Commands like: help, info, skill, who, look (when not targeting a specific object)
   - Self-contained with no external dependencies beyond the character object itself

2. **Room Tier (Medium, Localized)** - In `room-commands.go`:
   - Social interactions (say, emote, whisper), local interactions, and item manipulation
   - Moderate wait times based on command complexity
   - Processed asynchronously in room goroutines
   - Commands and responses flow through structured channels between characters and rooms
   - Room maintains state for all characters and items present
   - Robust nil reference checking to prevent crashes

3. **Game Tier (Slow, Global)** - In `game-commands.go`:
   - Cross-room effects, global events, weather changes, and server-wide announcements
   - Server-wide communication (shout, announce, who/list)
   - Longer wait times for complex actions
   - Commands are escalated from room goroutines to the central game routine
   - Uses structured command/response channel communication pattern
   - Returns "command not recognized" messages for unsupported commands

The main `commands.go` file now serves as the command registration and routing system, determining which tier should handle a given command and directing it appropriately. Movement commands (GO and MOVE) have been implemented as timed actions that respect character state, with support for both cardinal directions and named exits.

Command processing includes a timeout system where different commands have varying "wait periods" during which certain other commands cannot be executed. Character states (standing, sitting, prone, dead) affect command availability, with state-appropriate commands always accessible regardless of timeout status. The system currently implements a basic "standing" state by default, with plans to expand to sitting, prone, and dead states to influence command availability and character interactions.

Character sessions process commands through a strict parser that accepts only basic letters, numbers, and common special symbols, discarding any unrecognized input. Player input is managed through a thread-safe buffer system (player-buffer.go) that handles concurrent reads and writes with proper synchronization. Each command is evaluated to determine appropriate tier handling (character, room, or game) and routed accordingly through a structured channel system using CommandRequest and CommandResponse objects. Room commands are processed asynchronously in room-specific goroutines, while game-tier commands are escalated to the central game routine. This tiered approach ensures that only the appropriate components process each command, optimizing performance and ensuring proper state consistency. The proper cleanup and removal of characters from the game is a critical priority.

The game routine serves as the authoritative source for world state, managing all characters, rooms, items, and game mechanics including the passage of time. It handles all database operations through DynamoDB, using RAM caching to minimize database access and prevent blocking operations. While initially designed as a single routine, the architecture supports future scaling to multiple game routines, though this will require additional communication mechanisms.

The entire system is organized through a hierarchical context structure. The main package provides a global context that flows down through server and game components. The server context extends to interfaces, players, and characters, while interface contexts flow to players and characters. The game maintains its own context for characters, with each player having a context for their character, and each character maintaining its own context.

Testing will primarily be conducted through live user interaction, with unit tests implemented for functions that don't require network or cloud resources. The architecture heavily leverages AWS services, with CloudWatch handling metrics and logging, Cognito managing authentication, DynamoDB providing persistence, and S3 storing scripts. While the engine can run anywhere, it is optimized for AWS infrastructure. This design emphasizes clean separation of concerns while maintaining efficient communication patterns and supporting future scalability needs.

## Development Roadmap

### Completed Tasks

- [x] Core Server and Infrastructure
  - [x] Create the SSH server for client connections
  - [x] Implement a text parser for user input
  - [x] Add Cloudwatch Logs and Metrics integration
  - [x] Implement database with DynamoDB
  - [x] Set up AWS Cognito authentication
  - [x] Display connection IP address and port information
  - [x] Implement persistent logging
  - [x] Panic recovery and graceful shutdown
  - [x] Context-based coordination system

- [x] Player and Character Management
  - [x] Implement player authentication system
  - [x] Create character creation and selection system
  - [x] Build interactive password change system
  - [x] Add character list (who) command
  - [x] Add Bloom Filter to check for existing character names
  - [x] Allow character deletion
  - [x] Handle unplanned disconnections
  - [x] Display Message of the Day (MOTD)
  - [x] Player idle timeout with warnings
  - [x] Character persistence with DynamoDB

- [x] Command System
  - [x] Implement the three-tier command architecture
  - [x] Develop command timeout systems
  - [x] Add help command
  - [x] Add quit command
  - [x] Create character-commands.go, room-commands.go, game-commands.go modules
  - [x] Improve the say command
  - [x] Command wait time system for actions

- [x] Room System
  - [x] Implement movement commands with room state changes
  - [x] GO and MOVE commands for character movement
  - [x] Support for both cardinal directions and object-based exits
  - [x] Character state verification for movement
  - [x] Add room persistence flag to Room struct
  - [x] Add scriptID field to Room struct
  - [x] Implement Room goroutine system
  - [x] Create room goroutine management
  - [x] Add idle room detection and cleanup
  - [x] Implement item cleanup for empty rooms
  - [x] Allow starting room to be set by Archetype
  - [x] Update database tools to support room flags and scripts
  - [x] Enhanced exit system with descriptive exits
  - [x] Support for non-cardinal direction exits (doors, portals, stairs)
  - [x] Custom arrival/departure messaging for player movement
  - [x] Exit visibility controls for hidden paths

- [x] Item System Foundation
  - [x] Basic item data structures
  - [x] Item persistence in DynamoDB
  - [x] Item trait system for modifications
  - [x] Worn item tracking and state
  - [x] Hand system for holding items (left and right hands)
  - [x] Items picked up go to hands first (right hand is dominant)
  - [x] Switch command to swap items between hands

- [x] Communication System
  - [x] Say command with room-wide communication
  - [ ] Shout command for server-wide messages
  - [ ] Announce command for GM announcements
  - [ ] Whisper command for private messages

- [x] Stealth System
  - [x] Hide command to become invisible
  - [x] Unhide command to become visible
  - [x] Sneak command for stealthy movement
  - [x] Search command to find hidden characters
  - [x] Point command to reveal hidden characters
  - [x] Perception-based detection mechanics

- [x] Combat System (Basic)
  - [x] Face command to target opponents
  - [x] Assess command for combat situation
  - [x] Advance/Retreat for range management
  - [x] Flee command to escape combat
  - [x] Range-based combat positioning
  - [ ] Attack and damage resolution
  - [ ] Weapon and armor mechanics

- [x] Death and Revival System
  - [x] Character death states
  - [x] Ghost form for dead characters
  - [x] Depart command for revival
  - [x] State-based command restrictions

- [x] Experience and Skills
  - [x] Skill-based resolution system
  - [x] XP rewards from actions
  - [x] Variance-based XP modifiers
  - [x] Skill progression mechanics
  - [x] Attribute advancement

- [x] Security Features
  - [x] SSH authentication rate limiting
  - [x] IP-based and username-based ban system
  - [x] Obscenity filter for character names

### Upcoming Tasks (Priority Order)

#### High Priority - Core Functionality

- [ ] Item System Completion
  - [x] Implement inventory command to view items and hands
  - [x] Add get/take commands for picking up items (to hands)
  - [x] Add drop command for dropping items (from hands or inventory)
  - [x] Add wear/remove commands for equipment
  - [x] Add switch command for swapping hand items
  - [ ] Add examine command for detailed item inspection
  - [ ] Implement item USE verb interactions
  - [ ] Load item prototypes at startup
  - [ ] Create item prototype factory function

- [ ] Combat System Completion
  - [x] Face/assess/advance/retreat positioning
  - [ ] Attack command implementation
  - [ ] Damage calculation and application
  - [ ] Weapon skill integration
  - [ ] Armor and defense mechanics
  - [ ] Combat rounds and timing

- [ ] Communication Commands
  - [ ] Implement shout for server-wide messages
  - [ ] Implement announce for admin messages
  - [ ] Implement whisper for private messages
  - [ ] Add emote system

- [ ] Administrative Features
  - [ ] Implement privilege/permission system
  - [ ] Add @shutdown command for admins
  - [ ] Add @broadcast command for system messages
  - [ ] Create GM-only command prefix handling

- [ ] Command Rate Limiting
  - [ ] Implement per-player command rate limiting (5/second)
  - [ ] Add command frequency tracking
  - [ ] Implement queue/drop strategy for excess commands

- [ ] Build & Deploy Automation
  - [ ] Create server build script with version stamping
  - [ ] Implement automated deployment (systemd/Docker)
  - [ ] Set up CodeBuild pipeline for server compilation
  - [ ] Create Packer-based AMI deployment

#### Medium Priority - Enhanced Features

- [ ] Logging & Audit Trail
  - [ ] Implement dedicated audit logging for commands
  - [ ] Add command origin tracking (player ID, IP, session)
  - [ ] Create separate audit log stream

- [ ] Character Features
  - [ ] Implement auto-save functionality
  - [ ] Add dynamic prompt with HP/status
  - [x] Character states implemented (standing, sitting, prone, dead, ghost)

- [ ] Room System Extension
  - [x] S3-based script storage implemented
  - [ ] Additional script event types
  - [ ] Validate graph of loaded rooms and exits
  - [ ] Expand Lua scripting API capabilities

#### Low Priority - Advanced Features

- [ ] Advanced Features (Long-term)
  - [ ] Develop a weather and time system
  - [ ] Create a crafting system for items
  - [ ] Design an economic framework
  - [ ] Build a direct messaging system
  - [ ] Develop Non-Player Characters (NPCs)
  - [ ] Design and implement a quest system
  - [ ] Implement a party system for cooperative gameplay
  - [ ] Implement a magic system
  - [ ] Implement a reputation system
  - [ ] Develop a conditional room description system

## Commands

Game Information:

- [x] HELP: Display a list of commands.
- [ ] MAP: Display a map of the current area.
- [ ] TIME: Display the current time.
- [x] MOTD: Display the message of the day (shown on login).
- [ ] REPORT: Report a bug or issue.
- [ ] BUG: Report a bug or issue.
- [x] WHO: Display a list of players.

Basic Movement:

- [x] GO: Move to a new room using cardinal directions or named exits.
- [x] MOVE: Alias for GO command.
- [x] LOOK: Look at the current room.
- [ ] CLIMB: Climb an object like a tree or ladder.
- [ ] SWIM: Swim through water.
- [ ] JUMP: Jump over an object.
- [x] SNEAK: Move quietly while hidden.
- [x] FLEE: Escape from combat.

Objects and Inventory:

- [x] GET: Pick up an object (goes to right hand, then left hand if right is full).
- [x] DROP: Drop an object (from hands or inventory).
- [x] PUT: Put an object in a container (from hands or inventory).
- [x] TAKE: Take an object from a container (goes to hands).
- [x] INVENTORY: Display the contents of your inventory and hands.
- [x] WEAR: Wear an object.
- [x] REMOVE: Remove an object.
- [x] SWITCH: Switch items between your left and right hands.
- [ ] EXAMINE: Examine an object.
- [ ] EAT: Eat an object.
- [ ] DRINK: Drink an object.

Communication:

- [x] SAY: Speak to other players in the same room.
- [ ] WHISPER: Speak privately to another player.
- [ ] SHOUT: Shout server-wide message.
- [ ] ANNOUNCE: Admin announcement to all players.
- [ ] EMOTE: Perform an action.

Combat:

- [x] FACE: Face another player or NPC.
- [x] ADVANCE: Move towards another player or NPC.
- [x] RETREAT: Move away from another player or NPC.
- [x] ASSESS: Assess the situation.
- [ ] ATTACK: Attack another player or NPC.
- [ ] LOAD: Load a weapon.
- [ ] FIRE: Fire a weapon.

Character Management:

- [x] INFO: Display your character information (including held items).
- [x] SKILL: Display your skills.
- [ ] STATUS: Display the character status.
- [x] INVENTORY: Display the contents of your inventory and hands.

Group:

- [ ] GROUP: Create a group.
- [ ] JOIN: Join a group.
- [ ] FOPLLOW: Follow a group member.
- [ ] LEAVE: Leave a group.
- [ ] DISBAND: Disband a group.
- [ ] FRIEND: Add a friend.

Commerce:

- [ ] SHOP: Brows items available from a merchant
- [ ] BUY: Purchase an item from a merchant.
- [ ] SELL: Sell an item to a merchant.
- [ ] TRADE: Trade an item with another player.

Magic:

- [ ] PREPARE: Prepare a spell or ritual
- [ ] CAST: Cast a spell or ritual.
- [ ] DISPEL: Dispel a spell.

Crafting:

- [ ] FORAGE: Gather materials from the environment.
- [ ] CRAFT: Create an item from materials.
- [ ] SKIN: Remove materials from a creature.

Session Management:

- [x] QUIT: Exit the game.
- [ ] SETTINGS: Change your settings.

Stealth:

- [x] HIDE: Hide from other players.
- [x] SEARCH: Search for hidden objects or players.
- [x] UNHIDE: Reveal yourself.
- [x] POINT: Reveal a hidden character to everyone.

OTHER:

- [ ] USE: Use an object.
- [x] DEPART: Ghost command to return to life at a revival point.

## Implementation Status

### Server Architecture

- [x] Establish two primary goroutines (server and game)
- [x] Implement context-based coordination rather than WaitGroups
- [ ] Support 1,000 concurrent players
- [x] Implement room goroutine architecture
- [x] Panic recovery in all goroutines
- [x] Graceful shutdown with proper cleanup

### Room System

- [x] Individual room goroutines
- [x] Room persistence flag implementation
- [x] Room script ID implementation
- [x] Room activity tracking mechanism
- [ ] Script-driven room behaviors
- [x] Idle room detection and cleanup
- [x] Room unloading for non-persistent empty rooms
- [x] Item cleanup for empty rooms
- [x] Enhanced exit system with custom messages

### Scripting System

- [x] Script struct implementation
- [x] S3-based script storage and retrieval
- [x] In-memory script caching
- [x] Lua integration for room and item scripts
- [x] Basic scripting API (scripting-api.go)
- [ ] Additional script event hooks (onTimer, etc.)

### Interfaces

- [x] SSH interface implementation
- [ ] HTTPS interface implementation
- [ ] gRPC interface implementation
- [x] SSH authentication rate limiting
- [x] CloudWatch metrics reporting

### Authentication

- [x] AWS Cognito integration
- [x] User authentication flow
- [x] Password change functionality
- [x] Session management with idle timeout
- [x] IP-based ban system

### Player Management

- [x] Player session handling
- [x] Character creation
- [x] Character selection
- [x] Character deletion
- [ ] Command-level rate limiting
- [x] Console formatting for sensitive input
- [x] Player idle timeout (15 minutes)
- [x] Obscenity filter for names

### Character System

- [x] Command parsing system
- [x] Three-tier command architecture
  - [x] Modular file organization (character-commands.go, room-commands.go, game-commands.go)
  - [x] Command routing and tier determination
  - [x] Command error handling and validation
  - [x] Sub-modules for specialized commands:
    - [x] room-commands-stealth.go (hide/search mechanics)
    - [x] room-commands-items.go (item manipulation)
    - [x] room-commands-movement.go (movement system)
    - [x] room-commands-item-containers.go (container interactions)
- [x] Command wait time system
- [x] Character states (standing, sitting, prone, dead, ghost)
- [x] I/O buffering with channel limits
- [x] Thread-safe player input buffer (player-buffer.go)
- [x] Character state persistence
- [x] Character cleanup on disconnect
- [x] Experience and skill progression
- [x] Mechanics resolution system

### Game World

- [x] Basic room implementation
- [x] Room activity tracking
- [x] Exit implementation
  - [x] Directional and object-based exits (e.g., "north", "stairs", "portal")
  - [x] Custom exit descriptions and arrival messages
  - [x] Support for hidden/visible exits
  - [ ] Script hooks for exit-triggered events
- [ ] Item interaction system with verbs
- [x] Archetype system
- [ ] Combat system
- [ ] Time passage simulation
- [x] Basic item structures and persistence

### Database

- [x] DynamoDB integration
- [x] Database operations abstraction
- [x] Support for room persistence in database tools
- [x] Support for room script IDs in database tools
- [x] Character and item transactional saves
- [x] Non-blocking database operations via goroutines

### AWS Integration

- [x] CloudWatch for metrics and logging
- [x] Cognito for authentication
- [x] DynamoDB for persistence
- [x] S3 for script storage
- [x] CloudFormation deployment scripts
- [x] CodeBuild for portal deployment

### Testing

- [ ] Unit testing for standalone functions
- [x] Live user interaction testing

## Known Issues and GitHub Tracking

### Primary Technical Debt

1. **Item System Partially Complete** - Basic commands implemented, examine and use verbs needed
2. **Script System Partially Complete** - Basic Lua scripting works but additional event types needed
3. **Combat System Partially Complete** - Positioning implemented but attack/damage resolution missing
4. **Missing Admin Tools** - No in-game administration capabilities (@shutdown, @broadcast)
5. **Communication Commands Incomplete** - Shout, announce, whisper not implemented
6. **No Command Rate Limiting** - Per-player rate limiting system not implemented

## Web Portal

A Flutter application for player registration and self-service.

## Deployment

### AWS Infrastructure Setup

1. Ensure you have the following installed:
   - Go 1.24 or later
   - Python 3.12 or later
   - Flutter 3.29 or later
   - AWS CLI configured with appropriate credentials

2. Clone the repository:

   ```bash
   git clone https://github.com/robinje/eidolon-engine.git
   cd eidolon-engine
   ```

3. Install Python dependencies:

   ```bash
   pip install -r requirements/scripts-requirements.txt
   ```

4. Deploy AWS infrastructure:
   ```bash
   cd deployment
   python deploy.py
   ```
   This creates:
   - Cognito user pool for authentication
   - DynamoDB tables for game data
   - CloudWatch log groups and metrics
   - CodeBuild project for portal deployment

### Server Build and Run

1. Copy and configure the server:

   ```bash
   cd server
   cp config.template.yml config.yml
   # Edit config.yml with your AWS resource IDs
   ```

2. Build the server:

   ```bash
   go build -o eidolon-engine
   ```

3. Run the server:
   ```bash
   ./eidolon-engine
   ```

### Portal Deployment

The Flutter web portal is automatically deployed via CodeBuild when triggered by the deployment script.

## License

This project is licensed under the Apache 2.0 License. See the LICENSE file for more details.
