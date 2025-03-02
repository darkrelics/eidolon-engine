# Eidolon Engine System Design

## Server Design Goals

The Eidolon Engine system is built around two primary goroutines - server and game - which form the backbone of the architecture. The server component manages external interfaces, beginning with SSH and designed to later accommodate HTTPS and gRPC. It handles authentication through AWS Cognito, controls all external I/O operations, and tracks active interfaces. When players connect, the server creates individual player sessions through the appropriate interface, with communication managed through dedicated channels for input, output, and errors.

Each interface implements protocol-specific rate limiting and reports metrics to CloudWatch. The interfaces track their active players, with the system designed to support approximately 1000 concurrent players. Rather than using WaitGroups, the system relies on context and channels for coordinating operations and shutdowns between components.

Player sessions serve as the bridge between the interface and game world, handling essential functions like displaying messages of the day, character management, and console formatting for passwords and other sensitive input. Each session implements anti-abuse rate limiting and maintains clear communication boundaries through channels at both the interface and character layers. When a player creates or selects a character, the player session spawns a character session while maintaining tracking of its associated characters.

Character sessions process commands through a strict parser that accepts only basic letters, numbers, and common special symbols, discarding any unrecognized input. These sessions determine which commands can be handled locally and which need to be elevated to the game routine. They maintain their own I/O buffering with game-defined limits and communicate with the game routine through dedicated channels. The proper cleanup and removal of characters from the game is a critical priority.

The game routine serves as the authoritative source for world state, managing all characters, rooms, items, and game mechanics including the passage of time. It handles all database operations through DynamoDB, using RAM caching to minimize database access and prevent blocking operations. While initially designed as a single routine, the architecture supports future scaling to multiple game routines, though this will require additional communication mechanisms.

The entire system is organized through a hierarchical context structure. The main package provides a global context that flows down through server and game components. The server context extends to interfaces, players, and characters, while interface contexts flow to players and characters. The game maintains its own context for characters, with each player having a context for their character, and each character maintaining its own context.

Testing will primarily be conducted through live user interaction, with unit tests implemented for functions that don't require network or cloud resources. The architecture heavily leverages AWS services, with CloudWatch handling metrics and logging, Cognito managing authentication, and DynamoDB providing persistence. While the engine can run anywhere, it is optimized for AWS infrastructure. This design emphasizes clean separation of concerns while maintaining efficient communication patterns and supporting future scalability needs.

## Project State

### Server Architecture
- [x] Establish two primary goroutines (server and game)
- [x] Implement context-based coordination rather than WaitGroups
- [ ] Support 1,000 concurrent players

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
- [x] Local vs. game command handling
- [ ] I/O buffering with game-defined limits
- [x] Character state persistence
- [x] Character cleanup on disconnect

### Game World
- [ ] Room implementation
- [ ] Exit implementation
- [ ] Item implementation
- [ ] Archetype system
- [ ] Combat system
- [ ] Time passage simulation

### Database
- [x] DynamoDB integration
- [x] Database operations abstraction
- [ ] RAM caching to minimize database access
- [ ] Non-blocking database operations

### AWS Integration
- [x] CloudWatch for metrics and logging
- [x] Cognito for authentication
- [x] DynamoDB for persistence
- [ ] Infrastructure optimization for AWS

### Testing
- [ ] Unit testing for standalone functions
- [ ] Live user interaction testing