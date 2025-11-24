/*
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

*/

package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"
)

var CONFIGURATION_FILE string = "../config.yml"

func main() {

	fmt.Println("Main - Starting System...")

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Use a larger buffer to reduce blocking risk
	errorChannel := make(chan error, 100)

	// Start error handler goroutine
	errorHandlerDone := make(chan struct{})
	go handleErrors(ctx, errorChannel, errorHandlerDone)

	fmt.Printf("Main - Loading configuration from %s\n", CONFIGURATION_FILE)

	config, err := LoadConfiguration(CONFIGURATION_FILE)
	if err != nil {
		fmt.Printf("Main - Error loading configuration: %v\n", err)
		os.Exit(125)
	}

	fmt.Println("Main - Initializing logging...")
	cloudWatch, err := NewCloudWatch(ctx, config)
	if err != nil {
		fmt.Printf("Main - Error initializing logging: %v\n", err)
		os.Exit(124)
	}
	CloudWatchMetrics = cloudWatch

	Logger.Info("Main - Starting Game Engine...")
	game, err := NewGame(ctx, config, cloudWatch)
	if err != nil {
		Logger.Error("Main - Error initializing game engine", "error", err)
		os.Exit(123)
	}

	Logger.Info("Main - Starting Server...")
	server, err := NewServer(ctx, config, cloudWatch)
	if err != nil {
		Logger.Error("Main - Error initializing server", "error", err)
		os.Exit(122)
	}

	server.game = game
	cloudWatch.server = server

	Logger.Info("Main - Starting server components...")

	go func() {
		if err := cloudWatch.Run(errorChannel); err != nil {
			Logger.Error("CloudWatch: Unexpected error", "error", err)
			errorChannel <- err
		}
	}()

	go func() {
		if err := game.Run(errorChannel); err != nil {
			Logger.Error("Game: Unexpected error", "error", err)
			errorChannel <- err
		}
	}()

	go func() {
		if err := server.Run(errorChannel); err != nil {
			Logger.Error("Server: Unexpected error", "error", err)
			errorChannel <- err
		}
	}()

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
	}

	// Channel closure signals error handler termination
	close(errorChannel)
	select {
	case <-errorHandlerDone:
		Logger.Info("Error handler stopped")
	case <-time.After(5 * time.Second):
		Logger.Warn("Timeout waiting for error handler to stop")
	}

	if shutdownErr != nil {
		os.Exit(121)
	}

	os.Exit(0)
}

// handleErrors processes errors from components in a dedicated goroutine
func handleErrors(ctx context.Context, errorChan <-chan error, done chan<- struct{}) {
	defer close(done)

	RunWithPanicRecovery("error-handler", func() {
		errorCount := 0
		lastErrorTime := time.Now()

		for {
			select {
			case <-ctx.Done():
				Logger.Info("Error handler shutting down")
				return
			case err, ok := <-errorChan:
				if !ok {
					// Channel closed
					return
				}
				if err != nil {
					errorCount++
					Logger.Error("Component error",
						"error", err,
						"errorCount", errorCount)

					// Simple circuit breaker: if too many errors in short time
					if time.Since(lastErrorTime) < time.Second && errorCount > 10 {
						Logger.Error("Too many errors in short period, circuit breaker triggered",
							"errorCount", errorCount,
							"duration", time.Since(lastErrorTime))
					}

					if errorCount == 1 {
						lastErrorTime = time.Now()
					}
				}
			}
		}
	})
}

func shutdown(errorChan chan error, game *Game, server *Server, cloudWatch *CloudWatch) error {
	Logger.Info("Main - Shutting down system")

	var shutdownErr error

	// Stop components in reverse order
	if err := server.Stop(); err != nil {
		Logger.Error("Error stopping server", "error", err)
		shutdownErr = err
	}

	if err := game.Stop(); err != nil {
		Logger.Error("Error stopping game engine", "error", err)
		if shutdownErr == nil {
			shutdownErr = err
		}
	}

	if err := cloudWatch.Stop(); err != nil {
		Logger.Error("Error stopping CloudWatch", "error", err)
		if shutdownErr == nil {
			shutdownErr = err
		}
	}

	// Try to drain the error channel with a timeout
	drainTimer := time.NewTimer(2 * time.Second)
	defer drainTimer.Stop()

	select {
	case err := <-errorChan:
		if err != nil && shutdownErr == nil {
			Logger.Error("Error during component shutdown", "error", err)
			shutdownErr = err
		}
	case <-drainTimer.C:
		// Timeout waiting for error channel
	}

	return shutdownErr
}
