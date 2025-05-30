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
	"path/filepath"
	"sync"

	lua "github.com/yuin/gopher-lua"
)

// ScriptMetadata holds information about what a script handles
type ScriptMetadata struct {
	Commands []string          // Commands this script handles (e.g., ["pull", "push"])
	Events   []string          // Events this script handles (e.g., ["onCharacterEnter", "onRoomStart"])
	Periodic bool              // Whether script has periodic tick function
}

// ScriptManager manages Lua script execution for rooms
type ScriptManager struct {
	scripts  map[string]*lua.LState
	metadata map[string]*ScriptMetadata
	mutex    sync.RWMutex
}

// NewScriptManager creates a new script manager
func NewScriptManager() *ScriptManager {
	return &ScriptManager{
		scripts:  make(map[string]*lua.LState),
		metadata: make(map[string]*ScriptMetadata),
	}
}

// LoadScript loads a Lua script from the scripts directory
func (sm *ScriptManager) LoadScript(scriptID string) error {
	if scriptID == "" {
		return fmt.Errorf("empty script ID")
	}

	sm.mutex.Lock()
	defer sm.mutex.Unlock()

	// Check if script already loaded
	if _, exists := sm.scripts[scriptID]; exists {
		Logger.Debug("Script already loaded", "scriptID", scriptID)
		return nil
	}

	// Create new Lua state
	L := lua.NewState()
	
	// Load the script file
	scriptPath := filepath.Join("..", "scripts_lua", scriptID+".lua")
	if err := L.DoFile(scriptPath); err != nil {
		L.Close()
		return fmt.Errorf("failed to load script %s: %w", scriptID, err)
	}

	// Extract metadata from script
	metadata := &ScriptMetadata{
		Commands: []string{},
		Events:   []string{},
		Periodic: false,
	}

	// Check for SCRIPT_INFO table
	scriptInfo := L.GetGlobal("SCRIPT_INFO")
	if tbl, ok := scriptInfo.(*lua.LTable); ok {
		// Extract commands
		commands := L.GetField(tbl, "commands")
		if cmdTbl, ok := commands.(*lua.LTable); ok {
			cmdTbl.ForEach(func(_, v lua.LValue) {
				if str, ok := v.(lua.LString); ok {
					metadata.Commands = append(metadata.Commands, string(str))
				}
			})
		}

		// Extract events
		events := L.GetField(tbl, "events")
		if evtTbl, ok := events.(*lua.LTable); ok {
			evtTbl.ForEach(func(_, v lua.LValue) {
				if str, ok := v.(lua.LString); ok {
					metadata.Events = append(metadata.Events, string(str))
				}
			})
		}

		// Check for periodic
		periodic := L.GetField(tbl, "periodic")
		if b, ok := periodic.(lua.LBool); ok {
			metadata.Periodic = bool(b)
		}
	}

	sm.scripts[scriptID] = L
	sm.metadata[scriptID] = metadata
	
	Logger.Info("Script loaded successfully", 
		"scriptID", scriptID,
		"commands", metadata.Commands,
		"events", metadata.Events,
		"periodic", metadata.Periodic)
	
	return nil
}

// HandlesCommand checks if a script handles a specific command
func (sm *ScriptManager) HandlesCommand(scriptID string, command string) bool {
	sm.mutex.RLock()
	defer sm.mutex.RUnlock()

	metadata, exists := sm.metadata[scriptID]
	if !exists {
		return false
	}

	for _, cmd := range metadata.Commands {
		if cmd == command {
			return true
		}
	}
	return false
}

// UnloadScript unloads a Lua script
func (sm *ScriptManager) UnloadScript(scriptID string) {
	sm.mutex.Lock()
	defer sm.mutex.Unlock()

	if L, exists := sm.scripts[scriptID]; exists {
		L.Close()
		delete(sm.scripts, scriptID)
		delete(sm.metadata, scriptID)
		Logger.Info("Script unloaded", "scriptID", scriptID)
	}
}

// GetScript retrieves a loaded script state
func (sm *ScriptManager) GetScript(scriptID string) (*lua.LState, error) {
	sm.mutex.RLock()
	defer sm.mutex.RUnlock()

	L, exists := sm.scripts[scriptID]
	if !exists {
		return nil, fmt.Errorf("script %s not loaded", scriptID)
	}
	return L, nil
}

// ExecuteRoomFunction executes a specific function in a room's script
func (sm *ScriptManager) ExecuteRoomFunction(scriptID string, functionName string, room *Room, args ...lua.LValue) error {
	L, err := sm.GetScript(scriptID)
	if err != nil {
		return err
	}

	// Get the function from global scope
	fn := L.GetGlobal(functionName)
	if fn == lua.LNil {
		return fmt.Errorf("function %s not found in script %s", functionName, scriptID)
	}

	// Create a new thread for execution to avoid concurrency issues
	co, _ := L.NewThread()
	
	// Push function and arguments
	co.Push(fn)
	
	// Push room table as first argument
	roomTable := sm.createRoomTable(co, room)
	co.Push(roomTable)
	
	// Push additional arguments
	for _, arg := range args {
		co.Push(arg)
	}

	// Execute the function
	state, err, values := L.Resume(co, nil)
	if state == lua.ResumeError {
		return fmt.Errorf("error executing function %s: %w", functionName, err)
	}

	// Log any return values for debugging
	if len(values) > 0 {
		Logger.Debug("Script function returned values", 
			"scriptID", scriptID, 
			"function", functionName, 
			"valueCount", len(values))
	}

	return nil
}

// createRoomTable creates a Lua table representing a room
func (sm *ScriptManager) createRoomTable(L *lua.LState, room *Room) *lua.LTable {
	tbl := L.NewTable()
	
	// Basic room properties
	L.SetField(tbl, "id", lua.LNumber(room.roomID))
	L.SetField(tbl, "area", lua.LString(room.area))
	L.SetField(tbl, "title", lua.LString(room.title))
	L.SetField(tbl, "description", lua.LString(room.description))
	
	// Room methods will be added here
	
	return tbl
}

// ReloadScript reloads a script (unload then load)
func (sm *ScriptManager) ReloadScript(scriptID string) error {
	sm.UnloadScript(scriptID)
	return sm.LoadScript(scriptID)
}

// ListAvailableScripts returns a list of available script files
func (sm *ScriptManager) ListAvailableScripts() ([]string, error) {
	var scripts []string
	
	scriptsDir := filepath.Join("..", "scripts_lua")
	entries, err := os.ReadDir(scriptsDir)
	if err != nil {
		return nil, fmt.Errorf("failed to read scripts directory: %w", err)
	}

	for _, entry := range entries {
		if !entry.IsDir() && filepath.Ext(entry.Name()) == ".lua" {
			scriptID := entry.Name()[:len(entry.Name())-4] // Remove .lua extension
			scripts = append(scripts, scriptID)
		}
	}

	return scripts, nil
}

// Global script manager instance
var ScriptMgr *ScriptManager

// InitScriptManager initializes the global script manager
func InitScriptManager() {
	ScriptMgr = NewScriptManager()
	Logger.Info("Script manager initialized")
}