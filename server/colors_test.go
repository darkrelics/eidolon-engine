/*
Eidolon Engine

Copyright 2024-2026 Jason E. Robinson

*/

package main

import (
	"fmt"
	"io"
	"log/slog"
	"testing"
)

func init() {
	// Initialize test logger if not already set
	if Logger == nil {
		Logger = slog.New(slog.NewTextHandler(io.Discard, &slog.HandlerOptions{
			Level: slog.LevelError,
		}))
	}
}

func TestColorMap(t *testing.T) {
	// Test that ColorMap contains expected colors
	expectedColors := []struct {
		name string
		code string
	}{
		{"black", "30"},
		{"red", "31"},
		{"green", "32"},
		{"yellow", "33"},
		{"blue", "34"},
		{"magenta", "35"},
		{"cyan", "36"},
		{"white", "37"},
		{"bright_black", "90"},
		{"bright_red", "91"},
		{"bright_green", "92"},
		{"bright_yellow", "93"},
		{"bright_blue", "94"},
		{"bright_magenta", "95"},
		{"bright_cyan", "96"},
		{"bright_white", "97"},
	}

	for _, tc := range expectedColors {
		t.Run(tc.name, func(t *testing.T) {
			code, exists := ColorMap[tc.name]
			if !exists {
				t.Errorf("ColorMap missing color %s", tc.name)
			}
			if code != tc.code {
				t.Errorf("ColorMap[%s] = %s, want %s", tc.name, code, tc.code)
			}
		})
	}

	// Test that ColorMap has exactly the expected number of entries
	if len(ColorMap) != len(expectedColors) {
		t.Errorf("ColorMap has %d entries, want %d", len(ColorMap), len(expectedColors))
	}
}

func TestApplyColor(t *testing.T) {
	tests := []struct {
		name      string
		colorName string
		text      string
		want      string
	}{
		{
			name:      "Valid color red",
			colorName: "red",
			text:      "Hello",
			want:      "\033[31mHello\033[0m",
		},
		{
			name:      "Valid color green",
			colorName: "green",
			text:      "World",
			want:      "\033[32mWorld\033[0m",
		},
		{
			name:      "Valid bright color",
			colorName: "bright_cyan",
			text:      "Test",
			want:      "\033[96mTest\033[0m",
		},
		{
			name:      "Invalid color name",
			colorName: "purple",
			text:      "NoColor",
			want:      "NoColor",
		},
		{
			name:      "Empty color name",
			colorName: "",
			text:      "Empty",
			want:      "Empty",
		},
		{
			name:      "Empty text",
			colorName: "blue",
			text:      "",
			want:      "\033[34m\033[0m",
		},
		{
			name:      "Special characters in text",
			colorName: "yellow",
			text:      "Hello\nWorld\t!",
			want:      "\033[33mHello\nWorld\t!\033[0m",
		},
		{
			name:      "Case sensitive color name",
			colorName: "RED",
			text:      "CaseSensitive",
			want:      "CaseSensitive", // Should not match
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ApplyColor(tt.colorName, tt.text)
			if got != tt.want {
				t.Errorf("ApplyColor(%q, %q) = %q, want %q",
					tt.colorName, tt.text, got, tt.want)
			}
		})
	}
}

func TestApplyColorFormat(t *testing.T) {
	// Test the ANSI escape sequence format
	result := ApplyColor("red", "X")
	expected := fmt.Sprintf("\033[%sm%s\033[0m", "31", "X")

	if result != expected {
		t.Errorf("ApplyColor format incorrect: got %q, want %q", result, expected)
	}
}

func BenchmarkApplyColor(b *testing.B) {
	// Benchmark with valid color
	b.Run("ValidColor", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			_ = ApplyColor("red", "BenchmarkText")
		}
	})

	// Benchmark with invalid color
	b.Run("InvalidColor", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			_ = ApplyColor("notacolor", "BenchmarkText")
		}
	})
}
