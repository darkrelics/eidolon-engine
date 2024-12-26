package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
)

func main() {
	fmt.Println("Starting server...")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	errChan := make(chan error, 3)

	configFile := flag.String("config", "config.yml", "Configuration file")
	flag.Parse()

	fmt.Printf("Loading configuration from %s\n", *configFile)
	config, err := loadConfiguration(*configFile)
	if err != nil {
		fmt.Printf("Error loading configuration: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("Initializing logging...")
	cloudWatch, err := NewLogHandler(ctx, config)
	if err != nil {
		fmt.Printf("Error initializing logging: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("Start initializing server...")
	game, server, err := initialize(ctx, config)
	if err != nil {
		fmt.Printf("Initialization error: %v\n", err)
		if cerr := cloudWatch.Stop(); cerr != nil {
			fmt.Printf("Error stopping cloudwatch during cleanup: %v\n", cerr)
		}
		os.Exit(1)
	}

	cloudWatch.mutex.Lock()
	cloudWatch.server = server
	cloudWatch.mutex.Unlock()

	fmt.Println("Starting server components...")

	// Start components with error channels
	go func() { errChan <- cloudWatch.Run() }()
	go func() { errChan <- game.Run() }()
	go func() { errChan <- server.Run() }()

	// Handle shutdown via signal or component error
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	select {
	case sig := <-sigChan:
		fmt.Printf("Received signal: %v\n", sig)
	case err := <-errChan:
		if err != nil {
			fmt.Printf("Component error: %v\n", err)
		}
	}

	// Initiate graceful shutdown
	cancel()
	if err := shutdown(game, server, cloudWatch, "shutdown requested"); err != nil {
		fmt.Printf("Error during shutdown: %v\n", err)
		os.Exit(1)
	}

	os.Exit(0)
}

func initialize(ctx context.Context, config *Configuration) (*Game, *Server, error) {
	game, err := NewGame(ctx, config)
	if err != nil {
		return nil, nil, fmt.Errorf("game init error: %w", err)
	}

	server, err := NewServer(ctx, config)
	if err != nil {
		// Clean up game resources since server failed
		if cerr := game.Stop(); cerr != nil {
			return nil, nil, fmt.Errorf("server init error: %w, game cleanup error: %v", err, cerr)
		}
		return nil, nil, fmt.Errorf("server init error: %w", err)
	}

	server.game = game
	return game, server, nil
}

func runMetrics(cloudWatch *CloudWatchHandler, errChan chan error) {
	if err := cloudWatch.Run(); err != nil {
		Logger.Error("metrics collection failed", "error", err)
		errChan <- fmt.Errorf("metrics collection failed: %w", err)
	}
}

func runServer(server *Server, errChan chan error) {
	if err := server.Run(); err != nil {
		Logger.Error("server error", "error", err)
		errChan <- fmt.Errorf("server error: %w", err)
	}
}

func runGame(game *Game, errChan chan error) {
	if err := game.Run(); err != nil {
		Logger.Error("game error", "error", err)
		errChan <- fmt.Errorf("game error: %w", err)
	}
}

func handleSignals(game *Game, server *Server, cloudWatch *CloudWatchHandler, errChan chan error) error {
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	select {
	case sig := <-sigChan:
		return shutdown(game, server, cloudWatch, fmt.Sprintf("received signal: %v", sig))
	case err := <-errChan:
		return shutdown(game, server, cloudWatch, err.Error())
	}
}

func shutdown(game *Game, server *Server, cloudWatch *CloudWatchHandler, reason string) error {
	Logger.Info("initiating shutdown", "reason", reason)

	var err error = nil

	if err := server.Stop(); err != nil {
		Logger.Error("server shutdown error", "error", err)
	}

	if err := game.Stop(); err != nil {
		Logger.Error("game shutdown error", "error", err)
	}

	if err := cloudWatch.Stop(); err != nil {
		Logger.Error("logging shutdown error", "error", err)
	}

	return err
}
