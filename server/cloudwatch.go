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

	fmt.Println("New CloudWatch...Initalizing CloudWatch...")

	handlerCtx, cancel := context.WithCancel(ctx)

	awsConfig, err := config.LoadDefaultConfig(ctx,
		config.WithRegion(cfg.AWS.Region),
		config.WithRetryMode(aws.RetryModeStandard),
		config.WithRetryMaxAttempts(3),
	)
	if err != nil {
		fmt.Printf("Error loading AWS config: %v\n", err)
		cancel()
		return nil, fmt.Errorf("error loading AWS config: %w", err)
	}

	// Create CloudWatch Handler (JSON)
	loghandler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level:     parseLogLevel(cfg.Logging.LogLevel),
		AddSource: false,
	})

	//Create CloudWatch Handler

	handler := &CloudWatch{
		ctx:           handlerCtx,
		cancel:        cancel,
		logClient:     cloudwatchlogs.NewFromConfig(awsConfig),
		metricsClient: cloudwatch.NewFromConfig(awsConfig),
		logLevel:      cfg.Logging.LogLevel,
		logGroup:      cfg.Logging.LogGroup,
		logStream:     cfg.Logging.LogStream,
		namespace:     cfg.Logging.MetricNamespace,
		handlers:      []slog.Handler{loghandler},
		initialized:   false,
		interval:      time.Minute,
		sequenceToken: nil,
		metrics:       make(chan types.MetricDatum, 100),
	}

	// Set up global logger
	Logger = slog.New(loghandler)
	slog.SetDefault(Logger)

	return handler, nil
}

func (c *CloudWatch) Enabled(ctx context.Context, level slog.Level) bool {

	fmt.Println("CloudWatch Enabled...")

	return level >= parseLogLevel(c.logLevel)
}

func (c *CloudWatch) WithAttrs(attrs []slog.Attr) slog.Handler {

	fmt.Println("CloudWatch WithAttrs...")

	return c
}

func (c *CloudWatch) WithGroup(name string) slog.Handler {

	fmt.Println("CloudWatch WithGroup...")

	return c
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
