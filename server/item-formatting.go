/*
Eidolon Engine

Copyright 2024-2025 Jason Robinson

*/

package main

import (
	"fmt"
	"strings"
)

// formatItemDescription formats an item's description for display
func formatItemDescription(item *Item) string {
	var desc strings.Builder
	desc.WriteString(fmt.Sprintf("\n\r%s\n\r", item.name))
	desc.WriteString(item.description)
	desc.WriteString("\n\r")

	if item.wearable && len(item.wornOn) > 0 {
		desc.WriteString(fmt.Sprintf("It can be worn on: %s\n\r", strings.Join(item.wornOn, ", ")))
	}

	return desc.String()
}

// formatWornItem formats a worn item for inventory display
func formatWornItem(item *Item) string {
	item.mutex.RLock()
	defer item.mutex.RUnlock()

	description := fmt.Sprintf("  %s", item.name)
	if len(item.wornOn) > 0 {
		description += fmt.Sprintf(" (worn on %s)", strings.Join(item.wornOn, ", "))
	}
	description += "\n\r"

	return description
}

// formatCarriedItem formats a carried item for inventory display
func formatCarriedItem(item *Item) string {
	item.mutex.RLock()
	defer item.mutex.RUnlock()

	description := fmt.Sprintf("  %s", item.name)
	if item.stackable && item.quantity > 1 {
		description += fmt.Sprintf(" (x%d)", item.quantity)
	}
	description += "\n\r"

	return description
}
