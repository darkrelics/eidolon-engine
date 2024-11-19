package main

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// loadConfiguration reads the configuration file and unmarshals it into a Configuration struct.
func loadConfiguration(configFile string) (Configuration, error) {
	var config Configuration

	data, err := os.ReadFile(configFile)
	if err != nil {
		return config, fmt.Errorf("error reading config file '%s': %w", configFile, err)
	}

	err = yaml.Unmarshal(data, &config)
	if err != nil {
		return config, fmt.Errorf("error unmarshalling config from '%s': %w", configFile, err)
	}

	return config, nil
}
