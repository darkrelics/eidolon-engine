package main

import (
	"context"
	"errors"
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
	cwlogtypes "github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs/types"
)

var Logger *slog.Logger

type CloudWatchHandler struct {
	ctx           context.Context
	cancel        context.CancelFunc
	logsClient    *cloudwatchlogs.Client
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

func NewLogHandler(ctx context.Context, cfg *Configuration) (*CloudWatchHandler, error) {
	awsCfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(cfg.Aws.Region))
	if err != nil {
		return nil, fmt.Errorf("aws config load: %w", err)
	}

	handlerCtx, cancel := context.WithCancel(ctx)

	// Create console handler first
	consoleHandler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: parseLogLevel(cfg.Logging.LogLevel),
	}).WithAttrs([]slog.Attr{
		slog.String("application", cfg.Logging.ApplicationName),
		slog.String("region", cfg.Aws.Region),
	})

	handler := &CloudWatchHandler{
		ctx:           handlerCtx,
		cancel:        cancel,
		logsClient:    cloudwatchlogs.NewFromConfig(awsCfg),
		metricsClient: cloudwatch.NewFromConfig(awsCfg),
		logGroup:      cfg.Logging.LogGroup,
		logStream:     cfg.Logging.LogStream,
		namespace:     cfg.Logging.MetricNamespace,
		interval:      time.Minute,
		handlers:      []slog.Handler{consoleHandler},
	}

	// Create logger with console handler first so we get immediate output
	Logger = slog.New(consoleHandler)
	slog.SetDefault(Logger)

	return handler, nil
}

func (h *CloudWatchHandler) Run() error {
	if err := h.initLogStream(h.ctx); err != nil {
		return fmt.Errorf("log stream init: %w", err)
	}

	ticker := time.NewTicker(h.interval)
	defer ticker.Stop()

	for {
		select {
		case <-h.ctx.Done():
			return nil
		case <-ticker.C:
			if err := h.sendMetrics(); err != nil {
				Logger.Error("metrics send failed", "error", err)
			}
		}
	}
}

func (h *CloudWatchHandler) Stop() error {
	h.cancel()
	return nil
}

func (h *CloudWatchHandler) Handle(ctx context.Context, r slog.Record) error {
	if err := h.initLogStream(ctx); err != nil {
		return err
	}

	input := &cloudwatchlogs.PutLogEventsInput{
		LogGroupName:  aws.String(h.logGroup),
		LogStreamName: aws.String(h.logStream),
		LogEvents: []cwlogtypes.InputLogEvent{{
			Message:   aws.String(h.formatMessage(r)),
			Timestamp: aws.Int64(time.Now().UnixNano() / int64(time.Millisecond)),
		}},
	}

	if err := h.putLogs(ctx, input); err != nil {
		return err
	}

	return h.handleDownstream(ctx, r)
}

func (h *CloudWatchHandler) putLogs(ctx context.Context, input *cloudwatchlogs.PutLogEventsInput) error {
	const maxRetries = 3
	backoff := time.Second

	h.mutex.RLock()
	if h.sequenceToken != nil {
		input.SequenceToken = h.sequenceToken
	}
	h.mutex.RUnlock()

	for attempt := 0; attempt < maxRetries; attempt++ {
		output, err := h.logsClient.PutLogEvents(ctx, input)
		if err == nil {
			h.mutex.Lock()
			h.sequenceToken = output.NextSequenceToken
			h.mutex.Unlock()
			return nil
		}

		if errors.Is(err, &cwlogtypes.ResourceNotFoundException{}) {
			if err := h.initLogStream(ctx); err != nil {
				return err
			}
			continue
		}

		if attempt < maxRetries-1 {
			time.Sleep(backoff)
			backoff *= 2
			continue
		}

		return fmt.Errorf("put logs failed: %w", err)
	}
	return nil
}

func (h *CloudWatchHandler) initLogStream(ctx context.Context) error {
	if h.initialized {
		return nil
	}

	h.mutex.Lock()
	defer h.mutex.Unlock()

	if h.initialized {
		return nil
	}

	// Try to describe the log stream first to check if it exists
	_, err := h.logsClient.DescribeLogStreams(ctx, &cloudwatchlogs.DescribeLogStreamsInput{
		LogGroupName:        aws.String(h.logGroup),
		LogStreamNamePrefix: aws.String(h.logStream),
	})

	if err != nil {
		// If the stream doesn't exist, create it
		if strings.Contains(err.Error(), "ResourceNotFoundException") {
			_, err = h.logsClient.CreateLogStream(ctx, &cloudwatchlogs.CreateLogStreamInput{
				LogGroupName:  aws.String(h.logGroup),
				LogStreamName: aws.String(h.logStream),
			})
			if err != nil && !strings.Contains(err.Error(), "ResourceAlreadyExistsException") {
				return fmt.Errorf("create log stream: %w", err)
			}
		} else {
			return fmt.Errorf("describe log stream: %w", err)
		}
	}

	h.initialized = true
	return nil
}

func (h *CloudWatchHandler) sendMetrics() error {
	metrics := h.collectMetrics()

	_, err := h.metricsClient.PutMetricData(h.ctx, &cloudwatch.PutMetricDataInput{
		Namespace:  aws.String(h.namespace),
		MetricData: metrics,
	})

	return err
}

func (h *CloudWatchHandler) collectMetrics() []types.MetricDatum {
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

	if h.server != nil {
		metrics = append(metrics, types.MetricDatum{
			MetricName: aws.String("PlayerCount"),
			Unit:       types.StandardUnitCount,
			Value:      aws.Float64(float64(h.server.PlayerCount())),
		})
	}

	return metrics
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
	msg := r.Message
	r.Attrs(func(a slog.Attr) bool {
		msg += fmt.Sprintf(" %s=%v", a.Key, a.Value)
		return true
	})
	return msg
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

// Required slog.Handler interface methods
func (h *CloudWatchHandler) Enabled(ctx context.Context, level slog.Level) bool {
	return true
}

func (h *CloudWatchHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	return h
}

func (h *CloudWatchHandler) WithGroup(name string) slog.Handler {
	return h
}
