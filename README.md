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

The main `commands.go` file now serves as the command registration and routing system, determining which tier should handle a given command and directing it appropriately. Direction commands have been removed as they will be implemented using an alternative method in the future.

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

- [x] Player and Character Management
  - [x] Implement player authentication system
  - [x] Create character creation and selection system
  - [x] Build interactive password change system
  - [x] Add character list (who) command
  - [x] Add Bloom Filter to check for existing character names
  - [x] Allow character deletion
  - [x] Handle unplanned disconnections
  - [x] Display Message of the Day (MOTD)

- [x] Command System
  - [x] Implement the three-tier command architecture
  - [x] Develop command timeout systems
  - [x] Add help command
  - [x] Add quit command
  - [x] Create character-commands.go, room-commands.go, game-commands.go modules
  - [x] Improve the say command

- [x] Room System
  - [x] Implement movement commands with room state changes
  - [x] Add room persistence flag to Room struct
  - [x] Add scriptID field to Room struct
  - [x] Implement Room goroutine system
  - [x] Create room goroutine management
  - [x] Add idle room detection and cleanup
  - [x] Implement item cleanup for empty rooms
  - [x] Allow starting room to be set by Archetype
  - [x] Update database tools to support room flags and scripts

### Upcoming Tasks
- [ ] Item System
  - [ ] Construct the item system with verb interactions
  - [ ] Load item prototypes at start
  - [ ] Create item prototype factory function
  - [ ] Add inventory, get, take, drop commands
  - [ ] Add wear, remove, examine commands

- [ ] Command System Enhancements
  - [ ] Add state tracking for timeout management
  - [ ] Implement command queuing system
  - [ ] Add look at item command

- [ ] Room System Extension
  - [ ] Create Script management system with S3 storage
  - [ ] Implement room script loading from S3
  - [ ] Validate graph of loaded rooms and exits

- [ ] Player Features
  - [ ] Expand the character creation process
  - [ ] Develop player communication systems (whisper, shout)
  - [ ] Implement an obscenity filter
  - [ ] Improve input filters

- [ ] Administration Tools
  - [ ] Create administrative interface
  - [ ] Force password resets when needed
  - [ ] Add account deletion, ban, and mute capabilities
  - [ ] Limit auto-save to updated objects
  - [ ] Add rate limiting to the server
  - [ ] Add session timeout

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
- [ ] MOTD: Display the message of the day.
- [ ] REPORT: Report a bug or issue.
- [ ] BUG: Report a bug or issue.
- [x] WHO: Display a list of players.

Basic Movement:

- [x] GO: Move to a new room.
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

- [ ] SAY: Speak to other players.
- [ ] WHISPER: Speak privately to another player.
- [ ] SHOUT: Shout to the adjacent rooms.
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

- [ ] SHOW: Display your character information.
- [ ] SKILL: Display your skills.
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

### Room System

- [x] Individual room goroutines
- [x] Room persistence flag implementation
- [x] Room script ID implementation
- [x] Room activity tracking mechanism
- [ ] Script-driven room behaviors
- [x] Idle room detection and cleanup
- [x] Room unloading for non-persistent empty rooms
- [x] Item cleanup for empty rooms

### Scripting System

- [ ] Script struct implementation
- [ ] S3-based script storage
- [ ] In-memory script caching
- [ ] Lua integration for room and item scripts

### Interfaces

- [x] SSH interface implementation
- [ ] HTTPS interface implementation
- [ ] gRPC interface implementation
- [ ] Protocol-specific rate limiting
- [x] CloudWatch metrics reporting

### Authentication

- [x] AWS Cognito integration
- [x] User authentication flow
- [x] Password change functionality
- [ ] Session management

### Player Management

- [x] Player session handling
- [x] Character creation
- [x] Character selection
- [x] Character deletion
- [ ] Anti-abuse rate limiting
- [x] Console formatting for sensitive input

### Character System

- [x] Command parsing system
- [x] Three-tier command architecture
  - [x] Modular file organization (character-commands.go, room-commands.go, game-commands.go)
  - [x] Command routing and tier determination
  - [x] Command error handling and validation
- [ ] Command timeout system with roundtime
- [x] Basic character state tracking (standing)
- [ ] Advanced character states (sitting, prone, dead)
- [ ] I/O buffering with game-defined limits
- [x] Character state persistence
- [x] Character cleanup on disconnect

### Game World

- [x] Basic room implementation
- [x] Room activity tracking
- [ ] Exit implementation
- [ ] Item interaction system with verbs
- [x] Archetype system
- [ ] Combat system
- [ ] Time passage simulation

### Database

- [x] DynamoDB integration
- [x] Database operations abstraction
- [x] Support for room persistence in database tools
- [x] Support for room script IDs in database tools
- [ ] RAM caching to minimize database access
- [ ] Non-blocking database operations

### AWS Integration

- [x] CloudWatch for metrics and logging
- [x] Cognito for authentication
- [x] DynamoDB for persistence
- [ ] S3 for script storage
- [ ] Infrastructure optimization for AWS

### Testing

- [ ] Unit testing for standalone functions
- [ ] Live user interaction testing

## Recent Changes

### Core System Improvements

1. **Command System Restructuring**:

   - **Modular Architecture**: Separated command handling into three dedicated files:
     - `character-commands.go`: Fast, local character commands (help, info, skills, etc.)
     - `room-commands.go`: Room-level social and interactive commands (say, look, etc.)
     - `game-commands.go`: Global commands affecting the world (weather, who, etc.)
   - **Code Quality**: Enhanced error handling, fixed Printf-style function usage, removed unused methods
   - **Architectural Improvements**:
     - Removed direction commands (to be implemented differently)
     - Added fallback "command not recognized" responses
     - Simplified command tier determination
     - Streamlined `commands.go` to focus solely on command registration and routing

2. **Room System Enhancements**:

   - **Goroutine Management**: Implemented individual room goroutines with proper lifecycle methods
   - **Persistence System**: Added room persistence flags and activity tracking
   - **Resource Management**: Created idle room detection and cleanup mechanism
   - **Script Infrastructure**: Added scriptID field and supporting methods
   - **Database Integration**: Updated storage layer to support new room properties

These changes have significantly improved code organization, error handling, and system architecture while preparing for future scripting capabilities and ensuring efficient resource usage through proper room lifecycle management.

## Known Issues

### Summary

- **Critical Issues**: 2 issues - Security vulnerabilities related to credential handling and password validation
- **High Severity Issues**: 10 issues - Including race conditions, error handling problems, and memory management concerns
- **Medium Severity Issues**: 23 issues - Range from concurrency problems to design flaws and performance concerns
- **Low Severity Issues**: 30 issues - Code quality, logging, and minor design issues

### Primary Concerns

1. **Security vulnerabilities** - Credential handling and password validation still need improvement
2. **Race conditions and concurrency issues** - Several areas need mutex protection and proper synchronization
3. **Error handling gaps** - Error propagation and recovery need improvement
4. **Memory management concerns** - Large dataset handling requires pagination
5. **Hard-coded values** - Configuration should replace hard-coded values

### Recent Progress

The most recent commit (5494d81) addressed a logging issue in the portal code related to:

- Removed potentially insecure default values for configuration
- Improved error logging formats
- Simplified authentication error handling

### Critical Issues

1. **Insecure Credential Handling (cognito.go)**:

   - Sensitive credentials are passed as plain strings and could be accidentally logged
   - Located in the `Authenticate` function (lines 158-171)

2. **Weak Password Validation (interface_ssh.go)**:
   - Password validation only checks length (minimum 8 characters)
   - No requirements for complexity (uppercase, lowercase, numbers, symbols)
   - Located in `isValidPassword` function (lines 412-419)

### High Severity Issues

1. **Race Condition in Player Management (server.go)**:

   - Race condition between checking for existing session and adding new one
   - Could lead to security issues or resource leaks
   - Located in `AddPlayer` method (lines 295-307)

2. **Silent Failure in Session Management (server.go)**:

   - Method silently ignores failures to send disconnect messages
   - Located in `DuplicatePlayer` method (lines 326-333)

3. **Hidden Error Details (cognito.go)**:

   - Error details from Cognito are hidden from caller
   - Located in `SignUpUser` function (around line 70)

4. **No Authentication Rate Limiting (cognito.go)**:

   - Limited rate limiting on authentication attempts at application level
   - Makes the system vulnerable to brute force attacks

5. **Memory Issues with Large Datasets (database.go)**:

   - All DB query/scan items loaded into memory at once
   - Could cause out-of-memory issues with large datasets
   - Located in `Scan` and `Query` operations

6. **Insufficient Input Validation (player.go)**:

   - Insufficient validation/sanitization of player input
   - Could lead to command injection or other security issues

7. **Incomplete Error Handling in Player Data (player.go)**:

   - If saving player data fails, execution continues without proper handling

8. **Invalid UUID Handling (character.go)**:

   - The `GenerateUUIDv7` function doesn't handle errors from UUID generation
   - Could return nil and cause panics elsewhere

9. **SSH Connection Security (interface_ssh.go)**:

   - No validation of SSH connection parameters
   - No proper handling of unusual SSH client behavior

10. **Hard-Coded File Paths (game.go)**:
    - Critical game files use hard-coded paths
    - Makes deployment and configuration inflexible
    - Located in lines 36-37

## Action Items & Recommendations

### Immediate Priorities

- Fix the critical security vulnerabilities in `cognito.go` and `interface_ssh.go`
- Address the race condition in player management (server.go lines 295-307)
- Implement proper input validation for player commands
- Fix UUID generation error handling
- Begin implementation of room goroutine system
- Create script management structure

### Short-term Improvements

- Add database query pagination for large datasets
- Implement proper error handling in player data saving
- Consolidate player disconnection logic
- Move hard-coded values to configuration
- Continue room persistence system implementation
- Set up S3 script storage and loading

### Long-term Refactoring

- Implement comprehensive retry mechanisms with exponential backoff
- Improve context propagation throughout the codebase
- Improve concurrency patterns to avoid blocking operations
- Add versioning for data structures
- Enhance room scripting capabilities

## Web Portal

A Flutter application for player registration and self-service.

### Portal TODO

- [ ] Add unit tests
- [ ] Add integration tests
- [ ] Add widget tests
- [ ] Improve error messages
- [ ] Add retry mechanisms for network calls
- [ ] Add asset preloading
- [ ] Address client secret issues
- [ ] Add session timeout

## Deployment

Deploying the server involves several steps:

1. Ensure you have Go 1.24, Python 3.12 and Flutter 3.29 installed.
2. Clone the repository.
3. Install the required Python packages:
   ```
   pip install -r requirements/scripts-requirements.txt
   ```
4. Set up your AWS credentials (access key ID and secret access key) in your environment variables or AWS credentials file.
5. Run the deployment script:
   ```
   python scripts/deploy.py
   ```
   This script will create the necessary AWS resources using CloudFormation.
6. Once deployment is complete, build and run the server:
   ```
   cd ./server
   go build . -o server
   ./server
   ```

## License

This project is licensed under the Apache 2.0 License. See the LICENSE file for more details.
