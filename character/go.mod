module github.com/robinje/multi-user-dungeon/character

go 1.23

replace github.com/robinje/multi-user-dungeon/core => ../core

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
