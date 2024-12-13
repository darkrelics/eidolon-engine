package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"gopkg.in/yaml.v3"

	"github.com/robinje/multi-user-dungeon/core"
	"github.com/robinje/multi-user-dungeon/game"
	"github.com/robinje/multi-user-dungeon/server"
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

	CloudWatch, err := core.InitializeLogging(config)
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
			core.Logger.Error("Metrics collection failed", "error", err)
		}
	}()

	fmt.Println("Logger initialized.")

	fmt.Println("Initializing server...")

	Server, err := server.NewServer(ctx, config)

	if err != nil {
		fmt.Printf("Error initializing server: %v\n", err)
		os.Exit(1)
	}

	go func() {
		if err := server.RunServer(Server); err != nil {
			core.Logger.Error("Server error", "error", err)
		}
	}()

	fmt.Println("Server initialized.")

	fmt.Println("Initializing game...")

	Game, err := game.NewGame(ctx, config)

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)

}

// loadConfiguration reads the configuration file and unmarshals it into a Configuration struct.
func loadConfiguration(configFile string) (*core.Configuration, error) {
	var config core.Configuration

	data, err := os.ReadFile(configFile)
	if err != nil {
		return nil, fmt.Errorf("error reading config file '%s': %w", configFile, err)
	}

	err = yaml.Unmarshal(data, &config)
	if err != nil {
		return nil, fmt.Errorf("error unmarshalling config from '%s': %w", configFile, err)
	}

	return &config, nil
}

func shutdown(server *core.Server, game *core.Game) {
	const shutdownTimeout = 60 * time.Second
	_, cancel := context.WithTimeout(context.Background(), shutdownTimeout)
	defer cancel()

	core.Logger.Info("Initiating graceful shutdown...")

}
