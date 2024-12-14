package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {

	// Create the global context.

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	fmt.Println("Loading configuration...")

	configFile := flag.String("config", "config.yml", "Configuration file")
	flag.Parse()

	config, err := loadConfiguration(*configFile)
	if err != nil {
		fmt.Printf("Error loading configuration: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("Configuration loaded.")

	fmt.Println("Initializing logger...")

	CloudWatch, err := InitializeLogging(config)
	if err != nil {
		fmt.Printf("Error initializing logging: %v\n", err)
		os.Exit(1)
	}

	if CloudWatch == nil {
		fmt.Printf("CloudWatch handler not initialized")
		os.Exit(1)
	}

	err = CloudWatch.EnableXRay()
	if err != nil {
		fmt.Printf("Error enabling X-Ray: %v\n", err)
		os.Exit(1)
	}

	// Start metrics collection in a goroutine
	go func() {
		if err := CloudWatch.SendMetrics(ctx, 1*time.Minute); err != nil {
			Logger.Error("Metrics collection failed", "error", err)
		}
	}()

	fmt.Println("Logger initialized.")

	fmt.Println("Initializing server...")

	Server, err := NewServer(ctx, config)

	if err != nil {
		fmt.Printf("Error initializing server: %v\n", err)
		os.Exit(1)
	}

	go func() {
		if err := Server.Run(); err != nil {
			Logger.Error("Server error", "error", err)
			ctx.Done()
		}
	}()

	fmt.Println("Server initialized.")

	fmt.Println("Initializing game...")

	Game, err := NewGame(ctx, config)

	if err != nil {
		fmt.Printf("Error initializing game: %v\n", err)
		os.Exit(1)
	}

	go func() {
		if err := Game.Run(); err != nil {
			Logger.Error("Game error", "error", err)
			ctx.Done()
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)

	<-stop

	shutdown(Server, Game)

}

func shutdown(server *Server, game *Game) {
	const shutdownTimeout = 60 * time.Second
	_, cancel := context.WithTimeout(context.Background(), shutdownTimeout)
	defer cancel()

	Logger.Info("Initiating graceful shutdown...")

	game.Stop()

	server.Context.Done()

}
