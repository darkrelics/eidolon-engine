/*
Eidolon Engine

Copyright 2024-2026 Jason E. Robinson

*/

package main

import (
	"fmt"
)

// ColorMap maps color names to ANSI color codes.
var ColorMap = map[string]string{
	"black":          "30",
	"red":            "31",
	"green":          "32",
	"yellow":         "33",
	"blue":           "34",
	"magenta":        "35",
	"cyan":           "36",
	"white":          "37",
	"bright_black":   "90",
	"bright_red":     "91",
	"bright_green":   "92",
	"bright_yellow":  "93",
	"bright_blue":    "94",
	"bright_magenta": "95",
	"bright_cyan":    "96",
	"bright_white":   "97",
}

// ApplyColor applies the specified color to the text if the color exists in ColorMap.
func ApplyColor(colorName, text string) string {
	Logger.Debug("Applying color to text", "colorName", colorName, "text", text)

	if colorCode, exists := ColorMap[colorName]; exists {
		return fmt.Sprintf("\033[%sm%s\033[0m", colorCode, text)
	}
	// Return the original text if colorName is not found
	return text
}
