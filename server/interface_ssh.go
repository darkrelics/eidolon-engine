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
	Config         *Configuration
	Server         *Server
	GlobalContext  context.Context
	ServerContext  context.Context
	Context        context.Context
	Cancel         context.CancelFunc
	Mutex          sync.RWMutex
	StartTime      time.Time
	Port           uint16
	PrivateKeyPath string
	Listener       net.Listener
	Connections    uint64
	Database       *KeyPair
	SSHConfig      *ssh.ServerConfig
}

func NewSSHInterface(globalCtx context.Context, server *Server) (*Interface_SSH, error) {
	if !server.Config.SSH.Enabled {
		return nil, fmt.Errorf("ssh interface is disabled in configuration")
	}

	if server.Config.SSH.PrivateKeyPath == "" {
		return nil, fmt.Errorf("ssh private key path not configured")
	}

	privateBytes, err := os.ReadFile(server.Config.SSH.PrivateKeyPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read private key: %w", err)
	}

	private, err := ssh.ParsePrivateKey(privateBytes)
	if err != nil {
		return nil, fmt.Errorf("failed to parse private key: %w", err)
	}

	ctx, cancel := context.WithCancel(server.Context)

	sshInterface := &Interface_SSH{
		Config:         server.Config,
		Server:         server,
		GlobalContext:  globalCtx,
		ServerContext:  server.Context,
		Context:        ctx,
		Cancel:         cancel,
		Port:           server.Config.SSH.Port,
		PrivateKeyPath: server.Config.SSH.PrivateKeyPath,
		StartTime:      time.Now(),
		Database:       server.Database,
	}

	sshConfig := &ssh.ServerConfig{
		PasswordCallback: func(conn ssh.ConnMetadata, password []byte) (*ssh.Permissions, error) {
			authenticated := Authenticate(conn.User(), string(password), sshInterface)
			if authenticated {
				Logger.Info("Player authenticated", "player_name", conn.User())
				return nil, nil
			}
			Logger.Warn("Player failed authentication", "player_name", conn.User())
			return nil, fmt.Errorf("password rejected for %q", conn.User())
		},
	}
	sshConfig.AddHostKey(private)
	sshInterface.SSHConfig = sshConfig

	address := fmt.Sprintf(":%d", server.Config.SSH.Port)
	listener, err := net.Listen("tcp", address)
	if err != nil {
		return nil, fmt.Errorf("failed to listen on port %d: %w", server.Config.SSH.Port, err)
	}
	sshInterface.Listener = listener

	go monitorServerContext(server.Context, sshInterface)

	return sshInterface, nil
}

func monitorServerContext(serverCtx context.Context, sshInterface *Interface_SSH) {
	<-serverCtx.Done()
	sshInterface.Cancel()
}

func (ssh_interface *Interface_SSH) RunServer(server *Server) {
	Logger.Info("Starting SSH interface", "port", ssh_interface.Port)
	defer ssh_interface.Listener.Close()

	for {
		select {
		case <-ssh_interface.GlobalContext.Done():
			return
		case <-ssh_interface.ServerContext.Done():
			return
		case <-ssh_interface.Context.Done():
			return
		default:
			conn, err := ssh_interface.Listener.Accept()
			if err != nil {
				if errors.Is(err, net.ErrClosed) {
					return
				}
				Logger.Error("Connection accept failed", "error", err)
				continue
			}
			go handleConnection(ssh_interface.Context, ssh_interface, server, conn)
		}
	}
}

func handleConnection(ctx context.Context, ssh_interface *Interface_SSH, server *Server, conn net.Conn) {
	remoteAddr := conn.RemoteAddr().String()
	Logger.Info("New SSH connection", "remoteAddr", remoteAddr)
	defer conn.Close()

	if err := conn.SetDeadline(time.Now().Add(30 * time.Second)); err != nil {
		Logger.Error("Failed to set handshake deadline", "error", err, "remoteAddr", remoteAddr)
		return
	}

	sshConn, chans, reqs, err := ssh.NewServerConn(conn, ssh_interface.SSHConfig)
	if err != nil {
		Logger.Error("SSH handshake failed", "error", err, "remoteAddr", remoteAddr)
		return
	}
	defer sshConn.Close()

	if err := conn.SetDeadline(time.Time{}); err != nil {
		Logger.Error("Failed to clear deadline", "error", err, "remoteAddr", remoteAddr)
		return
	}

	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	go discardRequests(ctx, reqs)
	handleChannels(ctx, ssh_interface, server, sshConn, chans)
}

func discardRequests(ctx context.Context, reqs <-chan *ssh.Request) {
	for {
		select {
		case <-ctx.Done():
			return
		case req, ok := <-reqs:
			if !ok {
				return
			}
			if req.WantReply {
				req.Reply(false, nil)
			}
		}
	}
}

func handleChannels(ctx context.Context, ssh_interface *Interface_SSH, server *Server, sshConn *ssh.ServerConn, channels <-chan ssh.NewChannel) {
	playerName := sshConn.User()

	for {
		select {
		case <-ctx.Done():
			Logger.Info("Connection closing", "player", playerName)
			return

		case newChannel, ok := <-channels:
			if !ok {
				Logger.Info("Channel closed", "player", playerName)
				return
			}

			channel, requests, err := newChannel.Accept()
			if err != nil {
				Logger.Error("Channel accept failed", "error", err)
				continue
			}

			playerCtx, playerCancel := context.WithCancel(ctx)
			player := &Player{
				Server:        server,
				PlayerID:      playerName,
				ToPlayer:      make(chan string, 10),
				FromPlayer:    make(chan string, 10),
				Echo:          true,
				Connection:    channel,
				ConsoleWidth:  80,
				ConsoleHeight: 24,
				LoginTime:     time.Now(),
				Mutex:         sync.RWMutex{},
				Context:       playerCtx,
				Cancel:        playerCancel,
			}

			go handleSSHRequests(playerCtx, player, requests)
			if err := ssh_interface.Server.AddPlayer(player); err != nil {
				Logger.Error("Failed to add player", "error", err)
				playerCancel()
				continue
			}
		}
	}
}

func handleSSHRequests(ctx context.Context, player *Player, requests <-chan *ssh.Request) {
	for {
		select {
		case <-ctx.Done():
			return
		case req, ok := <-requests:
			if !ok {
				return
			}
			player.Mutex.Lock()
			processRequest(req, player)
			player.Mutex.Unlock()
		}
	}
}

func processRequest(req *ssh.Request, player *Player) {
	switch req.Type {
	case "shell":
		req.Reply(true, nil)
	case "pty-req":
		termLen := req.Payload[3]
		w, h := ParseDims(req.Payload[termLen+4:])
		player.ConsoleWidth = w
		player.ConsoleHeight = h
		req.Reply(true, nil)
	case "window-change":
		w, h := ParseDims(req.Payload)
		player.ConsoleWidth = w
		player.ConsoleHeight = h
	default:
		req.Reply(false, nil)
	}
}

func Authenticate(username, password string, ssh_interface *Interface_SSH) bool {
	authOutput, err := ssh_interface.Server.SignInUser(username, password)
	if err != nil {
		Logger.Error("Authentication failed", "username", username, "error", err)
		return false
	}

	if authOutput.AuthenticationResult == nil {
		Logger.Error("No authentication result", "username", username)
		return false
	}

	return true
}
