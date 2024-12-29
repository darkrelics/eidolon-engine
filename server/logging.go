package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch/types"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs"
)

var Logger *slog.Logger

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
}

func NewCloudWatch(ctx context.Context, cfg *Configuration) (*CloudWatch, error) {
	handlerCtx, cancel := context.WithCancel(ctx)

	fmt.Println("Creating console handler...")

	awsConfig, err := config.LoadDefaultConfig(ctx, config.WithRegion(cfg.aws.region))
	if err != nil {
		fmt.Printf("Error loading AWS config: %v\n", err)
		return nil, fmt.Errorf("error loading AWS config: %w", err)

	}

	//Create Console Hander

	consoleHandler := slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{
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
		handlers:      []slog.Handler{consoleHandler},
		initialized:   false,
		interval:      time.Minute,
	}

	return handler, nil
}

func parseLogLevel(level int) slog.Level {
	switch level {
	case 10:
		return slog.LevelDebug
	case 20:
		return slog.LevelInfo
	case 30:
		return slog.LevelWarn
	case 40:
		return slog.LevelError
	default:
		return slog.LevelInfo
	}
}

func (c *CloudWatch) initLogStream() error {

	if c.initialized {
		return nil
	}

	c.mutex.Lock()
	defer c.mutex.Unlock()

	// Describe the Log Stream
	_, err := c.logClient.DescribeLogStreams(c.ctx, &cloudwatchlogs.DescribeLogStreamsInput{
		LogGroupName:        aws.String(c.logGroup),
		LogStreamNamePrefix: aws.String(c.logStream),
	})

	if err != nil {
		if strings.Contains(err.Error(), "ResourceNotFoundException") {
			// Create the log group
			_, err = c.logClient.CreateLogStream(c.ctx, &cloudwatchlogs.CreateLogStreamInput{
				LogGroupName:  aws.String(c.logGroup),
				LogStreamName: aws.String(c.logStream),
			})
			if err != nil && !strings.Contains(err.Error(), "ResourceAlreadyExistsException") {
				return fmt.Errorf("create log stream: %w", err)
			}
		} else {
			return fmt.Errorf("error describing log stream: %w", err)
		}

	}

	c.initialized = true

	return nil
}

func (c *CloudWatch) collectMetrics() []types.MetricDatum {

	var m runtime.MemStats

	runtime.ReadMemStats(&m)

	metrics := []types.MetricDatum{
		{
			MetricName: aws.String("Memory Usage"),
			Unit:       types.StandardUnitMegabytes,
			Value:      aws.Float64(float64(m.Alloc) / 1024 / 1024),
		},
		{
			MetricName: aws.String("Go Routines"),
			Unit:       types.StandardUnitCount,
			Value:      aws.Float64(float64(runtime.NumGoroutine())),
		},
	}

	return metrics
}

func (c *CloudWatch) sendMetrics() error {

	metrics := c.collectMetrics()

	_, err := c.metricsClient.PutMetricData(c.ctx, &cloudwatch.PutMetricDataInput{
		Namespace:  aws.String(c.namespace),
		MetricData: metrics,
	})

	return err
}

func (c *CloudWatch) Run() error {

	if !c.initialized {
		if err := c.initLogStream(); err != nil {
			return fmt.Errorf("error initializing log stream: %w", err)
		}
	}

	ticker := time.NewTicker(c.interval)
	defer ticker.Stop()

	for {
		select {
		case <-c.ctx.Done():
			return nil
		case <-ticker.C:
			if err := c.sendMetrics(); err != nil {
				Logger.Error("Error sending metrics", "error", err)
			}
		}
	}
}

func (c *CloudWatch) Stop() error {
	c.cancel()
	return nil
}
