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

	"github.com/gofrs/uuid/v5"
	"golang.org/x/crypto/ssh"
	"golang.org/x/time/rate"
)

const (
	// Authentication rate limiting
	authLimitRate       = 1 // attempts per second per IP/user
	authLimitBurst      = 5 // burst size per IP/user
	globalAuthLimitRate = 10 // global attempts per second across all connections
	globalAuthLimitBurst = 50 // global burst size
	authTimeout         = 30 * time.Second
	authBanThreshold    = 10
	authBanDuration     = 15 * time.Minute
)

// AuthAttempt tracks authentication attempts and bans
type AuthAttempt struct {
	attempts int
	banUntil time.Time
	limiter  *rate.Limiter
}

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
	authAttempts   map[string]*AuthAttempt  // IP-based rate limiting
	userAttempts   map[string]*AuthAttempt  // Username-based rate limiting
	globalLimiter  *rate.Limiter            // Global rate limiter across all connections
	authMutex      sync.RWMutex
}

func PasswordCallBack(conn ssh.ConnMetadata, password []byte, sshInterface *Interface_SSH) (*ssh.Permissions, error) {
	clientIP := getClientIP(conn)
	username := strings.ToLower(conn.User())

	// Check global rate limit first (prevents DoS attacks)
	if !sshInterface.globalLimiter.Allow() {
		Logger.Warn("Global rate limit exceeded", "ip", clientIP, "username", username)
		if CloudWatchMetrics != nil {
			CloudWatchMetrics.SendRateLimitViolation("Global")
		}
		return nil, fmt.Errorf("server is experiencing high load, please try again later")
	}

	// Check if client IP is rate limited or banned
	if err := sshInterface.checkAuthLimit(clientIP); err != nil {
		Logger.Warn("Rate limited or banned client IP", "ip", clientIP, "error", err)
		return nil, err
	}

	// Check if username is rate limited or banned (prevents bypass via multiple IPs)
	if err := sshInterface.checkUserAuthLimit(username); err != nil {
		Logger.Warn("Rate limited or banned username", "username", username, "ip", clientIP, "error", err)
		return nil, err
	}

	// Sanitize password before use
	sanitizedPassword := string(password)
	if !isValidPassword(sanitizedPassword) {
		sshInterface.recordFailedAttempt(clientIP)
		sshInterface.recordFailedUserAttempt(username)
		return nil, fmt.Errorf("invalid password format")
	}

	authenticated, userUUID, err := Authenticate(conn.User(), sanitizedPassword, sshInterface)
	if err != nil {
		sshInterface.recordFailedAttempt(clientIP)
		sshInterface.recordFailedUserAttempt(username)
		Logger.Info("Failed to authenticate player", "error", err)
		// Return generic error to prevent user enumeration
		return nil, fmt.Errorf("authentication failed")
	}

	if authenticated {
		sshInterface.resetAuthAttempts(clientIP)
		sshInterface.resetUserAuthAttempts(username)
		Logger.Info("Player authenticated", "player_email", conn.User(), "player_uuid", userUUID.String())
		perms := &ssh.Permissions{
			Extensions: map[string]string{
				"uuid": userUUID.String(),
			},
		}
		return perms, nil
	} else {
		sshInterface.recordFailedAttempt(clientIP)
		sshInterface.recordFailedUserAttempt(username)
		Logger.Warn("Player failed to authenticate", "player_email", conn.User())
		return nil, fmt.Errorf("authentication failed")
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

	art := "Eidolon Engine\nCopyright 2024-2025 Jason Robinson\n"

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
		authAttempts:   make(map[string]*AuthAttempt),
		userAttempts:   make(map[string]*AuthAttempt),
		globalLimiter:  rate.NewLimiter(globalAuthLimitRate, globalAuthLimitBurst),
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
		AuthLogCallback: func(conn ssh.ConnMetadata, method string, err error) {
			if err != nil {
				Logger.Info("SSH auth attempt", "method", method, "success", false, "client", conn.RemoteAddr())
			} else {
				Logger.Info("SSH auth attempt", "method", method, "success", true, "client", conn.RemoteAddr())
			}
		},
	}

	sshConfig.AddHostKey(private)
	sshInterface.sshConfig = sshConfig

	// Try to create the listener
	address := fmt.Sprintf(":%d", server.config.SSH.Port)
	listener, err := net.Listen("tcp", address)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("failed to listen on port %d: %w", server.config.SSH.Port, err)
	}

	sshInterface.listener = listener

	// Start cleanup routine for expired auth attempts
	go sshInterface.cleanupAuthAttempts()

	return sshInterface, nil
}

func (ssh_interface *Interface_SSH) handleConnection(conn net.Conn, ctx context.Context) {
	defer conn.Close()

	// Set authentication timeout
	if err := conn.SetDeadline(time.Now().Add(authTimeout)); err != nil {
		Logger.Error("Failed to set handshake deadline", "error", err)
		return
	}

	sshConn, chans, reqs, err := ssh.NewServerConn(conn, ssh_interface.sshConfig)
	if err != nil {
		Logger.Error("SSH handshake failed", "remote_addr", conn.RemoteAddr(), "error", err)
		return
	}
	defer sshConn.Close()

	// Clear deadline after successful authentication
	if err := conn.SetDeadline(time.Time{}); err != nil {
		Logger.Error("Failed to clear deadline", "error", err)
		return
	}

	// Handle SSH requests with context cancellation
	go ssh_interface.handleSSHRequests(ctx, reqs)

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
	userUUID, err := uuid.FromString(userUUIDStr)
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

		player, err := NewPlayerSSH(ssh_interface.server, sshConn.User(), channel, ctx, userUUID)
		if err != nil {
			Logger.Error("Failed to create player", "error", err)
			channel.Close()
			continue
		}

		// Run player with connection context
		go ssh_interface.runPlayer(player, requests)
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
	go ssh_interface.listenForCancellation(done)

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

			// Create a child context for this connection
			connCtx, connCancel := context.WithCancel(ssh_interface.ctx)

			// Handle connection with context
			go ssh_interface.handleConnectionWithContext(conn, connCtx, connCancel)
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

// Rate limiting and ban functions
func (ssh_interface *Interface_SSH) checkAuthLimit(clientIP string) error {
	ssh_interface.authMutex.RLock()
	attempt, exists := ssh_interface.authAttempts[clientIP]
	ssh_interface.authMutex.RUnlock()

	if !exists {
		ssh_interface.authMutex.Lock()
		attempt = &AuthAttempt{
			limiter: rate.NewLimiter(authLimitRate, authLimitBurst),
		}
		ssh_interface.authAttempts[clientIP] = attempt
		ssh_interface.authMutex.Unlock()
	}

	// Check if client is banned
	if time.Now().Before(attempt.banUntil) {
		return fmt.Errorf("client is banned until %v", attempt.banUntil)
	}

	// Check rate limit
	if !attempt.limiter.Allow() {
		if CloudWatchMetrics != nil {
			CloudWatchMetrics.SendRateLimitViolation("IP")
		}
		return fmt.Errorf("rate limit exceeded")
	}

	return nil
}

func (ssh_interface *Interface_SSH) recordFailedAttempt(clientIP string) {
	ssh_interface.authMutex.Lock()
	defer ssh_interface.authMutex.Unlock()

	attempt, exists := ssh_interface.authAttempts[clientIP]
	if !exists {
		attempt = &AuthAttempt{
			limiter: rate.NewLimiter(authLimitRate, authLimitBurst),
		}
		ssh_interface.authAttempts[clientIP] = attempt
	}

	attempt.attempts++
	if attempt.attempts >= authBanThreshold {
		attempt.banUntil = time.Now().Add(authBanDuration)
		Logger.Warn("Client banned due to excessive failed attempts", "ip", clientIP, "ban_until", attempt.banUntil)
		
		// Send CloudWatch metric for IP ban
		if CloudWatchMetrics != nil {
			CloudWatchMetrics.SendAuthenticationBlock("IP", clientIP, authBanDuration)
		}
	}
}

func (ssh_interface *Interface_SSH) resetAuthAttempts(clientIP string) {
	ssh_interface.authMutex.Lock()
	defer ssh_interface.authMutex.Unlock()
	delete(ssh_interface.authAttempts, clientIP)
}

// Username-based rate limiting functions
func (ssh_interface *Interface_SSH) checkUserAuthLimit(username string) error {
	ssh_interface.authMutex.RLock()
	attempt, exists := ssh_interface.userAttempts[username]
	ssh_interface.authMutex.RUnlock()

	if !exists {
		ssh_interface.authMutex.Lock()
		attempt = &AuthAttempt{
			limiter: rate.NewLimiter(authLimitRate, authLimitBurst),
		}
		ssh_interface.userAttempts[username] = attempt
		ssh_interface.authMutex.Unlock()
	}

	// Check if user is banned
	if time.Now().Before(attempt.banUntil) {
		return fmt.Errorf("user is banned until %v", attempt.banUntil)
	}

	// Check rate limit
	if !attempt.limiter.Allow() {
		if CloudWatchMetrics != nil {
			CloudWatchMetrics.SendRateLimitViolation("Username")
		}
		return fmt.Errorf("rate limit exceeded")
	}

	return nil
}

func (ssh_interface *Interface_SSH) recordFailedUserAttempt(username string) {
	ssh_interface.authMutex.Lock()
	defer ssh_interface.authMutex.Unlock()

	attempt, exists := ssh_interface.userAttempts[username]
	if !exists {
		attempt = &AuthAttempt{
			limiter: rate.NewLimiter(authLimitRate, authLimitBurst),
		}
		ssh_interface.userAttempts[username] = attempt
	}

	attempt.attempts++
	if attempt.attempts >= authBanThreshold {
		attempt.banUntil = time.Now().Add(authBanDuration)
		Logger.Warn("User banned due to excessive failed attempts", "username", username, "ban_until", attempt.banUntil)
		
		// Send CloudWatch metric for username ban
		if CloudWatchMetrics != nil {
			CloudWatchMetrics.SendAuthenticationBlock("Username", username, authBanDuration)
		}
	}
}

func (ssh_interface *Interface_SSH) resetUserAuthAttempts(username string) {
	ssh_interface.authMutex.Lock()
	defer ssh_interface.authMutex.Unlock()
	delete(ssh_interface.userAttempts, username)
}

func (ssh_interface *Interface_SSH) cleanupAuthAttempts() {
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()

	for {
		select {
		case <-ssh_interface.ctx.Done():
			return
		case <-ticker.C:
			ssh_interface.authMutex.Lock()
			now := time.Now()
			// Clean up IP-based attempts
			for ip, attempt := range ssh_interface.authAttempts {
				if now.After(attempt.banUntil) && attempt.attempts < authBanThreshold {
					delete(ssh_interface.authAttempts, ip)
				}
			}
			// Clean up username-based attempts
			for username, attempt := range ssh_interface.userAttempts {
				if now.After(attempt.banUntil) && attempt.attempts < authBanThreshold {
					delete(ssh_interface.userAttempts, username)
				}
			}
			ssh_interface.authMutex.Unlock()
		}
	}
}

func getClientIP(conn ssh.ConnMetadata) string {
	addr := conn.RemoteAddr().String()
	idx := strings.LastIndex(addr, ":")
	if idx != -1 {
		return addr[:idx]
	}
	return addr
}

func isValidPassword(password string) bool {
	// Basic password validation - adjust as needed
	if len(password) < 8 || len(password) > 128 {
		return false
	}
	// Add additional validation as required
	return true
}

// parseDims parses terminal dimensions from the SSH payload.
func ParseDims(b []byte) (width, height int) {
	width = int(b[0])<<24 | int(b[1])<<16 | int(b[2])<<8 | int(b[3])
	height = int(b[4])<<24 | int(b[5])<<16 | int(b[6])<<8 | int(b[7])
	return width, height
}

// handleSSHRequests processes SSH requests for a connection
func (ssh_interface *Interface_SSH) handleSSHRequests(ctx context.Context, reqs <-chan *ssh.Request) {
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

// runPlayer runs a player's SSH session
func (ssh_interface *Interface_SSH) runPlayer(player *Player, requests <-chan *ssh.Request) {
	player.RunSSH(requests)
}

// listenForCancellation listens for context cancellation and closes the listener
func (ssh_interface *Interface_SSH) listenForCancellation(done chan struct{}) {
	select {
	case <-ssh_interface.server.ctx.Done():
		ssh_interface.listener.Close()
		close(done)
	case <-ssh_interface.ctx.Done():
		ssh_interface.listener.Close()
		close(done)
	}
}

// handleConnectionWithContext handles an SSH connection with proper context management
func (ssh_interface *Interface_SSH) handleConnectionWithContext(conn net.Conn, ctx context.Context, cancel context.CancelFunc) {
	defer cancel()
	ssh_interface.handleConnection(conn, ctx)
}
