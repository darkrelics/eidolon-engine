/*
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

*/

package main

import (
	"fmt"
	"strings"
	"time"
	"unicode/utf8"

	"golang.org/x/crypto/ssh"
	"golang.org/x/time/rate"
)

const (
	// Authentication rate limiting
	authLimitRate        = 1  // attempts per second per IP/user
	authLimitBurst       = 5  // burst size per IP/user
	globalAuthLimitRate  = 10 // global attempts per second across all connections
	globalAuthLimitBurst = 50 // global burst size
	authTimeout          = 30 * time.Second
	authBanThreshold     = 10
	authBanDuration      = 15 * time.Minute
)

// AuthAttempt tracks authentication attempts and bans
type AuthAttempt struct {
	attempts int
	banUntil time.Time
	limiter  *rate.Limiter
}

// PasswordCallBack handles SSH password authentication with rate limiting
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

// Rate limiting and ban functions for IP addresses
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

// cleanupAuthAttempts periodically removes expired authentication attempts
func (ssh_interface *Interface_SSH) cleanupAuthAttempts() {
	RunWithPanicRecovery("ssh.cleanupAuthAttempts", func() {
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
	})
}

// isValidPassword validates password format and complexity
func isValidPassword(password string) bool {
	// Length check - AWS Cognito requires 8-256 characters
	if len(password) < 8 || len(password) > 128 {
		return false
	}

	// Ensure password is valid UTF-8
	if !utf8.ValidString(password) {
		return false
	}

	// Check for null bytes or dangerous control characters
	for _, r := range password {
		// Reject null bytes
		if r == 0 {
			return false
		}
		// Reject control characters except tab, newline, and carriage return
		// These are sometimes used in password managers
		if r < 32 && r != '\t' && r != '\n' && r != '\r' {
			return false
		}
		// Reject non-printable characters above ASCII range
		if r == 127 {
			return false
		}
	}

	// Password complexity checks to align with security best practices
	var hasUpper, hasLower, hasDigit, hasSpecial bool
	for _, r := range password {
		switch {
		case r >= 'A' && r <= 'Z':
			hasUpper = true
		case r >= 'a' && r <= 'z':
			hasLower = true
		case r >= '0' && r <= '9':
			hasDigit = true
		case r >= 33 && r <= 126 && (r < 'A' || r > 'Z') && (r < 'a' || r > 'z') && (r < '0' || r > '9'):
			hasSpecial = true
		}
	}

	// Require at least 3 of 4 character types for security
	complexity := 0
	if hasUpper {
		complexity++
	}
	if hasLower {
		complexity++
	}
	if hasDigit {
		complexity++
	}
	if hasSpecial {
		complexity++
	}

	// Require at least 3 different character types
	if complexity < 3 {
		return false
	}

	return true
}
