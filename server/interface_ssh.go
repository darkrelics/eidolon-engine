package main

import (
	"context"
	"errors"
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

	ctx, cancel := context.WithCancel(context.Background())

	sshInterface := &Interface_SSH{
		config:         server.config,
		server:         server,
		ctx:            ctx,
		cancel:         cancel,
		port:           server.config.SSH.Port,
		privateKeyPath: server.config.SSH.PrivateKeyPath,
		start:          time.Now(),
	}

	sshConfig := &ssh.ServerConfig{
		PasswordCallback: func(conn ssh.ConnMetadata, password []byte) (*ssh.Permissions, error) {
			authenticated := Authenticate(conn.User(), string(password), sshInterface)
			if authenticated {
				Logger.Info("Player authenticated", "player_name", conn.User())
				return nil, nil
			}
			return nil, fmt.Errorf("authentication failed")
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

func (ssh_interface *Interface_SSH) Run() {
	Logger.Info("Starting SSH interface", "port", ssh_interface.port)
	defer ssh_interface.listener.Close()

	for {
		select {
		case <-ssh_interface.server.globalContext.Done():
			return
		case <-ssh_interface.server.context.Done():
			return
		case <-ssh_interface.ctx.Done():
			return
		default:
			conn, err := ssh_interface.listener.Accept()
			if err != nil {
				if errors.Is(err, net.ErrClosed) {
					return
				}
				Logger.Error("Connection accept failed", "error", err)
				continue
			}
			go ssh_interface.handleConnection(conn)
		}
	}
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

		player, err := NewPlayer(ssh_interface.server, sshConn.User(), channel, ssh_interface.ctx)
		if err != nil {
			Logger.Error("Failed to create player", "error", err)
			channel.Close()
			continue
		}

		go player.Run(requests)
	}
}

func (ssh_interface *Interface_SSH) Stop() error {
	ssh_interface.cancel()
	return nil
}
