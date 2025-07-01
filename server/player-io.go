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
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"

	"golang.org/x/crypto/ssh"
)

func (p *Player) handleRequests(ctx context.Context, requests <-chan *ssh.Request, done chan error) {
	defer func() {
		if r := recover(); r != nil {
			Logger.Warn("Recovered in handleRequests", "player", p.id, "recover", r)
			done <- fmt.Errorf("panic in request handler: %v", r)
		}
	}()

	for {
		select {
		case <-ctx.Done():
			done <- ctx.Err()
			return
		case req, ok := <-requests:
			if !ok {
				Logger.Debug("Request channel closed", "player", p.id)
				done <- nil
				return
			}

			p.mutex.Lock()
			switch req.Type {
			case "shell":
				if err := req.Reply(true, nil); err != nil {
					Logger.Error("Player-IO: Failed to reply to shell request", "error", err)
				}
			case "pty-req":
				termLen := req.Payload[3]
				w, h := ParseDims(req.Payload[termLen+4:])
				p.consoleWidth = w
				p.consoleHeight = h
				if err := req.Reply(true, nil); err != nil {
					Logger.Error("Player-IO: Failed to reply to pty-req", "error", err)
				}
			case "window-change":
				w, h := ParseDims(req.Payload)
				p.consoleWidth = w
				p.consoleHeight = h
			default:
				req.Reply(false, nil)
			}
			p.mutex.Unlock()
		}
	}
}

func (p *Player) handleInput(ctx context.Context, done chan error) {
	defer func() {
		if r := recover(); r != nil {
			Logger.Warn("Recovered in handleInput", "player", p.id, "recover", r)
			done <- fmt.Errorf("panic in input handler: %v", r)
		}
	}()

	reader := bufio.NewReader(p.connection)

	// Create idle timeout timer
	idleTimeout := time.Duration(p.server.config.Game.PlayerIdleTimeoutSeconds) * time.Second
	idleTimer := time.NewTimer(idleTimeout)
	defer idleTimer.Stop()

	// Warning timer (5 minutes before disconnect, or half the timeout if less than 10 minutes)
	var warningTime time.Duration
	if idleTimeout > 10*time.Minute {
		warningTime = 5 * time.Minute
	} else {
		warningTime = idleTimeout / 2
	}

	var warningTimer *time.Timer
	var warningShown bool

	if warningTime > 0 {
		warningTimer = time.NewTimer(idleTimeout - warningTime)
		defer warningTimer.Stop()
	}

	for {
		select {
		case <-ctx.Done():
			done <- ctx.Err()
			return
		case <-func() <-chan time.Time {
			if warningTimer != nil {
				return warningTimer.C
			}
			return nil
		}():
			if !warningShown {
				warningShown = true
				remainingMinutes := int(warningTime.Minutes())
				select {
				case p.commandOut <- ApplyColor("yellow", fmt.Sprintf("\r\n*** WARNING: You will be disconnected in %d minutes due to inactivity ***\r\n", remainingMinutes)):
				case <-ctx.Done():
					done <- ctx.Err()
					return
				}
			}
		case <-idleTimer.C:
			select {
			case p.commandOut <- ApplyColor("red", "\r\n*** Disconnected due to inactivity ***\r\n"):
			case <-ctx.Done():
			}
			Logger.Info("Player disconnected due to idle timeout", "player", p.id)
			done <- errors.New("idle timeout")
			return
		default:
			r, _, err := reader.ReadRune()
			if err != nil {
				if err == io.EOF {
					Logger.Info("Connection closed by client", "player", p.id)
					done <- nil
					return
				}
				Logger.Error("Error reading input", "player", p.id, "error", err)
				done <- fmt.Errorf("read error: %w", err)
				return
			}

			// Reset idle timers on any input
			if !idleTimer.Stop() {
				select {
				case <-idleTimer.C:
				default:
				}
			}
			idleTimer.Reset(idleTimeout)

			// Reset warning timer if not already shown
			if !warningShown && warningTimer != nil {
				if !warningTimer.Stop() {
					select {
					case <-warningTimer.C:
					default:
					}
				}
				warningTimer.Reset(idleTimeout - warningTime)
			} else if warningShown {
				// Clear warning state on new input
				warningShown = false
				if warningTimer != nil {
					warningTimer.Reset(idleTimeout - warningTime)
				}
			}

			// Handle different input cases
			switch r {
			case '\n', '\r':
				if p.inputBuffer.Length() > 0 {
					input := p.inputBuffer.String()
					select {
					case p.commandIn <- input:
						if p.echo {
							if _, err := p.connection.Write([]byte("\r\n")); err != nil {
								Logger.Error("Player-IO: Failed to write newline", "error", err)
							}
						}
						p.inputBuffer.Clear()
					case <-ctx.Done():
						done <- ctx.Err()
						return
					}
				} else {
					// Handle empty input - just show prompt again
					if p.echo {
						if _, err := p.connection.Write([]byte("\r\n")); err != nil {
							Logger.Error("Player-IO: Failed to write newline", "error", err)
						}
						if _, err := p.connection.Write([]byte(p.prompt)); err != nil {
							Logger.Error("Player-IO: Failed to write prompt", "error", err)
						}
					}
				}

			case '\b', 127: // Backspace
				if p.inputBuffer.RemoveLast() && p.echo {
					p.connection.Write([]byte("\b \b"))
				}

			case '\x03': // Ctrl-C
				done <- errors.New("player interrupt")
				return

			default:
				// Filter input to only allow printable ASCII (32-126)
				if r >= 32 && r <= 126 {
					if p.inputBuffer.Append(r) && p.echo {
						p.connection.Write([]byte(string(r)))
					}
				}
			}
		}
	}
}

func (p *Player) handleOutput(ctx context.Context, done chan error) {
	defer func() {
		if r := recover(); r != nil {
			Logger.Warn("Recovered in handleOutput", "player", p.id, "recover", r)
			done <- fmt.Errorf("panic in output handler: %v", r)
		}
	}()

	for {
		select {
		case <-ctx.Done():
			done <- ctx.Err()
			return
		case msg, ok := <-p.commandOut:
			if !ok {
				Logger.Debug("Output channel closed", "player", p.id)
				done <- nil
				return
			}

			if _, err := p.connection.Write([]byte(wrapText(msg, p.consoleWidth))); err != nil {
				Logger.Error("Write error in output handler", "player", p.id, "error", err)
				done <- fmt.Errorf("write error: %w", err)
				return
			}
		}
	}
}

func wrapText(text string, width int) string {
	// Handle edge cases
	if width <= 0 {
		width = 80 // Default width
	}

	if len(text) == 0 {
		return text
	}

	var result strings.Builder
	// Pre-allocate a reasonable buffer size to avoid reallocations
	result.Grow(len(text) + len(text)/10) // Add 10% for possible line breaks

	// Split the text into lines
	lines := strings.Split(text, "\n")

	for i, line := range lines {
		// Preserve empty lines
		if len(strings.TrimSpace(line)) == 0 {
			result.WriteString(line)
			if i < len(lines)-1 {
				result.WriteString("\r\n")
			}
			continue
		}

		// Track position in the current line (excluding ANSI sequences)
		linePos := 0
		lastSpace := -1
		startSegment := 0
		inAnsiSequence := false

		// Process each character in the line
		for pos, char := range line {
			// Handle ANSI escape sequences (don't count toward width)
			if char == '\033' {
				inAnsiSequence = true
			}

			if inAnsiSequence {
				if char == 'm' {
					inAnsiSequence = false
				}
				continue // Don't count ANSI sequence chars toward width
			}

			// Track spaces for potential line breaks
			if char == ' ' {
				lastSpace = pos
			}

			// Increment visible character position
			linePos++

			// Check if we need to wrap
			if linePos > width {
				if lastSpace != -1 {
					// Break at the last space
					result.WriteString(line[startSegment:lastSpace])
					result.WriteString("\r\n")
					startSegment = lastSpace + 1
					linePos = pos - lastSpace
					lastSpace = -1
				} else {
					// No space found, force break
					result.WriteString(line[startSegment:pos])
					result.WriteString("\r\n")
					startSegment = pos
					linePos = 1
				}
			}
		}

		// Add the remainder of the line
		if startSegment < len(line) {
			result.WriteString(line[startSegment:])
		}

		// Add line break if not the last line
		if i < len(lines)-1 {
			result.WriteString("\r\n")
		}
	}

	return result.String()
}
