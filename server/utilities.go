/*
Eidolon Engine

Copyright 2024-2025 Jason Robinson

*/

package main

import (
	"context"
	"fmt"
	"strings"

	"github.com/gofrs/uuid/v5"
)

func GenerateUUIDv7() uuid.UUID {

	uuid_type_7, err := uuid.NewV7()
	if err != nil {
		Logger.Error("Error generating UUIDv7", "error", err)
		return uuid.Nil
	}
	return uuid_type_7
}

// formatItemListWithOxfordComma formats a list of items with Oxford comma
func formatItemListWithOxfordComma(items []string) string {
	switch len(items) {
	case 0:
		return ""
	case 1:
		return items[0]
	case 2:
		return items[0] + " and " + items[1]
	default:
		return strings.Join(items[:len(items)-1], ", ") + ", and " + items[len(items)-1]
	}
}

// RunWithPanicRecovery runs a function with panic recovery and logging
func RunWithPanicRecovery(goroutineName string, fn func(), extraFields ...interface{}) {
	defer func() {
		if err := recover(); err != nil {
			fields := []interface{}{
				"goroutine", goroutineName,
				"error", err,
			}
			fields = append(fields, extraFields...)
			Logger.Error("Panic in goroutine", fields...)
		}
	}()
	fn()
}

// RunWithPanicRecoveryCallback runs a function with panic recovery and calls a callback on panic
func RunWithPanicRecoveryCallback(goroutineName string, fn func(), onPanic func(error), extraFields ...interface{}) {
	defer func() {
		if err := recover(); err != nil {
			fields := []interface{}{
				"goroutine", goroutineName,
				"error", err,
			}
			fields = append(fields, extraFields...)
			Logger.Error("Panic in goroutine", fields...)

			if onPanic != nil {
				onPanic(fmt.Errorf("%v", err))
			}
		}
	}()
	fn()
}

// SendErrorNonBlocking sends an error to a channel without blocking
func SendErrorNonBlocking(errChan chan<- error, err error, componentName string) {
	select {
	case errChan <- err:
		// Error sent successfully
	default:
		// Channel is full, log the error instead
		Logger.Error("Error channel full, dropping error",
			"component", componentName,
			"error", err)
	}
}

// SafeSendString sends a string to a channel without blocking or panicking
func SafeSendString(ch chan<- string, msg string, recipientName string) bool {
	select {
	case ch <- msg:
		return true
	default:
		Logger.Warn("Channel send failed", "recipient", recipientName, "messageLength", len(msg))
		return false
	}
}

// SafeSendStringContext sends a string to a channel with context cancellation support
func SafeSendStringContext(ctx context.Context, ch chan<- string, msg string, recipientName string) bool {
	select {
	case ch <- msg:
		return true
	case <-ctx.Done():
		Logger.Debug("Channel send cancelled", "recipient", recipientName, "reason", ctx.Err())
		return false
	default:
		Logger.Warn("Channel send failed", "recipient", recipientName, "messageLength", len(msg))
		return false
	}
}
