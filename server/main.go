package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"
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

	go cloudWatch.Run(errorChannel)
	go game.Run(errorChannel)
	go server.Run(errorChannel)

	// Handle shutdown via signal or component error

	signalChannel := make(chan os.Signal, 1)
	signal.Notify(signalChannel, os.Interrupt, syscall.SIGTERM)

	select {
	case sig := <-signalChannel:
		fmt.Printf("Received signal: %v\n", sig)
	case err := <-errorChannel:
		if err != nil {
			fmt.Printf("Component error: %v\n", err)
		}
	}

	// Initiate graceful shutdown
	cancel()

	if err := shutdown(errorChannel, game, server, cloudWatch, "shutdown requested"); err != nil {
		fmt.Printf("Error during shutdown: %v\n", err)
		os.Exit(121)
	}

	os.Exit(0)
}

func shutdown(errorChan chan error, game *Game, server *Server, cloudWatch *CloudWatch, reason string) error {

	fmt.Printf("Shutting down server: %s\n", reason)

	if err := server.Stop(); err != nil {
		errorChan <- err
		return err
	}

	if err := game.Stop(); err != nil {
		errorChan <- err
		return err
	}

	if err := cloudWatch.Stop(); err != nil {
		errorChan <- err
		return err
	}

	return nil
}
