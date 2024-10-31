package main

import (
	"fmt"
	"os"

	"github.com/robinje/multi-user-dungeon/core"
	"gopkg.in/yaml.v3"
)

// loadConfiguration reads the configuration file and unmarshals it into a Configuration struct.
func loadConfiguration(configFile string) (core.Configuration, error) {
	var config core.Configuration

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
