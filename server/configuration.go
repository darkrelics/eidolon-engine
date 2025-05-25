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
	"fmt"
	"os"

	"github.com/goccy/go-yaml"
)

// Configuration holds all configuration settings
type Configuration struct {
	// AWS configuration settings
	AWS struct {
		Region string `yaml:"Region"`
	} `yaml:"AWS"`

	// Cognito authentication settings
	Cognito struct {
		UserPoolID       string `yaml:"UserPoolId"`
		UserPoolClientID string `yaml:"UserPoolClientId"`
		UserPoolDomain   string `yaml:"UserPoolDomain"`
		UserPoolARN      string `yaml:"UserPoolArn"`
	} `yaml:"Cognito"`

	// Game mechanics settings
	Game struct {
		Balance                 float64 `yaml:"Balance"`
		StartingEssence         uint16  `yaml:"StartingEssence"`
		StartingHealth          uint16  `yaml:"StartingHealth"`
		AutoSave                uint16  `yaml:"AutoSave"`
		NamesPath               string  `yaml:"NamesPath"`
		ObscenityPath           string  `yaml:"ObscenityPath"`
		TickIntervalSeconds     int     `yaml:"TickIntervalSeconds"`     // Game tick interval (default: 1)
		RoomItemCleanupSeconds  int     `yaml:"RoomItemCleanupSeconds"`  // Room item cleanup interval (default: 600)
		RoomUnloadSeconds       int     `yaml:"RoomUnloadSeconds"`       // Non-persistent room unload time (default: 3600)
		CommandTimeoutSeconds   int     `yaml:"CommandTimeoutSeconds"`   // Command processing timeout (default: 5)
		PlayerIdleTimeoutSeconds int    `yaml:"PlayerIdleTimeoutSeconds"` // Player idle timeout (default: 900)
	} `yaml:"Game"`

	// Logging and metrics settings
	Logging struct {
		ApplicationName string `yaml:"ApplicationName"`
		LogLevel        int    `yaml:"LogLevel"`
		LogGroup        string `yaml:"LogGroup"`
		LogStream       string `yaml:"LogStream"`
		MetricNamespace string `yaml:"MetricNamespace"`
	} `yaml:"Logging"`

	// SSH server settings
	SSH struct {
		Enabled                        bool   `yaml:"Enabled"`
		Port                           uint16 `yaml:"Port"`
		PrivateKeyPath                 string `yaml:"PrivateKeyPath"`
		AuthTimeoutSeconds             int    `yaml:"AuthTimeoutSeconds"`             // SSH auth timeout (default: 30)
		AuthBanDurationSeconds         int    `yaml:"AuthBanDurationSeconds"`         // Ban duration after failed auth (default: 900)
		AuthCleanupIntervalSeconds     int    `yaml:"AuthCleanupIntervalSeconds"`     // Auth attempts cleanup interval (default: 300)
		ConnectionAcceptTimeoutSeconds int    `yaml:"ConnectionAcceptTimeoutSeconds"` // Connection accept timeout (default: 1)
	} `yaml:"SSH"`

	// Server settings
	Server struct {
		SessionCleanupIntervalSeconds int `yaml:"SessionCleanupIntervalSeconds"` // Stale session cleanup interval (default: 300)
		SessionIdleTimeoutSeconds     int `yaml:"SessionIdleTimeoutSeconds"`     // Session idle timeout (default: 1800)
		ConsoleIdleTimeoutSeconds     int `yaml:"ConsoleIdleTimeoutSeconds"`     // Console idle timeout (default: 30)
	} `yaml:"Server"`

	// CloudWatch settings
	CloudWatch struct {
		MetricsIntervalSeconds int `yaml:"MetricsIntervalSeconds"` // Metrics submission interval (default: 60)
		MetricsTimeoutSeconds  int `yaml:"MetricsTimeoutSeconds"`  // Metrics submission timeout (default: 10)
		LogFlushTimeoutSeconds int `yaml:"LogFlushTimeoutSeconds"` // Log flush timeout (default: 3)
		ShutdownDrainSeconds   int `yaml:"ShutdownDrainSeconds"`   // Error channel drain timeout during shutdown (default: 2)
	} `yaml:"CloudWatch"`
}

// LoadConfiguration reads the configuration file and unmarshals it into a Configuration struct.
func LoadConfiguration(configurationFile string) (*Configuration, error) {

	fmt.Println("Loading configuration", "file", configurationFile)

	data, err := os.ReadFile(configurationFile)
	if err != nil {
		return nil, fmt.Errorf("error reading configuration file '%s': %w", configurationFile, err)
	}

	var config Configuration

	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("error parsing configuration from '%s': %w", configurationFile, err)
	}

	// Set defaults for any unspecified values
	setConfigDefaults(&config)

	if err := validateConfiguration(&config); err != nil {
		return nil, fmt.Errorf("invalid configuration: %w", err)
	}

	fmt.Println("Configuration loaded successfully")
	return &config, nil
}

// setConfigDefaults sets default values for configuration fields that weren't specified
func setConfigDefaults(config *Configuration) {
	// Game defaults
	if config.Game.TickIntervalSeconds <= 0 {
		config.Game.TickIntervalSeconds = 1
	}
	if config.Game.RoomItemCleanupSeconds <= 0 {
		config.Game.RoomItemCleanupSeconds = 600 // 10 minutes
	}
	if config.Game.RoomUnloadSeconds <= 0 {
		config.Game.RoomUnloadSeconds = 3600 // 60 minutes
	}
	if config.Game.CommandTimeoutSeconds <= 0 {
		config.Game.CommandTimeoutSeconds = 5
	}
	if config.Game.PlayerIdleTimeoutSeconds <= 0 {
		config.Game.PlayerIdleTimeoutSeconds = 900 // 15 minutes
	}

	// SSH defaults
	if config.SSH.AuthTimeoutSeconds <= 0 {
		config.SSH.AuthTimeoutSeconds = 30
	}
	if config.SSH.AuthBanDurationSeconds <= 0 {
		config.SSH.AuthBanDurationSeconds = 900 // 15 minutes
	}
	if config.SSH.AuthCleanupIntervalSeconds <= 0 {
		config.SSH.AuthCleanupIntervalSeconds = 300 // 5 minutes
	}
	if config.SSH.ConnectionAcceptTimeoutSeconds <= 0 {
		config.SSH.ConnectionAcceptTimeoutSeconds = 1
	}

	// Server defaults
	if config.Server.SessionCleanupIntervalSeconds <= 0 {
		config.Server.SessionCleanupIntervalSeconds = 300 // 5 minutes
	}
	if config.Server.SessionIdleTimeoutSeconds <= 0 {
		config.Server.SessionIdleTimeoutSeconds = 1800 // 30 minutes
	}
	if config.Server.ConsoleIdleTimeoutSeconds <= 0 {
		config.Server.ConsoleIdleTimeoutSeconds = 30
	}

	// CloudWatch defaults
	if config.CloudWatch.MetricsIntervalSeconds <= 0 {
		config.CloudWatch.MetricsIntervalSeconds = 60
	}
	if config.CloudWatch.MetricsTimeoutSeconds <= 0 {
		config.CloudWatch.MetricsTimeoutSeconds = 10
	}
	if config.CloudWatch.LogFlushTimeoutSeconds <= 0 {
		config.CloudWatch.LogFlushTimeoutSeconds = 3
	}
	if config.CloudWatch.ShutdownDrainSeconds <= 0 {
		config.CloudWatch.ShutdownDrainSeconds = 2
	}
}

// validateConfiguration performs validation checks on the configuration
func validateConfiguration(config *Configuration) error {

	fmt.Println("Validating configuration...")

	if config.AWS.Region == "" {
		return fmt.Errorf("AWS Region is required")
	}

	if config.Cognito.UserPoolID == "" {
		return fmt.Errorf("cognito userPoolId is required")
	}

	if config.Cognito.UserPoolClientID == "" {
		return fmt.Errorf("cognito userPoolClientId is required")
	}

	if config.Game.StartingHealth <= 0 {
		return fmt.Errorf("game startingHealth must be greater than 0")
	}

	if config.Game.Balance <= 0 {
		return fmt.Errorf("game balance must be greater than 0")
	}

	if config.SSH.Enabled {
		if config.SSH.Port == 0 {
			return fmt.Errorf("ssh port is required when ssh is enabled")
		}
		if config.SSH.PrivateKeyPath == "" {
			return fmt.Errorf("ssh privateKeyPath is required when ssh is enabled")
		}
	}

	if config.Logging.LogGroup == "" {
		return fmt.Errorf("logging logGroup is required")
	}

	if config.Logging.LogStream == "" {
		return fmt.Errorf("logging logStream is required")
	}

	if config.Logging.MetricNamespace == "" {
		return fmt.Errorf("logging metricNamespace is required")
	}

	fmt.Println("Configuration is valid")

	return nil
}
