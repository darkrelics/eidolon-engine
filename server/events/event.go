package events

import (
	"time"

	"github.com/gofrs/uuid/v5"
)

type EventType string

const (
	EventTypeChat EventType = "chat"
)

type Event interface {
	GetID() uuid.UUID
	GetTimestamp() time.Time
	GetAggregateID() uuid.UUID
	GetType() EventType
	GetData() interface{}
}

type BaseEvent struct {
	ID          uuid.UUID
	Timestamp   time.Time
	AggregateID uuid.UUID
	Type        EventType
}

func (e *BaseEvent) GetID() uuid.UUID {
	return e.ID
}

func (e *BaseEvent) GetTimestamp() time.Time {
	return e.Timestamp
}

func (e *BaseEvent) GetAggregateID() uuid.UUID {
	return e.AggregateID
}

func (e *BaseEvent) GetType() EventType {
	return e.Type
}

func (e *BaseEvent) GetData() interface{} {
	return nil
}

func NewBaseEvent(aggregateID uuid.UUID, eventType EventType) BaseEvent {
	id, _ := uuid.NewV4()
	return BaseEvent{
		ID:          id,
		Timestamp:   time.Now(),
		AggregateID: aggregateID,
		Type:        eventType,
	}
}
