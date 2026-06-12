[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

![GitHub](https://img.shields.io/badge/github-%23121011.svg?style=for-the-badge&logo=github&logoColor=white)
![Dependabot](https://img.shields.io/badge/dependabot-025E8C?style=for-the-badge&logo=dependabot&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/github%20actions-%232671E5.svg?style=for-the-badge&logo=githubactions&logoColor=white)

![AWS](https://img.shields.io/badge/AWS-%23FF9900.svg?style=for-the-badge&logo=amazon-aws&logoColor=white)
![AmazonDynamoDB](https://img.shields.io/badge/Amazon%20DynamoDB-4053D6?style=for-the-badge&logo=Amazon%20DynamoDB&logoColor=white)

![Go](https://img.shields.io/badge/go-%2300ADD8.svg?style=for-the-badge&logo=go&logoColor=white)
![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![Flutter](https://img.shields.io/badge/Flutter-%2302569B.svg?style=for-the-badge&logo=Flutter&logoColor=white)

# Eidolon Engine

A multi-mode game engine supporting both story-driven incremental RPG and traditional MUD (Multi-User Dungeon) gameplay through a unified AWS backend.

## Overview

Eidolon Engine provides three deployment modes with a fully automated infrastructure deployment system:

- **MUD Mode**: Traditional Multi-User Dungeon without story features
- **Incremental Mode**: Story-driven gameplay with narrative progression
- **Hybrid Mode**: Full feature set combining MUD and story elements (default)

The system features a complete end-to-end deployment pipeline that provisions all AWS infrastructure and automatically deploys the frontend application.

## Key Features

### Game Features

- Character progression through skills and attributes (no levels)
- Timer-based incremental gameplay mechanics
- Real-time MUD interactions via SSH
- Persistent game state across sessions

### Technical Features

- AWS Lambda backend for all game logic (23 functions)
- DynamoDB for data persistence (14 tables)
- Infrastructure as Code using AWS CDK (9 stacks)
- Fully automated deployment with portal build
- Three deployment modes with dynamic stack ordering
- Fixed logical IDs preventing resource recreation
- Post-deployment Lambda updates from S3 artifacts
- Flutter web applications with IndexedDB caching
- Go-based SSH server for MUD mode
- Lua scripting for game mechanics and content

## Architecture

The engine uses a modern cloud-native architecture with a unified backend serving multiple frontends:

- **Frontend Applications**:
  - Flutter web app for incremental gameplay (`/incremental`)
  - Flutter portal for MUD web interface (`/portal`)
  - SSH server for traditional MUD access (`/server`)

- **Unified Backend Services** (shared by all game modes):
  - AWS Lambda functions for all game logic (`/lambda`)
  - DynamoDB tables for persistent game state
  - Character GameMode field prevents concurrent MUD/Incremental access
  - S3 for content storage and scripts
  - Cognito for unified authentication
  - API Gateway providing RESTful endpoints

- **Shared Libraries**:
  - Python utilities for AWS services (`/eidolon`)
  - Lua scripts for MUD game mechanics (`/scripts_lua`)

## Getting Started

### Prerequisites

- Python 3.12
- Go 1.24+ (for MUD server)
- Flutter 3.32+ (for web interfaces)
- AWS CLI configured with appropriate credentials
- AWS CDK 2.x

### Quick Start

1. **Clone the repository**:

   ```bash
   git clone https://github.com/robinje/eidolon-engine.git
   cd eidolon-engine
   ```

2. **Deploy AWS infrastructure**:

   ```bash
   cd deployment
   pip install -r ../requirements/deployment-requirements.txt
   python deploy.py
   ```

3. **Deployment Process**:

   The deployment system will:
   - Prompt for configuration (AWS region, domain, deployment mode)
   - Deploy infrastructure in the correct order based on selected mode
   - Build Lambda functions and layer automatically
   - Execute portal build and deploy to CloudFront
   - Display the portal URL upon completion

4. **Deployment Modes**:
   - **MUD Mode**: Traditional MUD without story features (uses portal.yml buildspec)
   - **Incremental Mode**: Story-driven gameplay (uses incremental.yml buildspec)
   - **Hybrid Mode**: Full feature set (default, uses incremental.yml buildspec)

5. **Access your game**:
   - Portal URL: `https://portal.yourdomain.com` (displayed after deployment)
   - API endpoint: `https://api.yourdomain.com`
   - SSH server can be run locally or on EC2 (MUD mode)

## Implementation Status

### MUD Mode

Status: Production-ready and fully functional.

### Incremental Mode

Status: Core gameplay functional.

- ✅ Character creation and progression
- ✅ Story progression and branching narratives
- ✅ Skill/attribute XP system
- ✅ Combat mechanics (rounds execute, wounds apply)
- ✅ Item drops and inventory display (names resolved from prototypes)
- ✅ Death mechanics (dead characters cannot start or continue stories)
- ✅ Currency rewards (story reward tiers grant coin items)
- ✅ Store system (atomic purchases paying with coins)
- ✅ Item consumption, equipment, split/consolidate/move

**Current State:** The economy loop (earn currency → buy items → use items) is complete: story rewards grant coins as unbounded stackable items, and store purchases spend them atomically. See [Currency](documentation/currency.md) for the coin model.

**Details:** Remaining work is tracked in GitHub issues and the [Incremental Remediation Plan](documentation/incremental-remediation-plan.md).

## Documentation

Comprehensive documentation is available in the `/documentation` directory:

- [Incremental Remediation Plan](documentation/incremental-remediation-plan.md) - Current findings and remaining work
- [Deployment Design](documentation/deployment-design.md) - Architecture and infrastructure design
- [Deployment Guide](documentation/deployment.md) - Step-by-step deployment instructions
- [Incremental Game Design](documentation/incremental-design.md) - Game system design
- [Game Mechanics](documentation/mechanics.md) - Core gameplay mechanics
- [API Reference](documentation/lambda-functions.md) - Lambda function specifications

## Project Structure

```
eidolon-engine/
├── incremental/          # Flutter incremental game UI
├── portal/              # Flutter web portal for MUD
├── server/              # Go MUD server (SSH)
├── lambda/              # AWS Lambda functions
├── eidolon/             # Shared Python libraries
├── deployment/          # CDK infrastructure code
├── scripts_lua/         # Lua game scripts
├── documentation/       # Project documentation
└── data/               # Game configuration data
```

## Development

### Style Guides

- [Python Style Guide](documentation/python-style.md) - Python coding standards
- [Flutter Style Guide](documentation/flutter-style.md) - Flutter/Dart conventions
- [AWS Style Guide](documentation/aws-style.md) - Infrastructure patterns
- [Documentation Style Guide](documentation/style-guide.md) - Writing standards

### Running Locally

Each component can be developed independently:

```bash
# Incremental UI
cd incremental
flutter run -d chrome

# MUD Server
cd server
go run .

# Deploy infrastructure changes
cd deployment
python deploy.py --analyze-only
```

## Deployment Modes

Choose the deployment mode based on your game focus:

- **MUD Mode**: Excludes story features, uses traditional MUD interface (`portal.yml`)
- **Incremental Mode**: Excludes S3/CloudWatch stacks, uses story interface (`incremental.yml`)
- **Hybrid Mode** (Default): All features enabled, uses story interface (`incremental.yml`)

The deployment automatically adjusts stack order and buildspec selection based on the chosen mode.

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.

## Contact

- GitHub Issues: For bug reports and feature requests
- Email: contact@darkrelics.net
