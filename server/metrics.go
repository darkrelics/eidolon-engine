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
	"context"
	"fmt"
	"runtime"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch/types"
)

// AWS CloudWatch has a limit of 20 metrics per request
const batchSize = 20

func (c *CloudWatch) collectMetrics() {

	Logger.Debug("Collecting metrics...")

	var m runtime.MemStats

	runtime.ReadMemStats(&m)

	c.metrics <- types.MetricDatum{
		MetricName: aws.String("Memory Usage"),
		Unit:       types.StandardUnitMegabytes,
		Value:      aws.Float64(float64(m.Alloc) / 1024 / 1024),
	}

	c.metrics <- types.MetricDatum{
		MetricName: aws.String("Go Routines"),
		Unit:       types.StandardUnitCount,
		Value:      aws.Float64(float64(runtime.NumGoroutine())),
	}
}

func (c *CloudWatch) SendMetrics(metrics []types.MetricDatum) error {

	Logger.Debug("Sending metrics...")

	if len(metrics) == 0 {
		return nil
	}

	for i := 0; i < len(metrics); i += batchSize {
		end := i + batchSize
		if end > len(metrics) {
			end = len(metrics)
		}

		batch := metrics[i:end]

		// Create context with timeout for the API call
		ctx, cancel := context.WithTimeout(c.ctx, 10*time.Second)
		defer cancel()

		input := &cloudwatch.PutMetricDataInput{
			Namespace:  aws.String(c.namespace),
			MetricData: batch,
		}

		// Implement retry with backoff
		var err error
		for retries := 0; retries < 3; retries++ {
			_, err = c.metricsClient.PutMetricData(ctx, input)
			if err == nil {
				break
			}

			if retries < 2 {
				// Exponential backoff
				time.Sleep(time.Duration(1<<retries) * time.Second)
			}
		}

		if err != nil {
			return fmt.Errorf("failed to send metrics batch after retries: %w", err)
		}
	}

	return nil
}

// SendSecurityMetric sends a security-related metric to CloudWatch
func (c *CloudWatch) SendSecurityMetric(metricName string, value float64, unit types.StandardUnit, dimensions []types.Dimension) {
	metric := types.MetricDatum{
		MetricName: aws.String(metricName),
		Unit:       unit,
		Value:      aws.Float64(value),
		Timestamp:  aws.Time(time.Now()),
		Dimensions: dimensions,
	}

	select {
	case c.metrics <- metric:
		// Metric queued successfully
	default:
		// Channel full, log but don't block
		Logger.Warn("Security metric channel full, dropping metric", "metric", metricName)
	}
}

// SendAuthenticationBlock sends a metric when an IP or user is blocked
func (c *CloudWatch) SendAuthenticationBlock(blockType string, identifier string, banDuration time.Duration) {
	dimensions := []types.Dimension{
		{
			Name:  aws.String("BlockType"),
			Value: aws.String(blockType),
		},
		{
			Name:  aws.String("Environment"),
			Value: aws.String(c.namespace),
		},
	}

	// Block count tracking monitors security events
	c.SendSecurityMetric("AuthenticationBlocks", 1, types.StandardUnitCount, dimensions)

	// Ban duration helps analyze attack patterns
	c.SendSecurityMetric("AuthenticationBanDuration", banDuration.Minutes(), types.StandardUnitSeconds, dimensions)

	// Log the block event separately (not as a normal log)
	Logger.Info("SECURITY_EVENT: Authentication block applied",
		"event_type", "auth_block",
		"block_type", blockType,
		"identifier", identifier,
		"ban_duration_minutes", banDuration.Minutes(),
		"timestamp", time.Now().Unix())
}

// SendRateLimitViolation sends a metric when a rate limit is exceeded (but not necessarily banned)
func (c *CloudWatch) SendRateLimitViolation(limitType string) {
	dimensions := []types.Dimension{
		{
			Name:  aws.String("LimitType"),
			Value: aws.String(limitType),
		},
		{
			Name:  aws.String("Environment"),
			Value: aws.String(c.namespace),
		},
	}

	c.SendSecurityMetric("RateLimitViolations", 1, types.StandardUnitCount, dimensions)
}

// Run manages CloudWatch metric batching and submission cycles
func (c *CloudWatch) Run(errChan chan error) error {
	var runErr error
	RunWithPanicRecoveryCallback("cloudwatch.Run", func() {
		runErr = c.runInternal(errChan)
	}, func(err error) {
		SendErrorNonBlocking(errChan, fmt.Errorf("panic in CloudWatch: %v", err), "CloudWatch")
	})
	return runErr
}

// runInternal contains the actual CloudWatch loop logic
func (c *CloudWatch) runInternal(errChan chan error) error {
	Logger.Info("CloudWatch: Starting CloudWatch Metrics Collection")

	if err := c.initLogStream(); err != nil {
		return fmt.Errorf("log stream init: %w", err)
	}

	ticker := time.NewTicker(c.interval)
	defer ticker.Stop()

	for {
		select {
		case <-c.ctx.Done():
			Logger.Info("CloudWatch: Run - Shutdown signal received")
			return nil
		case <-ticker.C:
			c.collectMetrics()

			metrics := make([]types.MetricDatum, 0)

		drainLoop:
			for {
				select {
				case metric := <-c.metrics:
					metrics = append(metrics, metric)
				default:
					break drainLoop
				}
			}

			if len(metrics) > 0 {
				if err := c.SendMetrics(metrics); err != nil {
					Logger.Error("Error sending metrics", "error", err)
					metricsErr := fmt.Errorf("error sending metrics: %w", err)
					SendErrorNonBlocking(errChan, metricsErr, "CloudWatch")
					return metricsErr
				}
			}
		}
	}
}

// AddMetric allows other parts of the system to submit metrics
func (c *CloudWatch) AddMetric(metric types.MetricDatum) {

	Logger.Debug("Adding metric...")

	select {
	case c.metrics <- metric:
	default:
		Logger.Warn("Metrics channel full, dropping metric", "name", *metric.MetricName)
	}
}
