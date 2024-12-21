package main

import (
	"context"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"
)

type application struct {
	server     *Server
	game       *Game
	logger     *slog.Logger
	cloudWatch *CloudWatchHandler
	errChan    chan error
}

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

	cloudWatch, err := InitializeLogging(config)
	if err != nil {
		fmt.Printf("Error initializing logging: %v\n", err)
		os.Exit(1)
	}

	if err = cloudWatch.EnableXRay(); err != nil {
		Logger.Error("Error enabling X-Ray", "error", err)
		os.Exit(1)
	}

	app := &application{
		cloudWatch: cloudWatch,
		errChan:    make(chan error, 2),
		logger:     Logger,
	}

	if err = app.initialize(ctx, config); err != nil {
		Logger.Error("Initialization error", "error", err)
		os.Exit(1)
	}

	if err = app.run(ctx); err != nil {
		Logger.Error("Runtime error", "error", err)
		os.Exit(1)
	}
}

func (app *application) initialize(ctx context.Context, config *Configuration) error {

	game, err := NewGame(ctx, config)
	if err != nil {
		return fmt.Errorf("game init error: %w", err)
	}
	app.game = game

	server, err := NewServer(ctx, config)
	if err != nil {
		return fmt.Errorf("server init error: %w", err)
	}
	app.server = server

	server.Game = game

	return nil
}

func (app *application) run(ctx context.Context) error {
	go app.runMetrics(ctx)
	go app.runGame(ctx)
	go app.runServer(ctx)

	return app.handleSignals(ctx)
}

func (app *application) runMetrics(ctx context.Context) {
	if err := app.cloudWatch.SendMetrics(ctx, time.Minute); err != nil {
		app.logger.Error("metrics collection failed", "error", err)
	}
}

func (app *application) runServer(ctx context.Context) {
	if err := app.server.Run(); err != nil {
		app.errChan <- fmt.Errorf("server error: %w", err)
	}
}

func (app *application) runGame(ctx context.Context) {
	if err := app.game.Run(); err != nil {
		app.errChan <- fmt.Errorf("game error: %w", err)
	}
}

func (app *application) handleSignals(ctx context.Context) error {
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	select {
	case sig := <-sigChan:
		return app.shutdown(ctx, fmt.Sprintf("received signal: %v", sig))
	case err := <-app.errChan:
		return app.shutdown(ctx, err.Error())
	}
}

func (app *application) shutdown(ctx context.Context, reason string) error {
	shutdownCtx, cancel := context.WithTimeout(ctx, 60*time.Second)
	defer cancel()

	app.logger.Info("initiating shutdown", "reason", reason)

	if err := app.game.Stop(); err != nil {
		app.logger.Error("game shutdown error", "error", err)
	}

	if err := app.server.Stop(shutdownCtx); err != nil {
		return fmt.Errorf("server shutdown error: %w", err)
	}

	return nil
}
