/*
Eidolon Engine

Copyright 2024-2025 Jason Robinson

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

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

	fmt.Println("Main - Starting System...")

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	errorChannel := make(chan error, 3)

	// Load configuration

	fmt.Printf("Main - Loading configuration from %s\n", CONFIGURATION_FILE)

	config, err := LoadConfiguration(CONFIGURATION_FILE)
	if err != nil {
		fmt.Printf("Main - Error loading configuration: %v\n", err)
		os.Exit(125)
	}

	// Initialize logging

	fmt.Println("Main - Initializing logging...")
	cloudWatch, err := NewCloudWatch(ctx, config)
	if err != nil {
		fmt.Printf("Main - Error initializing logging: %v\n", err)
		os.Exit(124)
	}

	// Initialize game engine

	Logger.Info("Main - Starting Game Engine...")
	game, err := NewGame(ctx, config)
	if err != nil {
		Logger.Error("Main - Error initializing game engine", "error", err)
		os.Exit(123)
	}

	// Initialize server

	Logger.Info("Main - Starting Server...")
	server, err := NewServer(ctx, config)
	if err != nil {
		Logger.Error("Main - Error initializing server", "error", err)
		os.Exit(122)
	}

	server.game = game
	cloudWatch.server = server

	Logger.Info("Main - Starting server components...")

	// Start components with error channels

	go cloudWatch.Run(errorChannel)
	go game.Run(errorChannel)
	go server.Run(errorChannel)

	// Handle shutdown via signal or component error

	signalChannel := make(chan os.Signal, 1)
	signal.Notify(signalChannel, os.Interrupt, syscall.SIGTERM)

	select {
	case sig := <-signalChannel:
		Logger.Info("Main: Received signal", "signal", sig)
	case err := <-errorChannel:
		if err != nil {
			Logger.Error("Main: Component error", "error", err)
			// Attempt to drain the error channel
			select {
			case err2 := <-errorChannel:
				Logger.Error("Main: Additional Component error", "error", err2)
			default:
				break // No more errors in the channel
			}
		}
	}

	// Initiate graceful shutdown
	cancel()

	shutdownErr := shutdown(errorChannel, game, server, cloudWatch)
	if shutdownErr != nil {
		Logger.Error("Main: Error during shutdown", "error", shutdownErr)
		os.Exit(121)
	}

	os.Exit(0)
}

func shutdown(errorChan chan error, game *Game, server *Server, cloudWatch *CloudWatch) error {

	// TODO: handle error channel

	Logger.Info("Main - Shutting down system")

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

	select {
	case err := <-errorChan:
		Logger.Error("Main: Error during shutdown", "error", err)
		return err
	default:
		break
	}

	return nil
}
