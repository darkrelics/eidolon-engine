# Deployment Modes Comparison

## Overview

The Eidolon Engine supports three deployment modes, all sharing the same backend infrastructure (Lambda functions, DynamoDB tables, and authentication). The modes differ only in which frontend application is deployed.

## Mode Comparison Table

| Aspect | MUD Mode | Incremental Mode | Hybrid Mode |
|--------|----------|------------------|-------------|
| **Frontend Deployed** | Portal (Flutter web) | Incremental (Flutter web) | Incremental (Flutter web) |
| **Primary Interface** | Web portal for MUD | Timer-based incremental game | Timer-based incremental game |
| **SSH Server** | Deployed separately | Not used | Deployed separately |
| **Backend Infrastructure** | Full shared backend | Full shared backend | Full shared backend |
| **Lambda Functions** | All functions available | All functions available | All functions available |
| **DynamoDB Tables** | All tables available | All tables available | All tables available |
| **Character Support** | MUD mode only | Incremental mode only | Both modes supported |
| **GameMode Values** | "MUD" | "Incremental" | "MUD" or "Incremental" |
| **Use Case** | Traditional MUD experience | Casual incremental gameplay | Full game experience |

## Deployment Commands

```bash
# Deploy in MUD mode (Portal frontend)
python deployment/deploy.py --deploy-mud

# Deploy in Incremental mode
python deployment/deploy.py --deploy-incremental

# Deploy in Hybrid mode (default)
python deployment/deploy.py --deploy-both
```

## Frontend Applications

### Portal (MUD Mode)
- **Location**: `/portal`
- **Purpose**: Web interface for MUD gameplay
- **Features**: Character management, game connection info, account settings
- **Connects to**: SSH server (deployed separately) or future WebSocket interface

### Incremental (Incremental/Hybrid Modes)
- **Location**: `/incremental`
- **Purpose**: Timer-based incremental RPG
- **Features**: Story progression, automated gameplay, character development
- **Connects to**: Lambda APIs directly

## Backend Infrastructure (Shared by All Modes)

### Lambda Functions
All Lambda functions are available in all modes:
- Character management (create, list, delete, save)
- Authentication triggers
- Game state management
- Future: Story progression, segment tracking

### DynamoDB Tables
All tables are shared across modes:
- Players (unified authentication)
- Characters (with GameMode field)
- Archetypes, Items, Rooms, Exits
- Prototypes, MOTD
- Future: Stories, ActiveSegments, CharacterHistory

### Character Mode Switching

The GameMode field on each character controls which game mode can access it:
- Characters can switch between modes (with restrictions)
- Prevents concurrent access from both modes
- Enforced by Lambda function validation

## Choosing a Deployment Mode

### Choose MUD Mode when:
- You only want the traditional MUD experience
- Players will connect via SSH or web portal
- You don't need incremental gameplay features

### Choose Incremental Mode when:
- You only want the incremental/idle game experience
- Players prefer automated, timer-based gameplay
- You don't need real-time MUD interactions

### Choose Hybrid Mode when:
- You want to offer both gameplay styles
- Players can choose their preferred experience
- You want maximum flexibility for future features

## Technical Considerations

### CORS Configuration
- API Gateway CORS settings accommodate all frontends
- CloudFront distributions are mode-specific
- Lambda functions handle CORS for their mode's origins

### CodeBuild Projects
- Build process selects appropriate frontend based on mode
- `buildspec/portal.yml` for MUD mode
- `buildspec/incremental.yml` for Incremental/Hybrid modes

### Future Enhancements
- WebSocket support for real-time MUD in browser
- Cross-mode character viewing (read-only)
- Unified leaderboards across modes