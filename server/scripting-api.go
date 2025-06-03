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
	"strings"
	"sync"
	"time"

	"github.com/gofrs/uuid/v5"
	lua "github.com/yuin/gopher-lua"
	"golang.org/x/text/cases"
	"golang.org/x/text/language"
)

// RegisterRoomAPI registers all room-related functions for Lua scripts
func (sm *ScriptManager) RegisterRoomAPI(L *lua.LState, room *Room) {
	if L == nil {
		Logger.Error("Cannot register room API: Lua state is nil")
		return
	}
	if room == nil {
		Logger.Error("Cannot register room API: room is nil")
		return
	}

	Logger.Info("Registering room API for script", "roomID", room.roomID, "scriptID", room.scriptID)

	// Create the eidolon global table
	eidolon := L.NewTable()
	L.SetGlobal("eidolon", eidolon)

	// Room functions
	roomAPI := L.NewTable()
	L.SetField(eidolon, "room", roomAPI)

	// Register room methods
	L.SetField(roomAPI, "sendMessage", L.NewFunction(sm.luaRoomSendMessage(room)))
	L.SetField(roomAPI, "sendToCharacter", L.NewFunction(sm.luaRoomSendToCharacter(room)))
	L.SetField(roomAPI, "getCharacters", L.NewFunction(sm.luaRoomGetCharacters(room)))
	L.SetField(roomAPI, "getItems", L.NewFunction(sm.luaRoomGetItems(room)))
	L.SetField(roomAPI, "addItem", L.NewFunction(sm.luaRoomAddItem(room)))
	L.SetField(roomAPI, "removeItem", L.NewFunction(sm.luaRoomRemoveItem(room)))
	L.SetField(roomAPI, "setDescription", L.NewFunction(sm.luaRoomSetDescription(room)))
	L.SetField(roomAPI, "getExits", L.NewFunction(sm.luaRoomGetExits(room)))

	Logger.Debug("Room API functions registered", "roomID", room.roomID)

	// Character functions
	charAPI := L.NewTable()
	L.SetField(eidolon, "character", charAPI)

	// Logger functions
	logAPI := L.NewTable()
	L.SetField(eidolon, "log", logAPI)
	L.SetField(logAPI, "info", L.NewFunction(sm.luaLogInfo))
	L.SetField(logAPI, "debug", L.NewFunction(sm.luaLogDebug))
	L.SetField(logAPI, "error", L.NewFunction(sm.luaLogError))

	Logger.Debug("All API functions registered successfully", "roomID", room.roomID)
}

// luaRoomSendMessage sends a message to all characters in the room
func (sm *ScriptManager) luaRoomSendMessage(room *Room) lua.LGFunction {
	return func(L *lua.LState) int {
		if room == nil {
			Logger.Warn("luaRoomSendMessage called with nil room")
			return 0
		}

		message := L.CheckString(1)

		// Add proper formatting to the message
		formattedMessage := fmt.Sprintf("\n\r%s\n\r", message)

		// Use the standard room message function which handles prompts
		SendRoomMessage(room, formattedMessage, nil)

		return 0
	}
}

// luaRoomSendToCharacter sends a message to a specific character
func (sm *ScriptManager) luaRoomSendToCharacter(room *Room) lua.LGFunction {
	return func(L *lua.LState) int {
		if room == nil {
			Logger.Warn("luaRoomSendToCharacter called with nil room")
			L.Push(lua.LFalse)
			return 1
		}

		charName := L.CheckString(1)
		message := L.CheckString(2)

		room.mutex.RLock()
		var targetChar *Character
		for _, char := range room.characters {
			if char != nil && char.name == charName {
				targetChar = char
				break
			}
		}
		room.mutex.RUnlock()

		if targetChar != nil && targetChar.player != nil {
			// Add proper formatting to the message
			formattedMessage := fmt.Sprintf("\n\r%s\n\r", message)

			if SafeSendString(targetChar.player.commandOut, formattedMessage, targetChar.name) {
				// Send prompt after message
				SafeSendString(targetChar.player.commandOut, targetChar.prompt, targetChar.name)
			}
			L.Push(lua.LTrue)
		} else {
			L.Push(lua.LFalse)
		}

		return 1
	}
}

// luaRoomGetCharacters returns a table of character names in the room
func (sm *ScriptManager) luaRoomGetCharacters(room *Room) lua.LGFunction {
	return func(L *lua.LState) int {
		if room == nil {
			Logger.Warn("luaRoomGetCharacters called with nil room")
			L.Push(L.NewTable())
			return 1
		}

		tbl := L.NewTable()

		room.mutex.RLock()
		i := 1
		for _, char := range room.characters {
			if char == nil {
				Logger.Warn("Found nil character in room", "roomID", room.roomID)
				continue
			}
			charTable := L.NewTable()
			L.SetField(charTable, "name", lua.LString(char.name))
			L.SetField(charTable, "state", lua.LString(char.charState))
			L.SetField(charTable, "hidden", lua.LBool(char.IsHidden()))
			L.RawSetInt(tbl, i, charTable)
			i++
		}
		room.mutex.RUnlock()

		L.Push(tbl)
		return 1
	}
}

// luaRoomGetItems returns a table of items in the room
func (sm *ScriptManager) luaRoomGetItems(room *Room) lua.LGFunction {
	return func(L *lua.LState) int {
		tbl := L.NewTable()

		room.mutex.RLock()
		i := 1
		for _, item := range room.items {
			itemTable := L.NewTable()
			L.SetField(itemTable, "name", lua.LString(item.name))
			L.SetField(itemTable, "description", lua.LString(item.description))
			L.SetField(itemTable, "id", lua.LString(item.id.String()))
			L.RawSetInt(tbl, i, itemTable)
			i++
		}
		room.mutex.RUnlock()

		L.Push(tbl)
		return 1
	}
}

// luaRoomAddItem adds an item to the room
func (sm *ScriptManager) luaRoomAddItem(room *Room) lua.LGFunction {
	return func(L *lua.LState) int {
		name := L.CheckString(1)
		description := L.CheckString(2)

		// Create a basic item
		itemID := uuid.Must(uuid.NewV7())
		item := &Item{
			id:          itemID,
			name:        name,
			description: description,
			mass:        1.0,
			value:       0,
			stackable:   false,
			quantity:    1,
			wearable:    false,
			container:   false,
			canPickUp:   true,
			mutex:       sync.RWMutex{},
			lastEdited:  time.Now(),
			lastSaved:   time.Now(),
		}

		room.mutex.Lock()
		room.items[item.id] = item
		room.mutex.Unlock()

		L.Push(lua.LString(item.id.String()))
		return 1
	}
}

// luaRoomRemoveItem removes an item from the room by name
func (sm *ScriptManager) luaRoomRemoveItem(room *Room) lua.LGFunction {
	return func(L *lua.LState) int {
		itemName := L.CheckString(1)

		room.mutex.Lock()
		var removed bool
		for id, item := range room.items {
			if item.name == itemName {
				delete(room.items, id)
				removed = true
				break
			}
		}
		room.mutex.Unlock()

		L.Push(lua.LBool(removed))
		return 1
	}
}

// luaRoomSetDescription sets the room's description
func (sm *ScriptManager) luaRoomSetDescription(room *Room) lua.LGFunction {
	return func(L *lua.LState) int {
		description := L.CheckString(1)

		room.mutex.Lock()
		room.description = description
		room.mutex.Unlock()

		return 0
	}
}

// luaRoomGetExits returns a table of exits from the room
func (sm *ScriptManager) luaRoomGetExits(room *Room) lua.LGFunction {
	return func(L *lua.LState) int {
		tbl := L.NewTable()

		room.mutex.RLock()
		i := 1
		for _, exit := range room.exits {
			exitTable := L.NewTable()
			L.SetField(exitTable, "direction", lua.LString(exit.direction))
			L.SetField(exitTable, "targetRoomID", lua.LNumber(exit.targetRoomID))
			L.RawSetInt(tbl, i, exitTable)
			i++
		}
		room.mutex.RUnlock()

		L.Push(tbl)
		return 1
	}
}

// Logging functions
func (sm *ScriptManager) luaLogInfo(L *lua.LState) int {
	message := L.CheckString(1)
	Logger.Info("Lua script", "message", message)
	return 0
}

func (sm *ScriptManager) luaLogDebug(L *lua.LState) int {
	message := L.CheckString(1)
	Logger.Debug("Lua script", "message", message)
	return 0
}

func (sm *ScriptManager) luaLogError(L *lua.LState) int {
	message := L.CheckString(1)
	Logger.Error("Lua script", "message", message)
	return 0
}

// ExecuteRoomCommand attempts to execute a command through the room's script
func (sm *ScriptManager) ExecuteRoomCommand(room *Room, cmd *CommandRequest) (bool, error) {
	if room.scriptID == "" || !room.scriptActive {
		return false, nil // No script, command not handled
	}

	// Get the command verb
	verb := strings.ToLower(cmd.Verb)

	Logger.Info("ExecuteRoomCommand called", "roomID", room.roomID, "scriptID", room.scriptID, "verb", verb)

	L, err := sm.GetRoomScript(room.roomID)
	if err != nil {
		Logger.Warn("Script not loaded for room", "roomID", room.roomID, "scriptID", room.scriptID, "error", err)
		return false, nil // Script should have been loaded during room startup
	}

	Logger.Info("Script retrieved successfully", "scriptID", room.scriptID, "luaState", L != nil)

	// Build function name from command verb (e.g., "pull" -> "onCommandPull")
	caser := cases.Title(language.English)
	functionName := "onCommand" + caser.String(verb)

	Logger.Info("Looking for function in script", "scriptID", room.scriptID, "functionName", functionName)

	// Check if handler exists
	handler := L.GetGlobal(functionName)
	if handler == lua.LNil {
		Logger.Info("No handler found for command in script", "scriptID", room.scriptID, "functionName", functionName)
		return false, nil // No handler for this command
	}

	Logger.Info("Found command handler in script", "scriptID", room.scriptID, "functionName", functionName)

	// Create character table
	charTable := L.NewTable()
	L.SetField(charTable, "name", lua.LString(cmd.Character.name))
	L.SetField(charTable, "id", lua.LString(cmd.Character.id.String()))

	// Create args table
	argsTable := L.NewTable()
	for i, arg := range cmd.Args {
		L.RawSetInt(argsTable, i+1, lua.LString(arg))
	}

	// Use CallByParam for safer execution
	err = L.CallByParam(lua.P{
		Fn:      handler,
		NRet:    1, // Expecting one return value (handled or not)
		Protect: true,
	}, charTable, argsTable)

	if err != nil {
		return false, fmt.Errorf("error executing command handler %s: %w", functionName, err)
	}

	// Check if command was handled (function should return true/false)
	ret := L.Get(-1) // Get the return value
	L.Pop(1)         // Remove it from stack

	if handled, ok := ret.(lua.LBool); ok {
		return bool(handled), nil
	}

	return false, nil
}

// ExecuteRoomEvent executes a room event handler if it exists
func (sm *ScriptManager) ExecuteRoomEvent(room *Room, eventName string, args ...interface{}) error {
	if room == nil {
		Logger.Warn("ExecuteRoomEvent called with nil room", "event", eventName)
		return nil
	}

	if room.scriptID == "" || !room.scriptActive {
		Logger.Debug("ExecuteRoomEvent: No script or inactive", "roomID", room.roomID, "scriptID", room.scriptID, "scriptActive", room.scriptActive)
		return nil
	}

	Logger.Debug("ExecuteRoomEvent: Getting script", "roomID", room.roomID, "scriptID", room.scriptID)
	L, err := sm.GetRoomScript(room.roomID)
	if err != nil {
		Logger.Debug("ExecuteRoomEvent: Script not loaded, attempting to load", "roomID", room.roomID, "scriptID", room.scriptID, "error", err)
		// Try to load the script if not loaded
		if loadErr := sm.LoadScriptForRoom(room.scriptID, room); loadErr != nil {
			Logger.Warn("Failed to load script for room event", "roomID", room.roomID, "event", eventName, "error", loadErr)
			return fmt.Errorf("failed to load script: %w", loadErr)
		}
		L, err = sm.GetRoomScript(room.roomID)
		if err != nil {
			Logger.Warn("Failed to get script after loading", "roomID", room.roomID, "event", eventName, "error", err)
			return err
		}
	}

	Logger.Debug("ExecuteRoomEvent: Got script", "roomID", room.roomID, "scriptID", room.scriptID, "luaState", L != nil)

	// Ensure we have a valid Lua state before proceeding
	if L == nil {
		Logger.Error("Lua state is nil after loading script", "roomID", room.roomID, "scriptID", room.scriptID, "event", eventName)
		return fmt.Errorf("lua state is nil for script %s", room.scriptID)
	}

	Logger.Debug("ExecuteRoomEvent: Checking for handler", "roomID", room.roomID, "event", eventName)

	// Check if the event handler exists
	handler := L.GetGlobal(eventName)
	if handler == lua.LNil {
		// No handler for this event, which is fine
		Logger.Debug("No handler found for room event", "roomID", room.roomID, "event", eventName)
		return nil
	}

	// Check handler type
	if handler.Type() != lua.LTFunction {
		Logger.Error("Handler is not a function", "roomID", room.roomID, "event", eventName, "type", handler.Type().String())
		return fmt.Errorf("handler %s is not a function, got %s", eventName, handler.Type().String())
	}

	Logger.Debug("ExecuteRoomEvent: Found handler, executing", "roomID", room.roomID, "event", eventName)

	// Convert arguments to Lua values
	luaArgs := make([]lua.LValue, len(args))
	for i, arg := range args {
		Logger.Debug("ExecuteRoomEvent: Converting arg", "roomID", room.roomID, "event", eventName, "argIndex", i, "argType", fmt.Sprintf("%T", arg))
		luaArgs[i] = sm.convertToLuaValue(L, arg)
		Logger.Debug("ExecuteRoomEvent: Converted arg", "roomID", room.roomID, "event", eventName, "argIndex", i, "luaType", luaArgs[i].Type().String())
	}

	// Add defer to catch any panics
	defer func() {
		if r := recover(); r != nil {
			Logger.Error("Panic during Lua execution", "roomID", room.roomID, "event", eventName, "panic", r)
		}
	}()

	// Use CallByParam which is safer than manual thread management
	err = L.CallByParam(lua.P{
		Fn:      handler,
		NRet:    0,
		Protect: true,
	}, luaArgs...)

	if err != nil {
		Logger.Error("Error executing room event", "roomID", room.roomID, "event", eventName, "error", err)
		return fmt.Errorf("error executing event %s: %w", eventName, err)
	}

	Logger.Debug("Successfully executed room event", "roomID", room.roomID, "event", eventName)
	return nil
}

// convertToLuaValue converts Go values to Lua values
func (sm *ScriptManager) convertToLuaValue(L *lua.LState, value interface{}) lua.LValue {
	if L == nil {
		Logger.Error("convertToLuaValue called with nil LState")
		return lua.LNil
	}

	switch v := value.(type) {
	case *Character:
		if v == nil {
			return lua.LNil
		}
		// Create character table
		table := L.NewTable()
		if table == nil {
			Logger.Error("Failed to create Lua table for character")
			return lua.LNil
		}
		table.RawSetString("name", lua.LString(v.name))
		table.RawSetString("id", lua.LString(v.id.String()))
		return table
	case string:
		return lua.LString(v)
	case int:
		return lua.LNumber(v)
	case bool:
		return lua.LBool(v)
	case nil:
		return lua.LNil
	default:
		// For other types, try to convert to string
		return lua.LString(fmt.Sprintf("%v", value))
	}
}
