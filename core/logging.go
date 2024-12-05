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

var Logger *slog.Logger

func NewCloudWatchHandler(logsClient *cloudwatchlogs.Client, metricsClient *cloudwatch.Client, level int, logGroup, logStream, namespace string, handlers []slog.Handler) *CloudWatchHandler {
	return &CloudWatchHandler{
		logsClient:    logsClient,
		metricsClient: metricsClient,
		logLevel:      level,
		logGroup:      logGroup,
		logStream:     logStream,
		namespace:     namespace,
		handlers:      handlers,
		mutex:         sync.RWMutex{},
		initialized:   false,
	}
}

func InitializeLogging(configuration *Configuration) (*CloudWatchHandler, error) {
	var level slog.Level
	switch configuration.Logging.LogLevel {
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

	awsCfg, err := config.LoadDefaultConfig(context.TODO(), config.WithRegion(configuration.Aws.Region))
	if err != nil {
		return nil, fmt.Errorf("unable to load SDK config: %w", err)
	}

	logsClient := cloudwatchlogs.NewFromConfig(awsCfg)
	metricsClient := cloudwatch.NewFromConfig(awsCfg)

	stdoutHandler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: level}).WithAttrs([]slog.Attr{
		slog.String("application", configuration.Logging.ApplicationName),
		slog.String("region", configuration.Aws.Region),
	})

	cwHandler := NewCloudWatchHandler(
		logsClient,
		metricsClient,
		configuration.Logging.LogLevel,
		configuration.Logging.LogGroup,
		configuration.Logging.LogStream,
		configuration.Logging.MetricNamespace,
		[]slog.Handler{stdoutHandler},
	)

	Logger = slog.New(cwHandler)
	slog.SetDefault(Logger)

	return cwHandler, nil
}

func GetEnv(key, defaultValue string) string {
	if value, exists := os.LookupEnv(key); exists {
		return value
	}
	return defaultValue
}

func (h *CloudWatchHandler) EnableXRay() error {
	var xrayLogLevel string
	switch h.logLevel {
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

	if err := xray.Configure(xray.Config{LogLevel: xrayLogLevel}); err != nil {
		Logger.Error("Failed to configure AWS X-Ray", "error", err)
		return fmt.Errorf("failed to configure AWS X-Ray: %w", err)
	}

	Logger.Debug("AWS X-Ray successfully configured")
	return nil
}

func (h *CloudWatchHandler) Enabled(ctx context.Context, level slog.Level) bool {
	for _, handler := range h.handlers {
		if handler.Enabled(ctx, level) {
			return true
		}
	}
	return level >= slog.Level(h.logLevel)
}

func (h *CloudWatchHandler) Handle(ctx context.Context, r slog.Record) error {
	if err := h.initializeLogStream(ctx); err != nil {
		return fmt.Errorf("failed to initialize log stream: %w", err)
	}

	message := h.formatMessage(r)
	input := &cloudwatchlogs.PutLogEventsInput{
		LogGroupName:  aws.String(h.logGroup),
		LogStreamName: aws.String(h.logStream),
		LogEvents: []cwlogtypes.InputLogEvent{{
			Message:   aws.String(message),
			Timestamp: aws.Int64(time.Now().UnixNano() / int64(time.Millisecond)),
		}},
	}

	if err := h.putLogsWithRetry(ctx, input); err != nil {
		return fmt.Errorf("failed to put logs: %w", err)
	}

	for _, handler := range h.handlers {
		if err := handler.Handle(ctx, r); err != nil {
			return err
		}
	}
	return nil
}

func (h *CloudWatchHandler) formatMessage(r slog.Record) string {
	message := r.Message
	for _, attr := range h.attrs {
		message += fmt.Sprintf(" %s=%v", attr.Key, attr.Value)
	}
	r.Attrs(func(a slog.Attr) bool {
		message += fmt.Sprintf(" %s=%v", a.Key, a.Value)
		return true
	})
	return message
}

func (h *CloudWatchHandler) putLogsWithRetry(ctx context.Context, input *cloudwatchlogs.PutLogEventsInput) error {
	maxRetries := 3
	for i := 0; i < maxRetries; i++ {
		if _, err := h.logsClient.PutLogEvents(ctx, input); err == nil {
			return nil
		} else if i == maxRetries-1 {
			return err
		}
		time.Sleep(time.Second * time.Duration(i+1))
	}
	return nil
}

func (h *CloudWatchHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	newHandlers := make([]slog.Handler, len(h.handlers))
	for i, handler := range h.handlers {
		newHandlers[i] = handler.WithAttrs(attrs)
	}

	return &CloudWatchHandler{
		logsClient:    h.logsClient,
		metricsClient: h.metricsClient,
		logGroup:      h.logGroup,
		logStream:     h.logStream,
		namespace:     h.namespace,
		attrs:         append(h.attrs, attrs...),
		handlers:      newHandlers,
		initialized:   h.initialized,
		logLevel:      h.logLevel,
	}
}

func (h *CloudWatchHandler) WithGroup(name string) slog.Handler {
	newHandlers := make([]slog.Handler, len(h.handlers))
	for i, handler := range h.handlers {
		newHandlers[i] = handler.WithGroup(name)
	}

	return &CloudWatchHandler{
		logsClient:    h.logsClient,
		metricsClient: h.metricsClient,
		logGroup:      h.logGroup,
		logStream:     h.logStream,
		namespace:     h.namespace,
		attrs:         h.attrs,
		handlers:      newHandlers,
		initialized:   h.initialized,
		logLevel:      h.logLevel,
	}
}

func (h *CloudWatchHandler) collectMetrics() []types.MetricDatum {
	var m runtime.MemStats
	runtime.ReadMemStats(&m)

	return []types.MetricDatum{
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

func (h *CloudWatchHandler) sendMetrics(ctx context.Context) error {
	metrics := h.collectMetrics()

	_, err := h.metricsClient.PutMetricData(ctx, &cloudwatch.PutMetricDataInput{
		Namespace:  aws.String(h.namespace),
		MetricData: metrics,
	})

	if err != nil {
		return fmt.Errorf("failed to send metrics to CloudWatch: %w", err)
	}

	Logger.Debug("Sent metrics to CloudWatch",
		"memoryUsageMB", *metrics[0].Value,
		"routineCount", *metrics[1].Value)

	return nil
}

func (h *CloudWatchHandler) SendMetrics(ctx context.Context, interval time.Duration) error {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	if err := h.sendMetrics(ctx); err != nil {
		Logger.Error("Failed to send initial metrics", "error", err)
	}

	for {
		select {
		case <-ctx.Done():
			Logger.Info("Stopping metrics collection due to context cancellation")
			return ctx.Err()
		case <-ticker.C:
			if err := h.sendMetrics(ctx); err != nil {
				Logger.Error("Failed to send metrics", "error", err)
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

	describeInput := &cloudwatchlogs.DescribeLogStreamsInput{
		LogGroupName:        aws.String(h.logGroup),
		LogStreamNamePrefix: aws.String(h.logStream),
	}

	output, err := h.logsClient.DescribeLogStreams(ctx, describeInput)
	if err != nil {
		var notFoundErr *types.ResourceNotFoundException
		if !errors.As(err, &notFoundErr) {
			return fmt.Errorf("failed to describe log streams: %w", err)
		}
	}

	if output == nil || len(output.LogStreams) == 0 {
		createInput := &cloudwatchlogs.CreateLogStreamInput{
			LogGroupName:  aws.String(h.logGroup),
			LogStreamName: aws.String(h.logStream),
		}

		if _, err := h.logsClient.CreateLogStream(ctx, createInput); err != nil {
			return fmt.Errorf("failed to create log stream: %w", err)
		}
	}

	h.initialized = true
	return nil
}
