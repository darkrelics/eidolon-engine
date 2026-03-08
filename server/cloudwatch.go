/*
Eidolon Engine

Copyright 2024-2026 Jason E. Robinson

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
		// Can't use Logger here as it's not initialized yet
		fmt.Printf("Error loading AWS config: %v\n", err)
		cancel()
		return nil, fmt.Errorf("error loading AWS config: %w", err)
	}

	// Test AWS credentials by attempting to describe log groups
	// This works with both IAM users and EC2 instance profiles
	testClient := cloudwatchlogs.NewFromConfig(awsConfig)
	_, err = testClient.DescribeLogGroups(ctx, &cloudwatchlogs.DescribeLogGroupsInput{
		Limit: aws.Int32(1),
	})
	if err != nil {
		// Can't use Logger here as it's not initialized yet
		fmt.Printf("Failed to verify AWS credentials: %v\n", err)
		cancel()
		return nil, fmt.Errorf("insufficient AWS credentials or permissions: %w", err)
	}

	// Temporary logger needed before CloudWatch initialization
	tempHandler := slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{
		Level: parseLogLevel(cfg.Logging.LogLevel),
	})
	tempLogger := slog.New(tempHandler)

	// Global logger assignment enables immediate logging
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

	// CloudWatch handler routes logs to AWS
	cwHandler := NewCloudWatchHandler(cloudWatch, parseLogLevel(cfg.Logging.LogLevel), true)

	// Final logger replaces temporary console logger
	finalLogger := slog.New(cwHandler)
	Logger = finalLogger
	slog.SetDefault(finalLogger)

	// Store handlers
	cloudWatch.handlers = []slog.Handler{cwHandler}

	return cloudWatch, nil
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
	case <-time.After(3 * time.Second):
		Logger.Error("CloudWatch: CloudWatch shutdown timed out", "error", "timeout")
		return fmt.Errorf("cloudwatch shutdown timeout")
	}
}
