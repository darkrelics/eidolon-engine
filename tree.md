.
│   .gitignore
│   config.template.yml
│   config.yml
│   go.mod
│   go.sum
│   go.work
│   go.work.sum
│   LICENSE
│   README.md
│   Schema.md
│   start.go
│   tree.md
│
├───.github
│   │   dependabot.yml
│   │
│   └───workflows
│           cloudformation-analysis.yml
│           codeql.yml
│           flutter-analysis.yml
│           go-auto-format.yml
│           javascript-auto-format.yml
│           pip-conflicts.yml
│           python-auto-format.yml
│
│
├───buildspec
│       registration.yml
│
├───character
│       archtype.go
│       character.go
│       combat.go
│       commands-combat.go
│       commands.go
│       go.mod
│       go.sum
│
├───cloudformation
│       cloudwatch.yml
│       codebuild.yml
│       cognito.yml
│       dynamo.yml
│
├───core
│       colors.go
│       configuration.go
│       database.go
│       go.mod
│       go.sum
│       logging.go
│       motd.go
│       types.go
│       utils.go
│
├───data
│       names.txt
│       obscenity.txt
│       test_archetypes.json
│       test_exits.json
│       test_exits_update.json
│       test_prototypes.json
│       test_rooms.json
│       test_rooms_update.json
│
├───database
│       create_item.py
│       data_loader.py
│       motd.py
│       viewer.py
│
├───editor
│       RoomEditor.ipynb
│
├───game
│       game.go
│       go.mod
│       go.sum
│       item.go
│       room.go
│       utils.go
│
├───interface_ssh
│       channels.go
│       go.mod
│       go.sum
│       go.work
│       go.work.sum
│       server.key
│       ssh_server.go
│
├───player
│       character-select.go
│       cognito.go
│       go.mod
│       go.sum
│       go.work
│       player.go
│       sessions.go
│
├───registration
│   │   .gitignore
│   │   analysis_options.yaml
│   │   pubspec.yaml
│   │   README.md
│   │
│   ├───lib
│   │       main.dart
│   │
│   ├───test
│   │       widget_test.dart
│   │
│   └───web
│       │   favicon.png
│       │   index.html
│       │   manifest.json
│       │
│       └───icons
│               Icon-192.png
│               Icon-512.png
│               Icon-maskable-192.png
│               Icon-maskable-512.png
│
├───requirements
│       editor-requirements.txt
│       scripts-requirements.txt
│
├───scripts
│       deploy.py
│       list_processor.py
│
└───server
        go.mod
        go.sum
        go.work
        go.work.sum
        motd.go
        server.go