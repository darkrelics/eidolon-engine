package events

import (
	"sync"

	"github.com/gofrs/uuid/v5"
)

type EventStore interface {
	Save(event Event) error
	Load(aggregateID uuid.UUID) ([]Event, error)
}

type MemoryEventStore struct {
	events map[uuid.UUID][]Event
	mutex  sync.RWMutex
}

func NewMemoryEventStore() *MemoryEventStore {
	return &MemoryEventStore{
		events: make(map[uuid.UUID][]Event),
	}
}

func (s *MemoryEventStore) Save(event Event) error {
	s.mutex.Lock()
	defer s.mutex.Unlock()

	aggID := event.GetAggregateID()
	s.events[aggID] = append(s.events[aggID], event)
	return nil
}

func (s *MemoryEventStore) Load(aggregateID uuid.UUID) ([]Event, error) {
	s.mutex.RLock()
	defer s.mutex.RUnlock()

	if events, ok := s.events[aggregateID]; ok {
		// Return a copy to prevent external modification
		result := make([]Event, len(events))
		copy(result, events)
		return result, nil
	}

	return []Event{}, nil
}
