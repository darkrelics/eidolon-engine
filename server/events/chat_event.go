package events

import (
	"github.com/gofrs/uuid/v5"
)

type ChatEventData struct {
	Message       string    `json:"message"`
	TargetRoomID  int64     `json:"targetRoomID"`
	CharacterName string    `json:"characterName"`
}

type ChatEvent struct {
	BaseEvent
	Data ChatEventData
}

func NewChatEvent(aggregateID uuid.UUID, message string, targetRoomID int64, characterName string) *ChatEvent {
	return &ChatEvent{
		BaseEvent: NewBaseEvent(aggregateID, EventTypeChat),
		Data: ChatEventData{
			Message:       message,
			TargetRoomID:  targetRoomID,
			CharacterName: characterName,
		},
	}
}

func (e *ChatEvent) GetData() interface{} {
	return e.Data
}
