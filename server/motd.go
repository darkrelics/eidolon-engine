package main

import (
	"time"

	"github.com/google/uuid"
)

type MOTD struct {
	MotdID    uuid.UUID
	Active    bool
	Message   string
	CreatedAt time.Time
}

type MOTDData struct {
	MotdID    string `json:"MotdID" dynamodbav:"MotdID"`
	Active    bool   `json:"active" dynamodbav:"Active"`
	Message   string `json:"message" dynamodbav:"Message"`
	CreatedAt string `json:"createdAt" dynamodbav:"CreatedAt"`
}
