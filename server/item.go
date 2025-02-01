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
	"time"

	"github.com/google/uuid"
)

type Item struct {
	id          uuid.UUID
	prototypeID uuid.UUID
	name        string
	description string
	mass        float64
	value       uint64
	stackable   bool
	maxStack    uint32
	quantity    uint32
	wearable    bool
	wornOn      []string
	verbs       map[string]string
	overrides   map[string]string
	traitMods   map[string]int8
	container   bool
	contents    []*Item
	isWorn      bool
	canPickUp   bool
	metadata    map[string]string
	mutex       sync.RWMutex
	lastEdited  time.Time
	lastSaved   time.Time
}

type ItemData struct {
	ItemID      string            `json:"itemId" dynamodbav:"ItemID"`
	PrototypeID string            `json:"prototypeID" dynamodbav:"PrototypeID"`
	Name        string            `json:"name" dynamodbav:"Name"`
	Description string            `json:"description" dynamodbav:"Description"`
	Mass        float64           `json:"mass" dynamodbav:"Mass"`
	Value       uint64            `json:"value" dynamodbav:"Value"`
	Stackable   bool              `json:"stackable" dynamodbav:"Stackable"`
	MaxStack    uint32            `json:"max_stack" dynamodbav:"MaxStack"`
	Quantity    uint32            `json:"quantity" dynamodbav:"Quantity"`
	Wearable    bool              `json:"wearable" dynamodbav:"Wearable"`
	WornOn      []string          `json:"worn_on" dynamodbav:"WornOn"`
	Verbs       map[string]string `json:"verbs" dynamodbav:"Verbs"`
	Overrides   map[string]string `json:"overrides" dynamodbav:"Overrides"`
	TraitMods   map[string]int8   `json:"trait_mods" dynamodbav:"TraitMods"`
	Container   bool              `json:"container" dynamodbav:"Container"`
	Contents    []string          `json:"contents" dynamodbav:"Contents"`
	IsWorn      bool              `json:"is_worn" dynamodbav:"IsWorn"`
	CanPickUp   bool              `json:"can_pick_up" dynamodbav:"CanPickUp"`
	Metadata    map[string]string `json:"metadata" dynamodbav:"Metadata"`
}

type Prototype struct {
	id          uuid.UUID
	name        string
	description string
	mass        float64
	value       uint64
	stackable   bool
	maxStack    uint32
	quantity    uint32
	wearable    bool
	wornOn      []string
	verbs       map[string]string
	overrides   map[string]string
	traitMods   map[string]int8
	container   bool
	contents    []uuid.UUID
	canPickUp   bool
	metadata    map[string]string
	mutex       sync.RWMutex
	lastEdited  time.Time
	lastSaved   time.Time
}

type PrototypeData struct {
	PrototypeID string            `json:"id" dynamodbav:"prototypeID"`
	Name        string            `json:"name" dynamodbav:"name"`
	Description string            `json:"description" dynamodbav:"description"`
	Mass        float64           `json:"mass" dynamodbav:"mass"`
	Value       uint64            `json:"value" dynamodbav:"value"`
	Stackable   bool              `json:"stackable" dynamodbav:"stackable"`
	MaxStack    uint32            `json:"max_stack" dynamodbav:"max_stack"`
	Quantity    uint32            `json:"quantity" dynamodbav:"quantity"`
	Wearable    bool              `json:"wearable" dynamodbav:"wearable"`
	WornOn      []string          `json:"worn_on" dynamodbav:"worn_on"`
	Verbs       map[string]string `json:"verbs" dynamodbav:"verbs"`
	Overrides   map[string]string `json:"overrides" dynamodbav:"overrides"`
	TraitMods   map[string]int8   `json:"trait_mods" dynamodbav:"trait_mods"`
	Container   bool              `json:"container" dynamodbav:"container"`
	Contents    []string          `json:"contents" dynamodbav:"contents"`
	CanPickUp   bool              `json:"can_pick_up" dynamodbav:"can_pick_up"`
	Metadata    map[string]string `json:"metadata" dynamodbav:"metadata"`
}
