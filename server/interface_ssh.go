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

// func PasswordCallBack(conn ssh.ConnMetadata, password []byte, sshInterface *Interface_SSH) (*ssh.Permissions, error) {

// 	authenticated, err := Authenticate(conn.User(), string(password), sshInterface)
// 	if err != nil {
// 		Logger.Info("Failed to authenticate player", "error", err)
// 		return nil, err
// 	}

// 	if authenticated {
// 		Logger.Info("Player authenticated", "player_name", conn.User())
// 		return nil, nil
// 	} else {
// 		Logger.Warn("Player failed to authenticate", "player_name", conn.User())
// 		return nil, fmt.Errorf("password rejected for %q", conn.User())
// 	}
// }

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

	sshInterface := &Interface_SSH{
		config:         config,
		server:         server,
		ctx:            ctx,
		cancel:         cancel,
		port:           config.SSH.Port,
		privateKeyPath: config.SSH.PrivateKeyPath,
		start:          time.Now(),
	}

	sshConfig := &ssh.ServerConfig{
		PasswordCallback: func(conn ssh.ConnMetadata, password []byte) (*ssh.Permissions, error) {
			return PasswordCallBack(conn, password, sshInterface)
		},
		NoClientAuth: false,

		// TODO: Add support for certificate authentication

		// TODO: Add MFA support using KeyboardInteractiveCallback

		BannerCallback: func(conn ssh.ConnMetadata) string {
			return art
		},
	}

	sshConfig.AddHostKey(private)

	sshInterface.sshConfig = sshConfig

	address := fmt.Sprintf(":%d", server.config.SSH.Port)

	listener, err := net.Listen("tcp", address)
	if err != nil {
		return nil, fmt.Errorf("failed to listen on port %d: %w", server.config.SSH.Port, err)
	}
	sshInterface.listener = listener

	return sshInterface, nil
}

// func (ssh_interface *Interface_SSH) handleConnection(conn net.Conn) {
// 	defer conn.Close()

// 	if err := conn.SetDeadline(time.Now().Add(30 * time.Second)); err != nil {
// 		Logger.Error("Failed to set handshake deadline", "error", err)
// 		return
// 	}

// 	sshConn, chans, reqs, err := ssh.NewServerConn(conn, ssh_interface.sshConfig)
// 	if err != nil {
// 		Logger.Error("SSH handshake failed", "error", err)
// 		return
// 	}
// 	defer sshConn.Close()

// 	if err := conn.SetDeadline(time.Time{}); err != nil {
// 		Logger.Error("Failed to clear deadline", "error", err)
// 		return
// 	}

// 	go ssh.DiscardRequests(reqs)

// 	for newChannel := range chans {
// 		if newChannel.ChannelType() != "session" {
// 			newChannel.Reject(ssh.UnknownChannelType, "unknown channel type")
// 			continue
// 		}

// 		channel, requests, err := newChannel.Accept()
// 		if err != nil {
// 			Logger.Error("Could not accept channel", "error", err)
// 			continue
// 		}

// 		player, err := NewPlayerSSH(ssh_interface.server, sshConn.User(), channel, ssh_interface.ctx)
// 		if err != nil {
// 			Logger.Error("Failed to create player", "error", err)
// 			channel.Close()
// 			continue
// 		}

// 		go player.RunSSH(requests)
// 	}
// }

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
	defer ssh_interface.listener.Close()

	for {
		select {
		case <-ssh_interface.server.ctx.Done():
			return
		case <-ssh_interface.ctx.Done():
			return
		default:
			conn, err := ssh_interface.listener.Accept()
			Logger.Info("New connection", "remote_addr", conn.RemoteAddr())
			if err != nil {
				if errors.Is(err, net.ErrClosed) {
					Logger.Warn("Listener closed", "error", err)
				}
				Logger.Error("Connection accept failed", "error", err)
				continue
			}
			go ssh_interface.handleConnection(conn)
		}
	}
}

func (ssh_interface *Interface_SSH) Stop() error {
	ssh_interface.cancel()
	return ssh_interface.listener.Close()
}

// parseDims parses terminal dimensions from the SSH payload.
func ParseDims(b []byte) (width, height int) {
	width = int(b[0])<<24 | int(b[1])<<16 | int(b[2])<<8 | int(b[3])
	height = int(b[4])<<24 | int(b[5])<<16 | int(b[6])<<8 | int(b[7])
	return width, height
}
