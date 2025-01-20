package main

import (
	"fmt"
	"log/slog"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs"
)

// TODO: split out the logging betweent the Console and Clouwatch to allow different format and
// levles for each.

var Logger *slog.Logger

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
