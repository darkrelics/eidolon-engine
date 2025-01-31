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

type Configuration struct {
	ssh struct {
		enabled bool   `yaml:"Enabled"`
		port    uint16 `yaml:"Port"`
		key     string `yaml:"PrivateKeyPath"`
	} `yaml:"SSH"`
	aws struct {
		region string `yaml:"Region"`
	} `yaml:"AWS"`
	cognito struct {
		userPoolId     string `yaml:"UserPoolId"`
		clientSecret   string `yaml:"UserPoolClientSecret"`
		client         string `yaml:"UserPoolClientId"`
		userPoolDomain string `yaml:"UserPoolDomain"`
		userPoolArn    string `yaml:"UserPoolArn"`
	} `yaml:"Cognito"`
	game struct {
		balance         float64 `yaml:"Balance"`
		startingEssence uint16  `yaml:"StartingEssence"`
		startingHealth  uint16  `yaml:"StartingHealth"`
	} `yaml:"Game"`
	logging struct {
		application string `yaml:"ApplicationName"`
		logLevel    int    `yaml:"LogLevel"`
		logGroup    string `yaml:"LogGroup"`
		logStream   string `yaml:"LogStream"`
		namespace   string `yaml:"MetricNamespace"`
	} `yaml:"Logging"`
}

// LoadConfiguration reads the configuration file and unmarshals it into a Configuration struct.
func LoadConfiguration(configurationFile string) (*Configuration, error) {

	var config Configuration

	fmt.Println("Loading configuration from", configurationFile)

	data, err := os.ReadFile(configurationFile)
	if err != nil {
		return nil, fmt.Errorf("error reading configuration file '%s': %w", configurationFile, err)
	}

	// Add validation before unmarshaling
	if err := validateConfig(data); err != nil {
		return nil, fmt.Errorf("invalid configuration: %w", err)
	}

	// Unmarshal the configuration data into the Configuration struct
	err = yaml.Unmarshal(data, &config)
	if err != nil {
		fmt.Printf("Error unmarshaling config from '%s': %v\n", configurationFile, err)
		return nil, fmt.Errorf("error unmarshaling config from '%s': %w", configurationFile, err)
	}

	fmt.Println("Configuration loaded successfully")

	return &config, nil
}

// validateConfig validates the configuration data before unmarshaling it.
func validateConfig(data []byte) error {
	// Verify required fileds are present
	var configMap map[string]interface{}
	if err := yaml.Unmarshal(data, &configMap); err != nil {
		fmt.Printf("Error unmarshaling config data: %v", err)
		return fmt.Errorf("error unmarshaling config data: %w", err)
	}

	// Check for required fields
	required := []string{"SSH", "AWS", "Cognito", "Game", "Logging"}
	for _, field := range required {
		if _, ok := configMap[field]; !ok {
			return fmt.Errorf("missing required field: %s", field)
		}
	}
	return nil

	// Add more validation rules
}
