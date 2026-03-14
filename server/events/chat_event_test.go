package events

import (
	"testing"

	"github.com/gofrs/uuid/v5"
)

func TestChatEvent(t *testing.T) {
	aggID, _ := uuid.NewV4()
	msg := "Hello World"
	roomID := int64(123)
	charName := "TestChar"

	event := NewChatEvent(aggID, msg, roomID, charName)

	if event.GetAggregateID() != aggID {
		t.Errorf("Expected AggregateID %s, got %s", aggID, event.GetAggregateID())
	}

	if event.GetType() != EventTypeChat {
		t.Errorf("Expected Type %s, got %s", EventTypeChat, event.GetType())
	}

	if event.Data.Message != msg {
		t.Errorf("Expected Message %s, got %s", msg, event.Data.Message)
	}

	if event.Data.TargetRoomID != roomID {
		t.Errorf("Expected RoomID %d, got %d", roomID, event.Data.TargetRoomID)
	}
}

func TestMemoryEventStore(t *testing.T) {
	store := NewMemoryEventStore()
	aggID, _ := uuid.NewV4()
	event := NewChatEvent(aggID, "Test", 1, "Char")

	err := store.Save(event)
	if err != nil {
		t.Fatalf("Failed to save event: %v", err)
	}

	loadedEvents, err := store.Load(aggID)
	if err != nil {
		t.Fatalf("Failed to load events: %v", err)
	}

	if len(loadedEvents) != 1 {
		t.Errorf("Expected 1 event, got %d", len(loadedEvents))
	}

	loadedEvent := loadedEvents[0].(*ChatEvent)
	if loadedEvent.Data.Message != "Test" {
		t.Errorf("Expected message 'Test', got '%s'", loadedEvent.Data.Message)
	}
}
