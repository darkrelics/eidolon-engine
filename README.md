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

A multi-mode game engine supporting both incremental RPG and MUD (Multi-User Dungeon) gameplay through a unified AWS backend.

## Overview

Eidolon Engine provides three deployment modes using shared backend infrastructure:

- **Incremental Mode**: Timer-based story progression with automated gameplay
- **MUD Mode**: Traditional text-based multiplayer game with SSH access
- **Hybrid Mode**: Combined incremental and MUD server deployment

The system uses AWS Lambda functions as the primary backend, with different frontend applications for each mode.

## Key Features

### Game Features
- Character progression through skills and attributes (no levels)
- Timer-based incremental gameplay mechanics
- Real-time MUD interactions via SSH
- Persistent game state across sessions
- Lua scripting for game content

### Technical Features
- AWS Lambda backend for all game logic
- DynamoDB for data persistence
- Infrastructure as Code using AWS CDK
- Automated deployment pipelines
- Flutter web applications
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

- Python 3.12+
- Go 1.24+ (for MUD server)
- Flutter 3.29+ (for web interfaces)
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

3. **Choose deployment mode**:
   - **Incremental Only**: Deploys incremental game UI and Lambda backend
   - **MUD Only**: Deploys portal UI, Lambda backend, and prepares for server
   - **Hybrid**: Full deployment with all components

4. **Access your game**:
   - Web interfaces available via CloudFront distribution
   - SSH server can be run locally or on EC2 (MUD mode)

## Documentation

Comprehensive documentation is available in the `/documentation` directory:

- [Architecture Overview](documentation/architecture/overview.md)
- [Deployment Guide](documentation/deployment/deployment-guide.md)
- [Game Design](documentation/game-design/)
- [API Reference](documentation/api/lambda-functions.md)
- [Development Setup](documentation/development/local-setup.md)

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

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines and coding standards.

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

The engine supports three deployment configurations, all using the same unified backend:

1. **Incremental Mode**: Deploys the incremental game UI with timer-based progression
2. **MUD Mode**: Deploys the Portal web interface for MUD access (SSH server deployed separately)
3. **Hybrid Mode**: Deploys the incremental UI while supporting both game types

All modes share the same Lambda functions and DynamoDB tables. The character GameMode field ensures a character can only be active in one mode at a time, preventing concurrent access issues.

## Contributing

Contributions are welcome. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Code style and standards
- Testing requirements
- Pull request process
- Issue reporting

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.

## Contact

- GitHub Issues: For bug reports and feature requests
- Email: contact@darkrelics.net