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
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

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

	errChan := make(chan error, 3)

	game, server, err := initialize(ctx, config)
	if err != nil {
		Logger.Error("Initialization error", "error", err)
		os.Exit(1)
	}

	go runMetrics(ctx, cloudWatch, errChan)
	go runGame(ctx, game, errChan)
	go runServer(ctx, server, errChan)

	if err = handleSignals(ctx, game, server, errChan); err != nil {
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

	server.Game = game
	return game, server, nil
}

func runMetrics(ctx context.Context, cloudWatch *CloudWatchHandler, errChan chan error) {
	if err := cloudWatch.SendMetrics(ctx, time.Minute); err != nil {
		Logger.Error("metrics collection failed", "error", err)
		errChan <- fmt.Errorf("metrics collection failed: %w", err)
	}
}

func runServer(ctx context.Context, server *Server, errChan chan error) {
	if err := server.Run(); err != nil {
		Logger.Error("server error", "error", err)
		errChan <- fmt.Errorf("server error: %w", err)
	}
}

func runGame(ctx context.Context, game *Game, errChan chan error) {
	if err := game.Run(); err != nil {
		Logger.Error("game error", "error", err)
		errChan <- fmt.Errorf("game error: %w", err)
	}
}

func handleSignals(ctx context.Context, game *Game, server *Server, errChan chan error) error {
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	select {
	case sig := <-sigChan:
		return shutdown(ctx, game, server, fmt.Sprintf("received signal: %v", sig))
	case err := <-errChan:
		return shutdown(ctx, game, server, err.Error())
	}
}

func shutdown(ctx context.Context, game *Game, server *Server, reason string) error {
	shutdownCtx, cancel := context.WithTimeout(ctx, 60*time.Second)
	defer cancel()

	Logger.Info("initiating shutdown", "reason", reason)

	if err := game.Stop(); err != nil {
		Logger.Error("game shutdown error", "error", err)
	}

	if err := server.Stop(shutdownCtx); err != nil {
		return fmt.Errorf("server shutdown error: %w", err)
	}

	return nil
}
