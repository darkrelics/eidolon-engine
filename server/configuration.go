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

	"gopkg.in/yaml.v3"
)

// Configuration holds all configuration settings
type Configuration struct {
	// AWS configuration settings
	aws struct {
		region string `yaml:"Region"`
	} `yaml:"AWS"`

	// Cognito authentication settings
	cognito struct {
		userPoolID           string `yaml:"UserPoolId"`
		userPoolClientSecret string `yaml:"UserPoolClientSecret"`
		userPoolClientID     string `yaml:"UserPoolClientId"`
		userPoolDomain       string `yaml:"UserPoolDomain"`
		userPoolARN          string `yaml:"UserPoolArn"`
	} `yaml:"Cognito"`

	// Game mechanics settings
	game struct {
		balance         float64 `yaml:"Balance"`
		startingEssence uint16  `yaml:"StartingEssence"`
		startingHealth  uint16  `yaml:"StartingHealth"`
		autoSave        uint16  `yaml:"AutoSave"`
	} `yaml:"Game"`

	// Logging and metrics settings
	logging struct {
		applicationName string `yaml:"ApplicationName"`
		logLevel        int    `yaml:"LogLevel"`
		logGroup        string `yaml:"LogGroup"`
		logStream       string `yaml:"LogStream"`
		metricNamespace string `yaml:"MetricNamespace"`
	} `yaml:"Logging"`

	// SSH server settings
	ssh struct {
		enabled        bool   `yaml:"Enabled"`
		port           uint16 `yaml:"Port"`
		privateKeyPath string `yaml:"PrivateKeyPath"`
	} `yaml:"SSH"`
}

// LoadConfiguration reads the configuration file and unmarshals it into a Configuration struct.
func LoadConfiguration(configurationFile string) (*Configuration, error) {
	Logger.Info("Loading configuration", "file", configurationFile)

	data, err := os.ReadFile(configurationFile)
	if err != nil {
		return nil, fmt.Errorf("error reading configuration file '%s': %w", configurationFile, err)
	}

	var config Configuration

	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("error parsing configuration from '%s': %w", configurationFile, err)
	}

	if err := validateConfiguration(&config); err != nil {
		return nil, fmt.Errorf("invalid configuration: %w", err)
	}

	Logger.Info("Configuration loaded successfully")
	return &config, nil
}

// validateConfiguration performs validation checks on the configuration
func validateConfiguration(config *Configuration) error {
	if config.aws.region == "" {
		return fmt.Errorf("AWS Region is required")
	}

	if config.cognito.userPoolID == "" {
		return fmt.Errorf("cognito userPoolId is required")
	}

	if config.cognito.userPoolClientID == "" {
		return fmt.Errorf("cognito userPoolClientId is required")
	}

	if config.cognito.userPoolClientSecret == "" {
		return fmt.Errorf("cognito userPoolClientSecret is required")
	}

	if config.game.startingHealth == 0 {
		return fmt.Errorf("game startingHealth must be greater than 0")
	}

	if config.game.startingEssence == 0 {
		return fmt.Errorf("game startingEssence must be greater than 0")
	}

	if config.game.balance <= 0 {
		return fmt.Errorf("game balance must be greater than 0")
	}

	if config.ssh.enabled {
		if config.ssh.port == 0 {
			return fmt.Errorf("ssh port is required when ssh is enabled")
		}
		if config.ssh.privateKeyPath == "" {
			return fmt.Errorf("ssh privateKeyPath is required when ssh is enabled")
		}
	}

	if config.logging.logGroup == "" {
		return fmt.Errorf("logging logGroup is required")
	}

	if config.logging.logStream == "" {
		return fmt.Errorf("logging logStream is required")
	}

	if config.logging.metricNamespace == "" {
		return fmt.Errorf("logging metricNamespace is required")
	}

	return nil
}
