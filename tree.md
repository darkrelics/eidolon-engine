.
│ .gitignore
│ LICENSE
│ README.md
│ tree.md
│
├───.github
│ │ dependabot.yml
│ │
│ └───workflows
│ cloudformation-analysis.yml
│ codeql.yml
│ flutter-analysis.yml
│ go-auto-format.yml
│ javascript-auto-format.yml
│ pip-conflicts.yml
│ python-auto-format.yml
│
├───buildspec
│ registration.yml
│
├───cloudformation
│ cloudwatch.yml
│ codebuild.yml
│ cognito.yml
│ dynamo.yml
│
├───data
│ names.txt
│ obscenity.txt
│ test_archetypes.json
│ test_exits.json
│ test_exits_update.json
│ test_prototypes.json
│ test_rooms.json
│ test_rooms_update.json
│
├───database
│ create_item.py
│ data_loader.py
│ motd.py
│ Schema.md
│ viewer.py
│
├───editor
│ RoomEditor.ipynb
│
├───registration
│ │ .gitignore
│ │ analysis_options.yaml
│ │ pubspec.yaml
│ │ README.md
│ │
│ ├───lib
│ │ main.dart
│ │
│ ├───test
│ │ widget_test.dart
│ │
│ └───web
│ │ favicon.png
│ │ index.html
│ │ manifest.json
│ │  
│ └───icons
│ Icon-192.png
│ Icon-512.png
│ Icon-maskable-192.png
│ Icon-maskable-512.png
│
├───requirements
│ editor-requirements.txt
│ scripts-requirements.txt
│
├───scripts
│ deploy.py
│ list_processor.py
│
└───server
archtype.go
character-select.go
character.go
cognito.go
colors.go
combat.go
commands-combat.go
commands.go
config.template.yml
config.yml
configuration.go
database.go
DESIGN.md
game.go
go.mod
go.sum
go.work
go.work.sum
interface_ssh.go
item.go
logging.go
motd.go
player.go
room.go
server.go
server.key
start.go
types.go
utils.go
