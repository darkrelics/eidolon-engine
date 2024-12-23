package main

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
)

var Logger *slog.Logger

type logState struct {
	sequenceToken *string
	initialized   bool
	mutex         sync.Mutex
}

type CloudWatchHandler struct {
	ctx           context.Context
	logsClient    *cloudwatchlogs.Client
	metricsClient *cloudwatch.Client
	logLevel      int
	logGroup      string
	logStream     string
	namespace     string
	attrs         []slog.Attr
	handlers      []slog.Handler
	state         *logState
	mutex         sync.RWMutex
	interval      time.Duration
}

func NewLogHandler(globalCtx context.Context, configuration *Configuration) (*CloudWatchHandler, error) {

	level := parseLogLevel(configuration.Logging.LogLevel)

	awsCfg, err := config.LoadDefaultConfig(globalCtx, config.WithRegion(configuration.Aws.Region))
	if err != nil {
		return nil, fmt.Errorf("unable to load SDK config: %w", err)
	}

	logsClient := cloudwatchlogs.NewFromConfig(awsCfg)
	metricsClient := cloudwatch.NewFromConfig(awsCfg)

	stdoutHandler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: level}).WithAttrs([]slog.Attr{
		slog.String("application", configuration.Logging.ApplicationName),
		slog.String("region", configuration.Aws.Region),
	})

	handler := &CloudWatchHandler{
		ctx:           globalCtx,
		logsClient:    logsClient,
		metricsClient: metricsClient,
		logLevel:      configuration.Logging.LogLevel,
		logGroup:      configuration.Logging.LogGroup,
		logStream:     configuration.Logging.LogStream,
		namespace:     configuration.Logging.MetricNamespace,
		handlers:      []slog.Handler{stdoutHandler},
		state:         &logState{},
		interval:      time.Minute, // Paramterize this
	}

	// Set the global logger
	Logger = slog.New(handler)
	slog.SetDefault(Logger)

	return handler, nil
}

func (h *CloudWatchHandler) Run() error {

	if h.interval < time.Second {
		return fmt.Errorf("interval must be at least 1 second")
	}

	ticker := time.NewTicker(h.interval)
	defer ticker.Stop()

	for {
		select {
		case <-h.ctx.Done():
			return h.ctx.Err()
		case <-ticker.C:
			if err := h.collectAndSendMetrics(h.ctx); err != nil {
				Logger.Error("Failed to send metrics", "error", err)
			}
		}
	}

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

func (h *CloudWatchHandler) Handle(ctx context.Context, r slog.Record) error {
	if err := h.ensureInitialized(ctx); err != nil {
		return fmt.Errorf("initialization error: %w", err)
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

	return h.handleDownstream(ctx, r)
}

func (h *CloudWatchHandler) putLogsWithRetry(ctx context.Context, input *cloudwatchlogs.PutLogEventsInput) error {
	const maxRetries = 3
	var backoff = time.Second

	for attempt := 0; attempt < maxRetries; attempt++ {
		h.state.mutex.Lock()
		if h.state.sequenceToken != nil {
			input.SequenceToken = aws.String(*h.state.sequenceToken)
		}
		h.state.mutex.Unlock()

		output, err := h.logsClient.PutLogEvents(ctx, input)
		if err == nil {
			h.state.mutex.Lock()
			if output.NextSequenceToken != nil {
				h.state.sequenceToken = output.NextSequenceToken
			}
			h.state.mutex.Unlock()
			return nil
		}

		if errors.Is(err, &cwlogtypes.ResourceNotFoundException{}) {
			if err := h.ensureInitialized(ctx); err != nil {
				return err
			}
			continue
		}

		if attempt < maxRetries-1 {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(backoff):
				backoff *= 2
				continue
			}
		}

		return fmt.Errorf("max retries exceeded: %w", err)
	}

	return errors.New("max retries exceeded")
}

func (h *CloudWatchHandler) ensureInitialized(ctx context.Context) error {
	// Check if initialization has already occurred without locking
	if h.state.initialized {
		return nil
	}

	h.mutex.Lock()
	defer h.mutex.Unlock()

	// Recheck the initialized flag after acquiring the lock to
	// handle the case of multiple goroutines attempting initialization concurrently
	if h.state.initialized {
		return nil
	}

	if err := h.createLogStreamIfNotExists(ctx); err != nil {
		return err
	}
	h.state.initialized = true

	return nil
}

func (h *CloudWatchHandler) createLogStreamIfNotExists(ctx context.Context) error {
	describeInput := &cloudwatchlogs.DescribeLogStreamsInput{
		LogGroupName:        aws.String(h.logGroup),
		LogStreamNamePrefix: aws.String(h.logStream),
	}

	output, err := h.logsClient.DescribeLogStreams(ctx, describeInput)
	if err != nil && !errors.Is(err, &cwlogtypes.ResourceNotFoundException{}) {
		return fmt.Errorf("failed to describe log streams: %w", err)
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

	return nil
}

func (h *CloudWatchHandler) SendMetrics(ctx context.Context, interval time.Duration) error {
	if interval < time.Second {
		return fmt.Errorf("interval must be at least 1 second")
	}

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
			if err := h.collectAndSendMetrics(ctx); err != nil {
				slog.Error("Failed to send metrics", "error", err)
			}
		}
	}
}

func (h *CloudWatchHandler) collectAndSendMetrics(ctx context.Context) error {
	var m runtime.MemStats
	runtime.ReadMemStats(&m)

	metrics := []types.MetricDatum{
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

	_, err := h.metricsClient.PutMetricData(ctx, &cloudwatch.PutMetricDataInput{
		Namespace:  aws.String(h.namespace),
		MetricData: metrics,
	})

	return err
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
		state:         h.state,
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
		state:         h.state,
		logLevel:      h.logLevel,
	}
}

func (h *CloudWatchHandler) Enabled(ctx context.Context, level slog.Level) bool {
	return level >= slog.Level(h.logLevel)
}

func (h *CloudWatchHandler) handleDownstream(ctx context.Context, r slog.Record) error {
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
