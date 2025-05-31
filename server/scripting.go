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
	"context"
	"fmt"
	"io"
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	lua "github.com/yuin/gopher-lua"
)

// ScriptMetadata holds information about what a script handles
type ScriptMetadata struct {
	Commands []string // Commands this script handles (e.g., ["pull", "push"])
	Events   []string // Events this script handles (e.g., ["onCharacterEnter", "onRoomStart"])
	Periodic bool     // Whether script has periodic tick function
}

// ScriptCache holds cached script content and metadata
type ScriptCache struct {
	content  string
	metadata *ScriptMetadata
	lastUsed time.Time
}

// ScriptManager manages Lua script execution for rooms
type ScriptManager struct {
	scripts      map[string]*lua.LState
	scriptCache  map[string]*ScriptCache
	s3Client     *s3.Client
	bucketName   string
	bucketPrefix string
	mutex        sync.RWMutex
}

// NewScriptManager creates a new script manager
func NewScriptManager(cfg *Configuration) (*ScriptManager, error) {
	ctx := context.Background()

	// Create AWS config
	awsConfig, err := config.LoadDefaultConfig(ctx,
		config.WithRegion(cfg.AWS.Region),
		config.WithRetryMode(aws.RetryModeStandard),
		config.WithRetryMaxAttempts(3),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create AWS config: %w", err)
	}

	// Create S3 client
	s3Client := s3.NewFromConfig(awsConfig)

	// Set default prefix if not specified
	prefix := cfg.Game.ScriptsS3Prefix
	if prefix == "" {
		prefix = "scripts"
	}
	if !strings.HasSuffix(prefix, "/") {
		prefix += "/"
	}

	return &ScriptManager{
		scripts:      make(map[string]*lua.LState),
		scriptCache:  make(map[string]*ScriptCache),
		s3Client:     s3Client,
		bucketName:   cfg.Game.ScriptsS3Bucket,
		bucketPrefix: prefix,
	}, nil
}

// LoadScript loads a Lua script from S3 cache or S3 bucket
func (sm *ScriptManager) LoadScript(scriptID string) error {
	return sm.LoadScriptForRoom(scriptID, nil)
}

// LoadScriptForRoom loads a Lua script and optionally registers it for a specific room
func (sm *ScriptManager) LoadScriptForRoom(scriptID string, room *Room) error {
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

	// Get script content from cache or S3
	scriptContent, metadata, err := sm.getScriptFromCacheOrS3(scriptID)
	if err != nil {
		return fmt.Errorf("failed to get script %s: %w", scriptID, err)
	}

	// Create new Lua state
	L := lua.NewState()

	// Load the script content
	Logger.Info("Compiling Lua script", "scriptID", scriptID, "contentLength", len(scriptContent))
	if err := L.DoString(scriptContent); err != nil {
		Logger.Error("Lua script compilation failed", "scriptID", scriptID, "error", err)
		L.Close()
		return fmt.Errorf("failed to load script %s: %w", scriptID, err)
	}
	Logger.Info("Lua script compiled successfully", "scriptID", scriptID)

	// Extract metadata from script if not already cached
	if metadata == nil {
		metadata = sm.extractScriptMetadata(L)
	}

	// Ensure cache entry exists and has metadata
	if cached, exists := sm.scriptCache[scriptID]; exists {
		cached.metadata = metadata
	} else {
		// Create cache entry if it doesn't exist
		sm.scriptCache[scriptID] = &ScriptCache{
			content:  scriptContent,
			metadata: metadata,
			lastUsed: time.Now(),
		}
	}

	sm.scripts[scriptID] = L

	// Register room API if room is provided
	if room != nil {
		// TODO: Temporarily disable room API registration for debugging
		Logger.Info("Skipping room API registration for debugging", "scriptID", scriptID, "roomID", room.roomID)
	}

	Logger.Info("Script loaded successfully",
		"scriptID", scriptID,
		"commands", metadata.Commands,
		"events", metadata.Events,
		"periodic", metadata.Periodic)

	// Log cache state for debugging
	if cached, exists := sm.scriptCache[scriptID]; exists {
		commandCount := 0
		if cached.metadata != nil {
			commandCount = len(cached.metadata.Commands)
		}
		Logger.Debug("Script cache updated", "scriptID", scriptID, "hasMetadata", cached.metadata != nil,
			"commandCount", commandCount)
	}

	return nil
}

// getScriptFromCacheOrS3 retrieves script content and metadata from cache or S3
func (sm *ScriptManager) getScriptFromCacheOrS3(scriptID string) (string, *ScriptMetadata, error) {
	// Check cache first
	if cached, exists := sm.scriptCache[scriptID]; exists {
		cached.lastUsed = time.Now()
		Logger.Debug("Script found in cache", "scriptID", scriptID)
		return cached.content, cached.metadata, nil
	}

	// Not in cache, load from S3
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	key := sm.bucketPrefix + scriptID + ".lua"
	output, err := sm.s3Client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(sm.bucketName),
		Key:    aws.String(key),
	})
	if err != nil {
		return "", nil, fmt.Errorf("failed to get script from S3: %w", err)
	}
	defer output.Body.Close()

	// Read the script content
	content, err := io.ReadAll(output.Body)
	if err != nil {
		return "", nil, fmt.Errorf("failed to read script content: %w", err)
	}

	scriptContent := string(content)

	// Cache the script
	sm.scriptCache[scriptID] = &ScriptCache{
		content:  scriptContent,
		metadata: nil, // Will be populated after Lua execution
		lastUsed: time.Now(),
	}

	Logger.Info("Script loaded from S3", "scriptID", scriptID, "bucket", sm.bucketName, "key", key)
	return scriptContent, nil, nil
}

// extractScriptMetadata extracts metadata from a loaded Lua state
func (sm *ScriptManager) extractScriptMetadata(L *lua.LState) *ScriptMetadata {
	metadata := &ScriptMetadata{
		Commands: []string{},
		Events:   []string{},
		Periodic: false,
	}

	// Check for SCRIPT_INFO table
	scriptInfo := L.GetGlobal("SCRIPT_INFO")
	if tbl, ok := scriptInfo.(*lua.LTable); ok {
		Logger.Info("Found SCRIPT_INFO table in Lua script")
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

		Logger.Info("Extracted script metadata", "commands", metadata.Commands, "events", metadata.Events, "periodic", metadata.Periodic)
	} else {
		Logger.Error("SCRIPT_INFO table not found or invalid in Lua script")
	}

	return metadata
}

// HandlesCommand checks if a script handles a specific command
func (sm *ScriptManager) HandlesCommand(scriptID string, command string) bool {
	sm.mutex.RLock()
	defer sm.mutex.RUnlock()

	// Check cache first for metadata
	if cached, exists := sm.scriptCache[scriptID]; exists && cached.metadata != nil {
		for _, cmd := range cached.metadata.Commands {
			if cmd == command {
				return true
			}
		}
		return false
	}

	// If script is loaded but metadata not in cache, try to get it from the loaded script
	if L, exists := sm.scripts[scriptID]; exists {
		// Script is loaded, extract metadata
		metadata := sm.extractScriptMetadata(L)
		// Update cache with metadata (note: this is read-locked, so we can't update here)
		for _, cmd := range metadata.Commands {
			if cmd == command {
				return true
			}
		}
		return false
	}

	// Script not loaded - we can't determine if it handles the command without loading it
	// For now, return false to avoid loading scripts just to check
	// The script will be loaded when ExecuteRoomCommand is called
	Logger.Debug("Script not loaded, cannot check if it handles command", "scriptID", scriptID, "command", command)
	return false
}

// UnloadScript unloads a Lua script but keeps cache
func (sm *ScriptManager) UnloadScript(scriptID string) {
	sm.mutex.Lock()
	defer sm.mutex.Unlock()

	if L, exists := sm.scripts[scriptID]; exists {
		L.Close()
		delete(sm.scripts, scriptID)
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

// ClearCache removes old entries from the script cache
func (sm *ScriptManager) ClearCache(maxAge time.Duration) {
	sm.mutex.Lock()
	defer sm.mutex.Unlock()

	now := time.Now()
	for scriptID, cached := range sm.scriptCache {
		if now.Sub(cached.lastUsed) > maxAge {
			delete(sm.scriptCache, scriptID)
			Logger.Debug("Removed script from cache", "scriptID", scriptID)
		}
	}
}

// GetCacheStats returns statistics about the script cache
func (sm *ScriptManager) GetCacheStats() (int, int) {
	sm.mutex.RLock()
	defer sm.mutex.RUnlock()

	return len(sm.scriptCache), len(sm.scripts)
}

// Global script manager instance
var ScriptMgr *ScriptManager

// InitScriptManager initializes the global script manager
func InitScriptManager(cfg *Configuration) error {
	var err error
	ScriptMgr, err = NewScriptManager(cfg)
	if err != nil {
		Logger.Error("NewScriptManager failed", "error", err)
		return fmt.Errorf("failed to initialize script manager: %w", err)
	}
	if ScriptMgr == nil {
		Logger.Error("ScriptMgr is nil after successful NewScriptManager - this should not happen")
		return fmt.Errorf("script manager is nil after initialization")
	}
	Logger.Info("Script manager initialized successfully", "bucket", cfg.Game.ScriptsS3Bucket, "prefix", cfg.Game.ScriptsS3Prefix)
	return nil
}
