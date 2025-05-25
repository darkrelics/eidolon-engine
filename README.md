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

Character sessions process commands through a strict parser that accepts only basic letters, numbers, and common special symbols, discarding any unrecognized input. Each command is evaluated to determine appropriate tier handling (character, room, or game) and routed accordingly through a structured channel system using CommandRequest and CommandResponse objects. Room commands are processed asynchronously in room-specific goroutines, while game-tier commands are escalated to the central game routine. This tiered approach ensures that only the appropriate components process each command, optimizing performance and ensuring proper state consistency. The proper cleanup and removal of characters from the game is a critical priority.

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

- [x] Communication System
  - [x] Say command with room-wide communication
  - [x] Shout command for server-wide messages
  - [x] Announce command for GM announcements

- [x] Security Features
  - [x] SSH authentication rate limiting
  - [x] IP-based and username-based ban system
  - [x] Obscenity filter for character names

### Upcoming Tasks (Priority Order)

#### High Priority - Core Functionality

- [ ] Item System Completion

  - [ ] Implement inventory command to view items
  - [ ] Add get/take commands for picking up items
  - [ ] Add drop command for dropping items
  - [ ] Add wear/remove commands for equipment
  - [ ] Add examine command for detailed item inspection
  - [ ] Implement item verb interactions
  - [ ] Load item prototypes at startup
  - [ ] Create item prototype factory function

- [ ] Administrative Features (Milestone 9)

  - [ ] Implement privilege/permission system
  - [ ] Add @shutdown command for admins
  - [ ] Add @broadcast command for system messages
  - [ ] Create GM-only command prefix handling

- [ ] Command Rate Limiting (Milestone 10)

  - [ ] Implement per-player command rate limiting (5/second)
  - [ ] Add command frequency tracking
  - [ ] Implement queue/drop strategy for excess commands

- [ ] Build & Deploy Automation (Milestone 11)

  - [ ] Create server build script with version stamping
  - [ ] Implement automated deployment (systemd/Docker)
  - [ ] Set up CodeBuild pipeline for server compilation
  - [ ] Create Packer-based AMI deployment

#### Medium Priority - Enhanced Features

- [ ] Logging & Audit Trail (Milestone 8)

  - [ ] Implement dedicated audit logging for commands
  - [ ] Add command origin tracking (player ID, IP, session)
  - [ ] Create separate audit log stream

- [ ] Character Features

  - [ ] Implement auto-save functionality
  - [ ] Add dynamic prompt with HP/status (Milestone 6)
  - [ ] Expand character states (sitting, prone, dead)
  - [ ] Add whisper command for private communication

- [ ] Room System Extension

  - [ ] Create Script management system with S3 storage
  - [ ] Implement room script loading from S3
  - [ ] Validate graph of loaded rooms and exits
  - [ ] Add Lua scripting support

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
- [ ] SNEAK: Move quietly.

Objects and Inventory:

- [ ] GET: Pick up an object.
- [ ] DROP: Drop an object.
- [ ] PUT: Put an object in a container.
- [ ] TAKE: Take an object from a container.
- [ ] INVENTORY: Display the contents of your inventory.
- [ ] WEAR: Wear an object.
- [ ] REMOVE: Remove an object.
- [ ] EXAMINE: Examine an object.
- [ ] EAT: Eat an object.
- [ ] DRINK: Drink an object.

Communication:

- [x] SAY: Speak to other players in the same room.
- [ ] WHISPER: Speak privately to another player.
- [x] SHOUT: Shout server-wide message.
- [x] ANNOUNCE: Admin announcement to all players.
- [ ] EMOTE: Perform an action.

Combat:

- [ ] FACE: Face another player or NPC.
- [ ] ADVACE: Move towards another player or NPC.
- [ ] RETREAT: Move away from another player or NPC.
- [ ] ASSESS: Assess the situation.
- [ ] ATTACK: Attack another player or NPC.
- [ ] LOAD: Load a weapon.
- [ ] FIRE: Fire a weapon.

Character Manegment:

- [x] INFO: Display your character information.
- [x] SKILL: Display your skills.
- [ ] STATUS: Display the character status.
- [ ] INVENTORY: Display the contents of your inventory.

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

OTHER:

- [ ] HIDE: Hide from other players.
- [ ] SEARCH: Search for hidden objects.
- [ ] UNHIDE: Reveal yourself.
- [ ] USE: Use an object.

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

- [ ] Script struct implementation
- [ ] S3-based script storage
- [ ] In-memory script caching
- [ ] Lua integration for room and item scripts

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
- [x] Command wait time system
- [x] Basic character state tracking (standing)
- [ ] Advanced character states (sitting, prone, dead)
- [x] I/O buffering with channel limits
- [x] Character state persistence
- [x] Character cleanup on disconnect

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
- [ ] RAM caching to minimize database access
- [x] Non-blocking database operations via goroutines

### AWS Integration

- [x] CloudWatch for metrics and logging
- [x] Cognito for authentication
- [x] DynamoDB for persistence
- [ ] S3 for script storage
- [x] CloudFormation deployment scripts
- [x] CodeBuild for portal deployment

### Testing

- [ ] Unit testing for standalone functions
- [x] Live user interaction testing

## Known Issues and GitHub Tracking

### Open Enhancement Issues

- [#501](https://github.com/robinje/eidolon-engine/issues/501) - Implement Dynamic Prompt Formatter (Milestone 6)
- [#502](https://github.com/robinje/eidolon-engine/issues/502) - Implement Character Auto-Save Feature
- [#503](https://github.com/robinje/eidolon-engine/issues/503) - Implement Audit Logging for Commands
- [#504](https://github.com/robinje/eidolon-engine/issues/504) - Add Command Origin Tracking
- [#505](https://github.com/robinje/eidolon-engine/issues/505) - Implement Player Privilege System
- [#506](https://github.com/robinje/eidolon-engine/issues/506) - Implement @shutdown Administrative Command
- [#507](https://github.com/robinje/eidolon-engine/issues/507) - Implement @broadcast Administrative Command
- [#508](https://github.com/robinje/eidolon-engine/issues/508) - Implement Command Rate Limiting (Milestone 10)
- [#509](https://github.com/robinje/eidolon-engine/issues/509) - Create EC2 AMI Deployment Pipeline
- [#510](https://github.com/robinje/eidolon-engine/issues/510) - Implement Server Build Pipeline

### Primary Technical Debt

1. **Item System Incomplete** - Basic structures exist but no player commands
2. **No Script System** - Room/item scripting not implemented
3. **Limited State Management** - Only "standing" state implemented
4. **No Combat System** - Combat commands and mechanics not implemented
5. **Missing Admin Tools** - No in-game administration capabilities

### Recent Progress

- Implemented player idle timeout system with configurable warnings
- Added comprehensive panic recovery and graceful shutdown
- Enhanced exit system with custom descriptions and visibility controls
- Implemented basic communication commands (say, shout, announce)
- Added SSH authentication rate limiting and ban system
- Created modular command architecture with dedicated files per tier

### Critical Issues

1. **Weak Password Validation (interface_ssh.go)**:
   - Password validation only checks length (minimum 8 characters)
   - No requirements for complexity (uppercase, lowercase, numbers, symbols)
   - Located in `isValidPassword` function (lines 412-419)

### High Severity Issues

1. **Command Rate Limiting Missing**:
   - No per-player command rate limiting implemented
   - System vulnerable to command spam/flooding
   - SSH auth has rate limiting, but game commands do not

2. **No Administrative Commands**:
   - No privilege system for GM/admin users
   - Cannot shutdown server remotely
   - No way to broadcast system messages

3. **Incomplete Audit Logging**:
   - Commands logged at Debug level only
   - No dedicated audit trail with player attribution
   - Missing command origin tracking (IP, session)

4. **No Automated Build/Deploy**:
   - Manual build process prone to errors
   - No version stamping in binaries
   - No automated deployment mechanism

5. **Missing Dynamic Prompts**:
   - Static prompts don't show player status
   - No HP/Essence display in prompt
   - Prompts not sent after game ticks

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
