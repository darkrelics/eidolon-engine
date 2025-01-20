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

	fmt.Println("Creating console handler...")

	handlerCtx, cancel := context.WithCancel(ctx)

	awsConfig, err := config.LoadDefaultConfig(ctx,
		config.WithRegion(cfg.aws.region),
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
		Level: parseLogLevel(cfg.logging.logLevel),
	})

	//Create CloudWatch Handler

	handler := &CloudWatch{
		ctx:           handlerCtx,
		cancel:        cancel,
		logClient:     cloudwatchlogs.NewFromConfig(awsConfig),
		metricsClient: cloudwatch.NewFromConfig(awsConfig),
		logGroup:      cfg.logging.logGroup,
		logStream:     cfg.logging.logStream,
		namespace:     cfg.logging.namespace,
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
