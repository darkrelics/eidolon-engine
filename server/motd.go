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
