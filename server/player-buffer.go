/*
Eidolon Engine

Copyright 2024-2026 Jason E. Robinson

*/

package main

import (
	"sync"
)

// InputBuffer provides thread-safe operations for storing and manipulating runes
type InputBuffer struct {
	buffer []rune
	mutex  sync.Mutex
}

func NewInputBuffer() *InputBuffer {
	return &InputBuffer{
		buffer: make([]rune, 0, 1024),
	}
}

func (ib *InputBuffer) Append(r rune) bool {
	ib.mutex.Lock()
	defer ib.mutex.Unlock()

	if len(ib.buffer) >= 240 {
		return false
	}
	ib.buffer = append(ib.buffer, r)
	return true
}

func (ib *InputBuffer) RemoveLast() bool {
	ib.mutex.Lock()
	defer ib.mutex.Unlock()

	if len(ib.buffer) == 0 {
		return false
	}
	ib.buffer = ib.buffer[:len(ib.buffer)-1]
	return true
}

func (ib *InputBuffer) Clear() {
	ib.mutex.Lock()
	defer ib.mutex.Unlock()
	ib.buffer = ib.buffer[:0]
}

func (ib *InputBuffer) String() string {
	ib.mutex.Lock()
	defer ib.mutex.Unlock()
	return string(ib.buffer)
}

func (ib *InputBuffer) Length() int {
	ib.mutex.Lock()
	defer ib.mutex.Unlock()
	return len(ib.buffer)
}
