// logging.go

/*
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

*/

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"runtime"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs"
	cwlogtypes "github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs/types"
)

// TODO: split out the logging between the Console and Cloudwatch to allow different format and
// levels for each.

const maxRetries = 3

var Logger *slog.Logger
var CloudWatchMetrics *CloudWatch

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

// CloudWatchHandler implements slog.Handler for AWS CloudWatch
type CloudWatchHandler struct {
	cloudWatch  *CloudWatch
	level       slog.Level
	attrs       []slog.Attr
	groups      []string
	consoleJSON bool
	jsonHandler slog.Handler
}

// NewCloudWatchHandler creates a new CloudWatch handler for slog
func NewCloudWatchHandler(cw *CloudWatch, level slog.Level, consoleJSON bool) *CloudWatchHandler {
	var jsonHandler slog.Handler
	if consoleJSON {
		jsonHandler = slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
			Level:     level,
			AddSource: false,
		})
	}

	return &CloudWatchHandler{
		cloudWatch:  cw,
		level:       level,
		attrs:       []slog.Attr{},
		groups:      []string{},
		consoleJSON: consoleJSON,
		jsonHandler: jsonHandler,
	}
}

// Enabled implements slog.Handler.Enabled
func (h *CloudWatchHandler) Enabled(ctx context.Context, level slog.Level) bool {
	return level >= h.level
}

// Handle processes log records for CloudWatch delivery
func (h *CloudWatchHandler) Handle(ctx context.Context, record slog.Record) error {
	// Also output to console JSON handler if enabled
	if h.consoleJSON && h.jsonHandler != nil {
		if err := h.jsonHandler.Handle(ctx, record); err != nil {
			// Log to stderr since we can't use the logger here
			fmt.Fprintf(os.Stderr, "CloudWatch: Failed to handle JSON log: %v\n", err)
		}
	}

	// Skip if CloudWatch is not initialized
	if h.cloudWatch == nil {
		return nil
	}

	// Marshal record to JSON for CloudWatch
	type logEntry struct {
		Time    string         `json:"Time"`
		Level   string         `json:"Level"`
		Message string         `json:"Message"`
		Attrs   map[string]any `json:"Attrs,omitempty"`
		File    string         `json:"File,omitempty"`
		Line    int            `json:"Line,omitempty"`
		Func    string         `json:"Function,omitempty"`
	}

	entry := logEntry{
		Time:    record.Time.Format(time.RFC3339),
		Level:   record.Level.String(),
		Message: record.Message,
		Attrs:   make(map[string]any),
	}

	// Get file/line info for the log entry if available
	if record.PC != 0 {
		fs := runtime.CallersFrames([]uintptr{record.PC})
		if frame, _ := fs.Next(); frame.PC != 0 {
			entry.File = frame.File
			entry.Line = frame.Line
			entry.Func = frame.Function
		}
	}

	// Add attributes
	record.Attrs(func(attr slog.Attr) bool {
		if attr.Key != "" && attr.Value.Kind() != slog.KindGroup {
			entry.Attrs[attr.Key] = attr.Value.Any()
		}
		return true
	})

	// Add handler attributes
	for _, attr := range h.attrs {
		if attr.Key != "" {
			entry.Attrs[attr.Key] = attr.Value.Any()
		}
	}

	// Marshal to JSON
	jsonData, err := json.Marshal(entry)
	if err != nil {
		return fmt.Errorf("failed to marshal log entry: %w", err)
	}

	// CloudWatch transmission includes structured metadata
	if err := h.cloudWatch.initLogStream(); err != nil {
		return err
	}

	input := &cloudwatchlogs.PutLogEventsInput{
		LogGroupName:  aws.String(h.cloudWatch.logGroup),
		LogStreamName: aws.String(h.cloudWatch.logStream),
		LogEvents: []cwlogtypes.InputLogEvent{
			{
				Message:   aws.String(string(jsonData)),
				Timestamp: aws.Int64(time.Now().UnixNano() / int64(time.Millisecond)),
			},
		},
	}

	h.cloudWatch.mutex.RLock()
	if h.cloudWatch.sequenceToken != nil {
		input.SequenceToken = h.cloudWatch.sequenceToken
	}
	h.cloudWatch.mutex.RUnlock()

	return h.cloudWatch.putLogs(input)
}

// WithAttrs implements slog.Handler.WithAttrs
func (h *CloudWatchHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	newH := *h
	newH.attrs = append(h.attrs, attrs...)

	// Also update console JSON handler if enabled
	if h.consoleJSON && h.jsonHandler != nil {
		newH.jsonHandler = h.jsonHandler.WithAttrs(attrs)
	}

	return &newH
}

// WithGroup implements slog.Handler.WithGroup
func (h *CloudWatchHandler) WithGroup(name string) slog.Handler {
	newH := *h
	newH.groups = append(h.groups, name)

	// Also update console JSON handler if enabled
	if h.consoleJSON && h.jsonHandler != nil {
		newH.jsonHandler = h.jsonHandler.WithGroup(name)
	}

	return &newH
}

// initLogStream initializes the CloudWatch log stream, creating the log group and stream if needed.
func (c *CloudWatch) initLogStream() error {
	// Skip if already initialized
	if c.initialized {
		return nil
	}

	// Use fmt for debugging to avoid recursive logging
	fmt.Printf("Initializing CloudWatch log stream: %s/%s\n", c.logGroup, c.logStream)

	c.mutex.Lock()
	defer c.mutex.Unlock()

	// Double-check if already initialized after acquiring the lock
	if c.initialized {
		return nil
	}

	// Check and create log group if needed
	if err := c.ensureLogGroupExists(); err != nil {
		return err
	}

	// Check and create log stream if needed
	token, err := c.ensureLogStreamExists()
	if err != nil {
		return err
	}
	if token != nil {
		c.sequenceToken = token
	}

	// Verify the log stream is working with a test message
	if err := c.sendTestMessage(); err != nil {
		return err
	}

	c.initialized = true
	fmt.Printf("CloudWatch log stream initialization complete\n")
	return nil
}

// ensureLogGroupExists checks if the log group exists and creates it if needed.
func (c *CloudWatch) ensureLogGroupExists() error {
	_, err := c.logClient.DescribeLogGroups(c.ctx, &cloudwatchlogs.DescribeLogGroupsInput{
		LogGroupNamePrefix: aws.String(c.logGroup),
	})

	if err != nil {
		fmt.Printf("Error checking log group %s: %v\n", c.logGroup, err)

		// Create the log group
		_, err = c.logClient.CreateLogGroup(c.ctx, &cloudwatchlogs.CreateLogGroupInput{
			LogGroupName: aws.String(c.logGroup),
		})

		if err != nil && !strings.Contains(err.Error(), "ResourceAlreadyExistsException") {
			fmt.Printf("Failed to create log group %s: %v\n", c.logGroup, err)
			return fmt.Errorf("create log group: %w", err)
		}
		fmt.Printf("Created log group: %s\n", c.logGroup)
	}

	return nil
}

// ensureLogStreamExists checks if the log stream exists and creates it if needed.
// Returns the current sequence token if available.
func (c *CloudWatch) ensureLogStreamExists() (*string, error) {
	resp, err := c.logClient.DescribeLogStreams(c.ctx, &cloudwatchlogs.DescribeLogStreamsInput{
		LogGroupName:        aws.String(c.logGroup),
		LogStreamNamePrefix: aws.String(c.logStream),
	})

	// Check if the log stream exists and get its sequence token
	var sequenceToken *string
	logStreamExists := false
	if err == nil && resp != nil && len(resp.LogStreams) > 0 {
		for _, stream := range resp.LogStreams {
			if aws.ToString(stream.LogStreamName) == c.logStream {
				logStreamExists = true
				if stream.UploadSequenceToken != nil {
					sequenceToken = stream.UploadSequenceToken
					fmt.Printf("Found existing log stream with sequence token: %s\n", *sequenceToken)
				}
				break
			}
		}
	}

	// Create the log stream if it doesn't exist
	if !logStreamExists {
		fmt.Printf("Creating log stream: %s in group: %s\n", c.logStream, c.logGroup)

		_, err = c.logClient.CreateLogStream(c.ctx, &cloudwatchlogs.CreateLogStreamInput{
			LogGroupName:  aws.String(c.logGroup),
			LogStreamName: aws.String(c.logStream),
		})

		if err != nil {
			if !strings.Contains(err.Error(), "ResourceAlreadyExistsException") {
				fmt.Printf("Failed to create log stream %s: %v\n", c.logStream, err)
				return nil, fmt.Errorf("create log stream: %w", err)
			}
			fmt.Printf("Log stream already exists (race condition): %s\n", c.logStream)
		} else {
			fmt.Printf("Successfully created log stream: %s\n", c.logStream)
		}
	}

	return sequenceToken, nil
}

// sendTestMessage sends a test message to verify the log stream is working.
func (c *CloudWatch) sendTestMessage() error {
	testInput := &cloudwatchlogs.PutLogEventsInput{
		LogGroupName:  aws.String(c.logGroup),
		LogStreamName: aws.String(c.logStream),
		LogEvents: []cwlogtypes.InputLogEvent{
			{
				Message:   aws.String("CloudWatch logging initialized"),
				Timestamp: aws.Int64(time.Now().UnixNano() / int64(time.Millisecond)),
			},
		},
	}

	if c.sequenceToken != nil {
		testInput.SequenceToken = c.sequenceToken
	}

	testOutput, err := c.logClient.PutLogEvents(c.ctx, testInput)
	if err != nil {
		fmt.Printf("Error sending test log event: %v\n", err)

		// Token mismatch requires synchronization with CloudWatch
		if strings.Contains(err.Error(), "InvalidSequenceTokenException") {
			updatedToken := c.extractSequenceTokenFromError(err)
			if updatedToken != "" {
				c.sequenceToken = aws.String(updatedToken)
				fmt.Printf("Updated sequence token to: %s\n", *c.sequenceToken)

				// Try again with the correct token
				testInput.SequenceToken = c.sequenceToken
				testOutput, err = c.logClient.PutLogEvents(c.ctx, testInput)
				if err != nil {
					fmt.Printf("Error sending test log event after token update: %v\n", err)
					return fmt.Errorf("failed to send test log event: %w", err)
				}
			}
		} else {
			return fmt.Errorf("failed to send test log event: %w", err)
		}
	}

	if testOutput != nil && testOutput.NextSequenceToken != nil {
		c.sequenceToken = testOutput.NextSequenceToken
		fmt.Printf("Updated sequence token to: %s\n", *c.sequenceToken)
	}

	return nil
}

// extractSequenceTokenFromError extracts the sequence token from an invalid sequence token error.
func (c *CloudWatch) extractSequenceTokenFromError(err error) string {
	parts := strings.Split(err.Error(), "sequenceToken is: ")
	if len(parts) > 1 {
		token := strings.TrimSpace(parts[1])
		return strings.Trim(token, "\"")
	}
	return ""
}

func (c *CloudWatch) putLogs(input *cloudwatchlogs.PutLogEventsInput) error {
	var err error
	backoff := time.Second

	for attempt := 0; attempt < maxRetries; attempt++ {
		var output *cloudwatchlogs.PutLogEventsOutput

		output, err = c.logClient.PutLogEvents(c.ctx, input)
		if err == nil {
			c.mutex.Lock()
			c.sequenceToken = output.NextSequenceToken
			c.mutex.Unlock()
			return nil
		}

		// Error-specific handling enables recovery strategies
		if strings.Contains(err.Error(), "ResourceNotFoundException") {
			if err := c.initLogStream(); err != nil {
				return err
			}
			continue
		}

		// Token mismatch requires synchronization with CloudWatch
		if strings.Contains(err.Error(), "InvalidSequenceTokenException") {
			// Extract the expected sequence token from the error message
			parts := strings.Split(err.Error(), "sequenceToken is: ")
			if len(parts) > 1 {
				token := strings.TrimSpace(parts[1])
				token = strings.Trim(token, "\"")

				c.mutex.Lock()
				c.sequenceToken = aws.String(token)
				c.mutex.Unlock()

				input.SequenceToken = aws.String(token)
				continue
			}
		}

		// Back off and retry
		if attempt < maxRetries-1 {
			time.Sleep(backoff)
			backoff *= 2
			continue
		}
	}

	return fmt.Errorf("put logs failed after %d attempts: %w", maxRetries, err)
}
