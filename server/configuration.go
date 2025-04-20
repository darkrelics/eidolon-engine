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
	AWS struct {
		Region string `yaml:"Region"`
	} `yaml:"AWS"`

	// Cognito authentication settings
	Cognito struct {
		UserPoolID string `yaml:"UserPoolId"`
		// Removed UserPoolClientSecret
		UserPoolClientID string `yaml:"UserPoolClientId"`
		UserPoolDomain   string `yaml:"UserPoolDomain"`
		UserPoolARN      string `yaml:"UserPoolArn"`
	} `yaml:"Cognito"`

	// Game mechanics settings
	Game struct {
		Balance         float64 `yaml:"Balance"`
		StartingEssence uint16  `yaml:"StartingEssence"`
		StartingHealth  uint16  `yaml:"StartingHealth"`
		AutoSave        uint16  `yaml:"AutoSave"`
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
		Enabled        bool   `yaml:"Enabled"`
		Port           uint16 `yaml:"Port"`
		PrivateKeyPath string `yaml:"PrivateKeyPath"`
	} `yaml:"SSH"`
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

	if err := validateConfiguration(&config); err != nil {
		return nil, fmt.Errorf("invalid configuration: %w", err)
	}

	fmt.Println("Configuration loaded successfully")
	return &config, nil
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

	// Removed check for UserPoolClientSecret

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
