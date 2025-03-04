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
	"log/slog"
	"os"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch/types"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs"
)

type CloudWatch struct {
	ctx           context.Context
	cancel        context.CancelFunc
	logClient     *cloudwatchlogs.Client
	metricsClient *cloudwatch.Client
	logLevel      int
	logGroup      string
	logStream     string
	namespace     string
	handlers      []slog.Handler
	sequenceToken *string
	mutex         sync.RWMutex
	initialized   bool
	interval      time.Duration
	server        *Server
	metrics       chan types.MetricDatum
}

func NewCloudWatch(ctx context.Context, cfg *Configuration) (*CloudWatch, error) {
	fmt.Println("New CloudWatch...Initializing CloudWatch...")

	handlerCtx, cancel := context.WithCancel(ctx)

	awsConfig, err := config.LoadDefaultConfig(ctx,
		config.WithRegion(cfg.AWS.Region),
		config.WithRetryMode(aws.RetryModeStandard),
		config.WithRetryMaxAttempts(3),
	)
	if err != nil {
		Logger.Info("Error loading AWS config", "error", err)
		cancel()
		return nil, fmt.Errorf("error loading AWS config: %w", err)
	}

	// Create a temporary console logger for bootstrapping
	tempHandler := slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{
		Level: parseLogLevel(cfg.Logging.LogLevel),
	})
	tempLogger := slog.New(tempHandler)

	// Set temporary logger
	Logger = tempLogger
	slog.SetDefault(tempLogger)

	// Create CloudWatch instance
	cloudWatch := &CloudWatch{
		ctx:           handlerCtx,
		cancel:        cancel,
		logClient:     cloudwatchlogs.NewFromConfig(awsConfig),
		metricsClient: cloudwatch.NewFromConfig(awsConfig),
		logLevel:      cfg.Logging.LogLevel,
		logGroup:      cfg.Logging.LogGroup,
		logStream:     cfg.Logging.LogStream,
		namespace:     cfg.Logging.MetricNamespace,
		initialized:   false,
		interval:      time.Minute,
		sequenceToken: nil,
		metrics:       make(chan types.MetricDatum, 100),
	}

	// Create the CloudWatch handler that implements slog.Handler
	cwHandler := NewCloudWatchHandler(cloudWatch, parseLogLevel(cfg.Logging.LogLevel), true)

	// Create and set the final logger
	finalLogger := slog.New(cwHandler)
	Logger = finalLogger
	slog.SetDefault(finalLogger)

	// Store handlers
	cloudWatch.handlers = []slog.Handler{cwHandler}

	return cloudWatch, nil
}

func (c *CloudWatch) Enabled(ctx context.Context, level slog.Level) bool {
	// This function is kept for backward compatibility but no longer implements
	// the slog.Handler interface directly
	return level >= parseLogLevel(c.logLevel)
}

func (c *CloudWatch) WithAttrs(attrs []slog.Attr) slog.Handler {
	// This function is kept for backward compatibility but no longer implements
	// the slog.Handler interface directly
	return c
}

func (c *CloudWatch) WithGroup(name string) slog.Handler {
	// This function is kept for backward compatibility but no longer implements
	// the slog.Handler interface directly
	return c
}

func (c *CloudWatch) Handle(ctx context.Context, r slog.Record) error {
	// This function is kept for backward compatibility but no longer implements
	// the slog.Handler interface directly
	return nil
}

// Stop gracefully shuts down the CloudWatch component.
func (c *CloudWatch) Stop() error {
	Logger.Info("CloudWatch: Stopping CloudWatch...")
	defer Logger.Info("CloudWatch: CloudWatch stopped")

	// Signal the Run goroutine to stop
	c.cancel()

	// Give the Run goroutine some time to exit and flush any remaining metrics/logs
	select {
	case <-c.ctx.Done():
		Logger.Info("CloudWatch: CloudWatch shutdown complete")
		return nil
	case <-time.After(10 * time.Second): // Example timeout
		Logger.Error("CloudWatch: CloudWatch shutdown timed out", "error", "timeout")
		return fmt.Errorf("cloudwatch shutdown timeout")
	}
}
