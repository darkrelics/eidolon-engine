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

# Multi-User Dungeon Engine

The goal of this project is to create a commercial-quality multi-user dungeon (MUD) engine that is flexible enough to be used as either a conventional MUD or an interactive fiction game.

The current implementation includes an SSH server for secure authentication and communication between the player and the server. The engine is primarily written in Go. Additionally, there is a user management system stub written in JavaScript and various utility scripts written in Python.

## Project Overview

The engine is primarily written in Go (version 1.23) with an SSH server for secure authentication and communication between the player and the server. Additionally, there are database utility scripts written in Python (version 3.12) and various deployment scripts.

Key components:

- Go server (v1.23) for game logic and player interactions
- Python (v3.12) scripts for database management and deployment
- AWS services for database (DynamoDB) and Identity Provider (Cognito)
- CloudFormation templates for AWS resource management

## Current Objectives

- [x] Create the TCP server for client connections.
- [x] Create a text parser for user input.
- [x] Implement a player authentication system.
- [x] Implement a database for the game.
- [x] Implement a character creation system.
- [x] Implement a text colorization system.
- [x] Add Cloudwatch Logs and Metrics.
- [x] Build an interactive password change system.
- [ ] Develop a weather and time system.
- [ ] Construct the item system.
- [ ] Create a crafting system for items.
- [ ] Develop game mechanics.
- [ ] Design an economic framework
- [ ] Build a direct messaging system.
- [ ] Develop simple Non-Player Characters (NPCs).
- [ ] Design and implement a quest system.
- [ ] Implement a dynamic content updating system.
- [ ] Implement a player-to-player trading system.
- [ ] Implement a party system for cooperative gameplay.
- [ ] Implement a magic system.
- [ ] Impliment a quest tracking system.
- [ ] Impliment a reputation system.
- [ ] Develop a conditional room description system.
- [ ] Implement a world creation system.
- [ ] Develop more complex Non-Player Characters (NPCs) with basic AI.

## TODO

- [x] Fix output formatting for the client.
- [x] Allow players to enter their name.
- [x] Display the incoming IP address and Port on the server.
- [x] Add a help command.
- [x] Add a character list command.
- [x] Allow users to change their passwords.
- [x] Expand the character creation process.
- [x] Add take item command.
- [x] Add inventory command.
- [x] Add drop item command.
- [x] Add wear item command.
- [x] Add remove item command.
- [x] Add examine item command.
- [x] Implement Persistent Logging.
- [x] Load item prototypes at start.
- [x] Create function for creating items from prototypes.
- [x] Ensure that a message is passed when a character is added to the game.
- [x] Add a Message of the Day (MOTD) command.
- [x] Add Bloom Filter to check for existing characters names being used.
- [x] Add the ability to delete characters.
- [x] Allow starting room to be set by Archtype.
- [x] Improve the input filters
- [x] Handle unplanned disconnections.
- [x] Limit Auto Save to updated objects.
- [ ] Improve the say command.
- [ ] Add look at item command.
- [ ] Implement an obscenity filter.
- [ ] Validate graph of loaded rooms and exits.
- [ ] Create administrative interface.
- [ ] Force Password Resets when needed.
- [ ] Add the ability to delete accounts.
- [ ] Add the ability to ban accounts.
- [ ] Add the ability to mute accounts.
- [ ] Improve error handling.
- [ ] Perform data validation for base data.
- [ ] Add rate limiting to the server.
- [ ] Expand error handling.
- [ ] Add Session Timeout.

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

- [x] FACE: Face another player or NPC.
- [ ] ADVACE: Move towards another player or NPC.
- [ ] RETREAT: Move away from another player or NPC.
- [x] ASSESS: Assess the situation.
- [ ] ATTACK: Attack another player or NPC.
- [ ] PARRY: Defend against an attack.
- [ ] DODGE: Avoid an attack.
- [ ] LOAD: Load a weapon.
- [ ] FIRE: Fire a weapon.

Character Manegment:

- [ ] SKILLS: Display your skills.
- [ ] STATUS: Display the character status.

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

- [ ] PASSWORD: Change your password.
- [ ] QUIT: Exit the game.
- [ ] LOGOUT: Exit the game. (return to character managment)
- [ ] SETTINGS: Change your settings.

OTHER:

- [ ] HIDE: Hide from other players.
- [ ] SEARCH: Search for hidden objects.
- [ ] UNHIDE: Reveal yourself.
- [ ] USE: Use an object.

## Deployment

Deploying the server involves several steps:

1. Ensure you have Go 1.23 and Python 3.12 installed.
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
   go build ./ssh_server
   ./ssh_server
   ```

## Development

- `core/` directory contains the main game logic and types.
- `data/` directory contains the data files for the game.
- `database/` directory contains Python scripts for database management.
- `editor/` directory contains the editor for creating and editing game content.
- `registration/` directory contains the web registration page for new players.
- `scripts/` directory contains deployment and utility scripts.
- `ssh_server/` directory contains the main server implementation.

## License

This project is licensed under the Apache 2.0 License. See the LICENSE file for more details.
