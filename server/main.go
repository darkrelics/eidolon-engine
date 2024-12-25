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
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	errChan := make(chan error, 3)

	configFile := flag.String("config", "config.yml", "Configuration file")
	flag.Parse()

	config, err := loadConfiguration(*configFile)
	if err != nil {
		fmt.Printf("Error loading configuration: %v\n", err)
		os.Exit(1)
	}

	cloudWatch, err := NewLogHandler(ctx, config)
	if err != nil {
		fmt.Printf("Error initializing logging: %v\n", err)
		os.Exit(1)
	}

	game, server, err := initialize(ctx, config)
	if err != nil {
		Logger.Error("Initialization error", "error", err)
		os.Exit(1)
	}

	if server != nil {
		cloudWatch.mutex.Lock()
		cloudWatch.server = server
		cloudWatch.mutex.Unlock()
	}

	go runMetrics(cloudWatch, errChan)
	go runGame(game, errChan)
	go runServer(server, errChan)

	if err = handleSignals(game, server, cloudWatch, errChan); err != nil {
		Logger.Error("Runtime error", "error", err)
		os.Exit(1)
	}
}

func initialize(ctx context.Context, config *Configuration) (*Game, *Server, error) {
	game, err := NewGame(ctx, config)
	if err != nil {
		return nil, nil, fmt.Errorf("game init error: %w", err)
	}

	server, err := NewServer(ctx, config)
	if err != nil {
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
