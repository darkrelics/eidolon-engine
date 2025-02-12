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
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs"
	cwlogtypes "github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs/types"
)

// TODO: split out the logging betweent the Console and Clouwatch to allow different format and
// levles for each.

const maxRetries = 3

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

	fmt.Println("Initilize Log Stream...")
	defer Logger.Info("CloudWatch: Log stream initialized")

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

func (c *CloudWatch) Handle(ctx context.Context, r slog.Record) error {
	fmt.Println("CloudWatch Handle...")

	if err := c.initLogStream(); err != nil {
		return fmt.Errorf("failed to initialize log stream: %w", err)
	}

	// Marshal the slog.Record to JSON
	var buf bytes.Buffer
	encoder := json.NewEncoder(&buf)
	if err := encoder.Encode(r); err != nil {
		return fmt.Errorf("failed to marshal slog.Record to JSON: %w", err)
	}

	input := &cloudwatchlogs.PutLogEventsInput{
		LogGroupName:  aws.String(c.logGroup),
		LogStreamName: aws.String(c.logStream),
		LogEvents: []cwlogtypes.InputLogEvent{{
			Message:   aws.String(buf.String()), // Send the JSON string
			Timestamp: aws.Int64(time.Now().UnixNano() / int64(time.Millisecond)),
		}},
	}

	if c.sequenceToken != nil {
		input.SequenceToken = c.sequenceToken
	}

	output, err := c.logClient.PutLogEvents(ctx, input)
	if err != nil {
		return fmt.Errorf("failed to put log events: %w", err)
	}

	c.mutex.Lock()
	c.sequenceToken = output.NextSequenceToken
	c.mutex.Unlock()

	return nil
}

func (c *CloudWatch) putLogs(input *cloudwatchlogs.PutLogEventsInput) error {

	fmt.Println("Putting Logs...")

	backoff := time.Second

	for attempt := 0; attempt < maxRetries; attempt++ {
		output, err := c.logClient.PutLogEvents(c.ctx, input)
		if err == nil {
			c.mutex.Lock()
			c.sequenceToken = output.NextSequenceToken
			c.mutex.Unlock()
			return nil
		}

		if strings.Contains(err.Error(), "ResourceNotFoundException") {
			if err := c.initLogStream(); err != nil {
				return err
			}
			continue
		}

		if attempt < maxRetries-1 {
			time.Sleep(backoff)
			backoff *= 2
			continue
		}

		return fmt.Errorf("put logs failed after %d attempts: %w", maxRetries, err)
	}

	return nil
}
