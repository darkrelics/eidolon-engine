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
