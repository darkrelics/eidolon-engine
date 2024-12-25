package main

import (
	"fmt"
	"os"
	"strings"

	"gopkg.in/yaml.v3"
)

type Configuration struct {
	SSH struct {
		Enabled        bool   `yaml:"Enabled"`
		Port           uint16 `yaml:"Port"`
		PrivateKeyPath string `yaml:"PrivateKeyPath"`
	} `yaml:"SSH"`
	Aws struct {
		Region string `yaml:"Region"`
	} `yaml:"Aws"`
	Cognito struct {
		UserPoolID     string `yaml:"UserPoolId"`
		ClientSecret   string `yaml:"UserPoolClientSecret"`
		ClientID       string `yaml:"UserPoolClientId"`
		UserPoolDomain string `yaml:"UserPoolDomain"`
		UserPoolArn    string `yaml:"UserPoolArn"`
	} `yaml:"Cognito"`
	Game struct {
		Balance         float64 `yaml:"Balance"`
		AutoSave        uint16  `yaml:"AutoSave"`
		StartingEssence uint16  `yaml:"StartingEssence"`
		StartingHealth  uint16  `yaml:"StartingHealth"`
	} `yaml:"Game"`
	Logging struct {
		ApplicationName string `yaml:"ApplicationName"`
		LogLevel        int    `yaml:"LogLevel"`
		LogGroup        string `yaml:"LogGroup"`
		LogStream       string `yaml:"LogStream"`
		MetricNamespace string `yaml:"MetricNamespace"`
	} `yaml:"Logging"`
}

// loadConfiguration reads the configuration file and unmarshals it into a Configuration struct.
func loadConfiguration(configFile string) (*Configuration, error) {
	var config Configuration

	data, err := os.ReadFile(configFile)
	if err != nil {
		return nil, fmt.Errorf("error reading config file '%s': %w", configFile, err)
	}

	// Add validation before unmarshaling
	if err := validateConfigData(data); err != nil {
		return nil, fmt.Errorf("invalid configuration: %w", err)
	}

	err = yaml.Unmarshal(data, &config)
	if err != nil {
		return nil, fmt.Errorf("error unmarshalling config from '%s': %w", configFile, err)
	}

	return &config, nil
}

func validateConfigData(data []byte) error {
	// Verify required fields exist
	var rawConfig map[string]interface{}
	if err := yaml.Unmarshal(data, &rawConfig); err != nil {
		return err
	}

	required := []string{"Aws.Region", "Game.Balance", "Game.AutoSave"}
	for _, field := range required {
		parts := strings.Split(field, ".")
		value := rawConfig
		for _, part := range parts {
			if v, ok := value[part].(map[string]interface{}); ok {
				value = v
				continue
			}
			if _, ok := value[part]; !ok {
				return fmt.Errorf("missing required field: %s", field)
			}
		}
	}
	return nil
}
