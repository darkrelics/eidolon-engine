package main

import (
	"context"
	"fmt"
	"os"
)

var CONFIGURATION_FILE string = "config.yml"

func main() {

	fmt.Println("Starting System...")

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	errorChannel := make(chan error, 3)

	fmt.Printf("Loading configuration from %s\n", CONFIGURATION_FILE)

	config, err := LoadConfiguration(CONFIGURATION_FILE)
	if err != nil {
		fmt.Printf("Error loading configuration: %v\n", err)
		os.Exit(125)
	}

	fmt.Println("Initializing logging...")
	cloudWatch, err := NewCloudWatch(ctx, config)
	if err != nil {
		fmt.Printf("Error initializing logging: %v\n", err)
		os.Exit(124)

		// Initialize graceful shutdown
		cancel()

		os.Exit(0)

	}

	fmt.Println("Starting Game Engine...")
	game, err := NewGame(ctx, config)
	if err != nil {
		fmt.Printf("Error initializing game engine: %v\n", err)
		os.Exit(123)
	}
}
