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
	"net"
	"os"
	"sync"
	"time"

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

	authenticated, err := Authenticate(conn.User(), string(password), sshInterface)
	if err != nil {
		Logger.Info("Failed to authenticate player", "error", err)
		return nil, err
	}

	if authenticated {
		Logger.Info("Player authenticated", "player_name", conn.User())
		return nil, nil
	} else {
		Logger.Warn("Player failed to authenticate", "player_name", conn.User())
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

	art := `
	┏┓• ┓  ┓      ┏┓    •    
	┣ ┓┏┫┏┓┃┏┓┏┓  ┣ ┏┓┏┓┓┏┓┏┓
	┗┛┗┗┻┗┛┗┗┛┛┗  ┗┛┛┗┗┫┗┛┗┗
					   ┛     
	`

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

		player, err := NewPlayerSSH(ssh_interface.server, sshConn.User(), channel, ssh_interface.ctx)
		if err != nil {
			Logger.Error("Failed to create player", "error", err)
			channel.Close()
			continue
		}

		go player.Run(requests)
	}
}
