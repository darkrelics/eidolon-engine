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
	"errors"
	"fmt"
	"net"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"golang.org/x/crypto/ssh"
)

type Interface_SSH struct {
	config         *Configuration
	server         *Server
	ctx            context.Context
	cancel         context.CancelFunc
	mutex          sync.RWMutex
	start          time.Time
	port           uint16
	privateKeyPath string
	listener       net.Listener
	sshConfig      *ssh.ServerConfig
}

func PasswordCallBack(conn ssh.ConnMetadata, password []byte, sshInterface *Interface_SSH) (*ssh.Permissions, error) {
	authenticated, userUUID, err := Authenticate(conn.User(), string(password), sshInterface)
	if err != nil {
		Logger.Info("Failed to authenticate player", "error", err)
		return nil, err
	}

	if authenticated {
		Logger.Info("Player authenticated", "player_email", conn.User(), "player_uuid", userUUID.String())
		// Store the UUID string in the permissions so it can be retrieved later
		perms := &ssh.Permissions{
			Extensions: map[string]string{
				"uuid": userUUID.String(),
			},
		}
		return perms, nil
	} else {
		Logger.Warn("Player failed to authenticate", "player_email", conn.User())
		return nil, fmt.Errorf("password rejected for %q", conn.User())
	}
}

func NewSSHInterface(server *Server) (*Interface_SSH, error) {
	if !server.config.SSH.Enabled {
		return nil, fmt.Errorf("ssh interface is disabled")
	}

	privateBytes, err := os.ReadFile(server.config.SSH.PrivateKeyPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read private key: %w", err)
	}

	private, err := ssh.ParsePrivateKey(privateBytes)
	if err != nil {
		return nil, fmt.Errorf("failed to parse private key: %w", err)
	}

	art := "Edolon Engine\nCopyright 2024-2025 Jason Robinson\n"

	ctx, cancel := context.WithCancel(server.ctx)

	config := server.config

	// Create the SSH interface structure
	sshInterface := &Interface_SSH{
		config:         config,
		server:         server,
		ctx:            ctx,
		cancel:         cancel,
		port:           config.SSH.Port,
		privateKeyPath: config.SSH.PrivateKeyPath,
		start:          time.Now(),
	}

	// Set up the SSH server config
	sshConfig := &ssh.ServerConfig{
		PasswordCallback: func(conn ssh.ConnMetadata, password []byte) (*ssh.Permissions, error) {
			return PasswordCallBack(conn, password, sshInterface)
		},
		NoClientAuth: false,
		BannerCallback: func(conn ssh.ConnMetadata) string {
			return art
		},
	}

	sshConfig.AddHostKey(private)
	sshInterface.sshConfig = sshConfig

	// Try to create the listener
	address := fmt.Sprintf(":%d", server.config.SSH.Port)
	listener, err := net.Listen("tcp", address)
	if err != nil {
		// Cancel the context we created since we're returning an error
		cancel()
		return nil, fmt.Errorf("failed to listen on port %d: %w", server.config.SSH.Port, err)
	}

	// Only set the listener if we successfully created it
	sshInterface.listener = listener

	return sshInterface, nil
}

func (ssh_interface *Interface_SSH) handleConnection(conn net.Conn) {
	defer conn.Close()

	if err := conn.SetDeadline(time.Now().Add(30 * time.Second)); err != nil {
		Logger.Error("Failed to set handshake deadline", "error", err)
		return
	}

	sshConn, chans, reqs, err := ssh.NewServerConn(conn, ssh_interface.sshConfig)
	if err != nil {
		Logger.Error("SSH handshake failed", "error", err)
		return
	}
	defer sshConn.Close()

	if err := conn.SetDeadline(time.Time{}); err != nil {
		Logger.Error("Failed to clear deadline", "error", err)
		return
	}

	go ssh.DiscardRequests(reqs)

	// Extract UUID from permissions
	userUUIDStr := ""
	if sshConn.Permissions != nil && sshConn.Permissions.Extensions != nil {
		userUUIDStr = sshConn.Permissions.Extensions["uuid"]
	}

	if userUUIDStr == "" {
		Logger.Error("No UUID found for authenticated user", "email", sshConn.User())
		return
	}

	// Parse the UUID string
	userUUID, err := uuid.Parse(userUUIDStr)
	if err != nil {
		Logger.Error("Failed to parse UUID", "uuid_string", userUUIDStr, "error", err)
		return
	}

	for newChannel := range chans {
		if newChannel.ChannelType() != "session" {
			newChannel.Reject(ssh.UnknownChannelType, "unknown channel type")
			continue
		}

		channel, requests, err := newChannel.Accept()
		if err != nil {
			Logger.Error("Could not accept channel", "error", err)
			continue
		}

		player, err := NewPlayerSSH(ssh_interface.server, sshConn.User(), channel, ssh_interface.ctx, userUUID)
		if err != nil {
			Logger.Error("Failed to create player", "error", err)
			channel.Close()
			continue
		}

		go player.RunSSH(requests)
	}
}

func (ssh_interface *Interface_SSH) Run(errorChan chan error) {
	Logger.Info("Starting SSH interface", "port", ssh_interface.port)

	// Make sure listener is not nil
	if ssh_interface.listener == nil {
		Logger.Error("SSH listener is nil, cannot run interface")
		errorChan <- fmt.Errorf("SSH listener is nil")
		return
	}

	defer ssh_interface.listener.Close()

	// Create a done channel to signal the loop to exit
	done := make(chan struct{})

	// Set up a goroutine to listen for context cancellation
	go func() {
		select {
		case <-ssh_interface.server.ctx.Done():
			ssh_interface.listener.Close()
			close(done)
		case <-ssh_interface.ctx.Done():
			ssh_interface.listener.Close()
			close(done)
		}
	}()

	for {
		select {
		case <-done:
			return
		default:
			// Set a short timeout for Accept to ensure we can exit cleanly
			ssh_interface.listener.(*net.TCPListener).SetDeadline(time.Now().Add(1 * time.Second))

			conn, err := ssh_interface.listener.Accept()
			if err != nil {
				if errors.Is(err, net.ErrClosed) {
					Logger.Warn("Listener closed", "error", err)
					return
				}

				// Check for timeout error which we use to poll for context cancellation
				if netErr, ok := err.(net.Error); ok && netErr.Timeout() {
					// Check if context is done to exit
					select {
					case <-done:
						return
					default:
						// Just a timeout, continue
						continue
					}
				}

				Logger.Error("Connection accept failed", "error", err)
				continue
			}

			Logger.Info("New connection", "remote_addr", conn.RemoteAddr())
			go ssh_interface.handleConnection(conn)
		}
	}
}

func (ssh_interface *Interface_SSH) Stop() error {
	Logger.Info("Stopping SSH interface")

	// Cancel the context first
	ssh_interface.cancel()

	// Use a mutex to ensure we only close the listener once
	ssh_interface.mutex.Lock()
	defer ssh_interface.mutex.Unlock()

	// Check if listener is already closed
	if ssh_interface.listener != nil {
		// Try to close the listener but don't report error if it's already closed
		err := ssh_interface.listener.Close()
		if err != nil && !strings.Contains(err.Error(), "use of closed network connection") {
			return err
		}
		ssh_interface.listener = nil
	}

	return nil
}

// parseDims parses terminal dimensions from the SSH payload.
func ParseDims(b []byte) (width, height int) {
	width = int(b[0])<<24 | int(b[1])<<16 | int(b[2])<<8 | int(b[3])
	height = int(b[4])<<24 | int(b[5])<<16 | int(b[6])<<8 | int(b[7])
	return width, height
}
