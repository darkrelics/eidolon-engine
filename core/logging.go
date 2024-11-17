package core

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"runtime"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch/types"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs"
	cwlogtypes "github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs/types"
	"github.com/aws/aws-xray-sdk-go/xray"
)

// Global variables
var (
	Logger *slog.Logger
)

func InitializeLogging(cfg *Configuration) error {
	// Determine the log level
	var level slog.Level
	switch cfg.Logging.LogLevel {
	case 10:
		level = slog.LevelDebug
	case 20:
		level = slog.LevelInfo
	case 30:
		level = slog.LevelWarn
	case 40:
		level = slog.LevelError
	default:
		level = slog.LevelInfo
	}

	// Initialize AWS SDK configuration
	awsCfg, err := config.LoadDefaultConfig(context.TODO(), config.WithRegion(cfg.Aws.Region))
	if err != nil {
		return fmt.Errorf("unable to load SDK config: %w", err)
	}

	// Create CloudWatch Logs client
	client := cloudwatchlogs.NewFromConfig(awsCfg)

	// Create CloudWatch handler
	cwHandler := NewCloudWatchHandler(client, cfg.Logging.LogGroup, cfg.Logging.LogStream)

	// Create a multi-writer handler that writes to both CloudWatch and stdout
	multiHandler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: level}).WithAttrs([]slog.Attr{
		slog.String("application", cfg.Logging.ApplicationName),
		slog.String("region", cfg.Aws.Region),
	})

	// Initialize the Logger with both handlers
	Logger = slog.New(NewMultiHandler(multiHandler, cwHandler))
	slog.SetDefault(Logger)

	return nil
}

// GetEnv retrieves environment variables or returns a default value if not set
func GetEnv(key, defaultValue string) string {
	if value, exists := os.LookupEnv(key); exists {
		return value
	}
	return defaultValue
}

func EnableXRay(cfg *Configuration) error {
	// Determine the log level
	var xrayLogLevel string
	switch cfg.Logging.LogLevel {
	case 10:
		xrayLogLevel = "debug"
	case 20:
		xrayLogLevel = "info"
	case 30:
		xrayLogLevel = "warn"
	case 40:
		xrayLogLevel = "error"
	default:
		xrayLogLevel = "info"
	}

	Logger.Info("Configuring AWS X-Ray", "logLevel", xrayLogLevel)

	err := xray.Configure(xray.Config{
		LogLevel: xrayLogLevel,
	})

	if err != nil {
		Logger.Error("Failed to configure AWS X-Ray", "error", err)
		return fmt.Errorf("failed to configure AWS X-Ray: %w", err)
	}

	Logger.Debug("AWS X-Ray successfully configured")

	return nil
}

func NewCloudWatchHandler(client *cloudwatchlogs.Client, logGroup, logStream string) *CloudWatchHandler {
	return &CloudWatchHandler{
		client:      client,
		logGroup:    logGroup,
		logStream:   logStream,
		mutex:       sync.RWMutex{},
		initialized: false,
	}
}

func (h *CloudWatchHandler) Enabled(ctx context.Context, level slog.Level) bool {
	return true
}

func (h *CloudWatchHandler) Handle(ctx context.Context, r slog.Record) error {
	if err := h.initializeLogStream(ctx); err != nil {
		// Log the error to stdout as a fallback
		fmt.Printf("Failed to initialize CloudWatch log stream: %v\n", err)
		return err
	}

	message := r.Message
	for _, attr := range h.attrs {
		message += fmt.Sprintf(" %s=%v", attr.Key, attr.Value)
	}
	r.Attrs(func(a slog.Attr) bool {
		message += fmt.Sprintf(" %s=%v", a.Key, a.Value)
		return true
	})

	input := &cloudwatchlogs.PutLogEventsInput{
		LogGroupName:  aws.String(h.logGroup),
		LogStreamName: aws.String(h.logStream),
		LogEvents: []cwlogtypes.InputLogEvent{
			{
				Message:   aws.String(message),
				Timestamp: aws.Int64(time.Now().UnixNano() / int64(time.Millisecond)),
			},
		},
	}

	// Implement retry logic
	maxRetries := 3
	for i := 0; i < maxRetries; i++ {
		_, err := h.client.PutLogEvents(ctx, input)
		if err == nil {
			return nil
		}
		if i == maxRetries-1 {
			// Log the error to stdout as a fallback
			fmt.Printf("Failed to write log to CloudWatch after %d retries: %v\n", maxRetries, err)
			return err
		}
		// Wait before retrying (you might want to implement exponential backoff here)
		time.Sleep(time.Second * time.Duration(i+1))
	}
	return fmt.Errorf("failed to write log to CloudWatch after %d retries", maxRetries)
}

func (h *CloudWatchHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	return &CloudWatchHandler{
		client:    h.client,
		logGroup:  h.logGroup,
		logStream: h.logStream,
		attrs:     append(h.attrs, attrs...),
	}
}

func (h *CloudWatchHandler) WithGroup(name string) slog.Handler {
	return h
}

func NewMultiHandler(handlers ...slog.Handler) *MultiHandler {
	return &MultiHandler{handlers: handlers}
}

func (h *MultiHandler) Enabled(ctx context.Context, level slog.Level) bool {
	for _, handler := range h.handlers {
		if handler.Enabled(ctx, level) {
			return true
		}
	}
	return false
}

func (h *MultiHandler) Handle(ctx context.Context, r slog.Record) error {
	for _, handler := range h.handlers {
		if err := handler.Handle(ctx, r); err != nil {
			return err
		}
	}
	return nil
}

func (h *MultiHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	newHandlers := make([]slog.Handler, len(h.handlers))
	for i, handler := range h.handlers {
		newHandlers[i] = handler.WithAttrs(attrs)
	}
	return NewMultiHandler(newHandlers...)
}

func (h *MultiHandler) WithGroup(name string) slog.Handler {
	newHandlers := make([]slog.Handler, len(h.handlers))
	for i, handler := range h.handlers {
		newHandlers[i] = handler.WithGroup(name)
	}
	return NewMultiHandler(newHandlers...)
}

// NewMetricsCollector creates and initializes a new MetricsCollector
func NewMetricsCollector(s *Server, interval time.Duration) (*MetricsCollector, error) {
	if s == nil {
		return nil, fmt.Errorf("server instance is nil")
	}
	if s.Config == nil {
		return nil, fmt.Errorf("server configuration is nil")
	}
	if s.Config.Aws.Region == "" {
		return nil, fmt.Errorf("AWS region configuration is missing")
	}
	if s.Config.Logging.MetricNamespace == "" {
		return nil, fmt.Errorf("metric namespace configuration is missing")
	}

	cfg, err := config.LoadDefaultConfig(context.Background(),
		config.WithRegion(s.Config.Aws.Region))
	if err != nil {
		return nil, fmt.Errorf("failed to load AWS SDK config: %w", err)
	}

	return &MetricsCollector{
		client:    cloudwatch.NewFromConfig(cfg),
		server:    s,
		interval:  interval,
		namespace: s.Config.Logging.MetricNamespace,
	}, nil
}

// collectMetrics gathers the current metrics
func (mc *MetricsCollector) collectMetrics() []types.MetricDatum {
	var m runtime.MemStats
	runtime.ReadMemStats(&m)

	return []types.MetricDatum{
		{
			MetricName: aws.String("PlayerCount"),
			Unit:       types.StandardUnitCount,
			Value:      aws.Float64(float64(mc.server.PlayerCount)),
		},
		{
			MetricName: aws.String("MemoryUsage"),
			Unit:       types.StandardUnitMegabytes,
			Value:      aws.Float64(float64(m.Alloc) / 1024 / 1024),
		},
		{
			MetricName: aws.String("RoutineCount"),
			Unit:       types.StandardUnitCount,
			Value:      aws.Float64(float64(runtime.NumGoroutine())),
		},
	}
}

// sendMetrics sends the collected metrics to CloudWatch
func (mc *MetricsCollector) sendMetrics(ctx context.Context) error {
	metrics := mc.collectMetrics()

	_, err := mc.client.PutMetricData(ctx, &cloudwatch.PutMetricDataInput{
		Namespace:  aws.String(mc.namespace),
		MetricData: metrics,
	})

	if err != nil {
		return fmt.Errorf("failed to send metrics to CloudWatch: %w", err)
	}

	// Log metric values for debugging
	Logger.Debug("Sent metrics to CloudWatch", "playerCount", *metrics[0].Value, "memoryUsageMB", *metrics[1].Value, "routineCount", *metrics[2].Value)

	return nil
}

// SendMetrics runs the metrics collection loop
func SendMetrics(ctx context.Context, s *Server, interval time.Duration) error {
	collector, err := NewMetricsCollector(s, interval)
	if err != nil {
		return fmt.Errorf("failed to initialize metrics collector: %w", err)
	}

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	// Send initial metrics
	if err := collector.sendMetrics(ctx); err != nil {
		Logger.Error("Failed to send initial metrics", "error", err)
	}

	for {
		select {
		case <-ctx.Done():
			Logger.Info("Stopping metrics collection due to context cancellation")
			return ctx.Err()

		case <-ticker.C:
			if err := collector.sendMetrics(ctx); err != nil {
				Logger.Error("Failed to send metrics", "error", err)
				// Continue running despite errors
			}
		}
	}
}

func (h *CloudWatchHandler) initializeLogStream(ctx context.Context) error {
	h.mutex.Lock()
	defer h.mutex.Unlock()

	if h.initialized {
		return nil
	}

	// Check if the log stream exists
	describeLogStreamsInput := &cloudwatchlogs.DescribeLogStreamsInput{
		LogGroupName:        aws.String(h.logGroup),
		LogStreamNamePrefix: aws.String(h.logStream),
	}

	output, err := h.client.DescribeLogStreams(ctx, describeLogStreamsInput)
	if err != nil {
		// If the error is not because the stream doesn't exist, return the error
		var notFoundErr *types.ResourceNotFoundException
		if !errors.As(err, &notFoundErr) {
			return fmt.Errorf("failed to describe log streams: %w", err)
		}
	}

	// If the log stream doesn't exist, create it
	if output == nil || len(output.LogStreams) == 0 {
		createLogStreamInput := &cloudwatchlogs.CreateLogStreamInput{
			LogGroupName:  aws.String(h.logGroup),
			LogStreamName: aws.String(h.logStream),
		}

		_, err = h.client.CreateLogStream(ctx, createLogStreamInput)
		if err != nil {
			return fmt.Errorf("failed to create log stream: %w", err)
		}
	}

	h.initialized = true
	return nil
}
