package main

import "testing"

func TestParseDims(t *testing.T) {
	tests := []struct {
		name       string
		payload    []byte
		wantWidth  int
		wantHeight int
	}{
		{
			name:       "Valid payload",
			payload:    []byte{0, 0, 0, 80, 0, 0, 0, 24},
			wantWidth:  80,
			wantHeight: 24,
		},
		{
			name:       "Short payload",
			payload:    []byte{1, 2, 3},
			wantWidth:  0,
			wantHeight: 0,
		},
		{
			name:       "Empty payload",
			payload:    nil,
			wantWidth:  0,
			wantHeight: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			w, h := ParseDims(tt.payload)
			if w != tt.wantWidth || h != tt.wantHeight {
				t.Errorf("ParseDims(%v) = (%d,%d), want (%d,%d)", tt.payload, w, h, tt.wantWidth, tt.wantHeight)
			}
		})
	}
}
