module character

go 1.23

replace github.com/robinje/multi-user-dungeon/core => ../core

replace github.com/robinje/multi-user-dungeon/game => ../game

replace github.com/robinje/multi-user-dungeon/interface_ssh => ../interface_ssh

replace github.com/robinje/multi-user-dungeon/player => ../player

replace github.com/robinje/multi-user-dungeon/server => ../server

require (
	github.com/aws/aws-sdk-go v1.54.15
	github.com/bits-and-blooms/bloom/v3 v3.7.0
	github.com/google/uuid v1.6.0
)

require (
	github.com/bits-and-blooms/bitset v1.14.3 // indirect
	github.com/davecgh/go-spew v1.1.1 // indirect
	github.com/jmespath/go-jmespath v0.4.0 // indirect
)
