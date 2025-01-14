package main

import (
	"context"
	"fmt"
	"os"
)

var CONFIGURATION_FILE string = "config.yml"

func main() {

	// Initialize the system components

	fmt.Println("Starting System...")

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	errorChannel := make(chan error, 3)

	// Load configuration

	fmt.Printf("Loading configuration from %s\n", CONFIGURATION_FILE)

	config, err := LoadConfiguration(CONFIGURATION_FILE)
	if err != nil {
		fmt.Printf("Error loading configuration: %v\n", err)
		os.Exit(125)
	}

	// Initialize logging

	fmt.Println("Initializing logging...")
	cloudWatch, err := NewCloudWatch(ctx, config)
	if err != nil {
		fmt.Printf("Error initializing logging: %v\n", err)
		os.Exit(124)
	}

	// Initialize game engine

	fmt.Println("Starting Game Engine...")
	game, err := NewGame(ctx, config)
	if err != nil {
		fmt.Printf("Error initializing game engine: %v\n", err)
		os.Exit(123)
	}

	// Initialize server

	fmt.Println("Starting Server...")
	server, err := NewServer(ctx, config)
	if err != nil {
		fmt.Printf("Error initializing server: %v\n", err)
		os.Exit(122)
	}

	server.game = game

	// Associate server with cloudWatch

	cloudWatch.mutex.Lock()
	cloudWatch.server = server
	cloudWatch.mutex.Unlock()

	fmt.Println("Starting server components...")

	// Start components with error channels
}
