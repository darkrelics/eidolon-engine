package main

type Archetype struct {
	ArchetypeName string             `json:"ArchetypeName" dynamodbav:"archetypeName"`
	Description   string             `json:"Description" dynamodbav:"description"`
	Attributes    map[string]float64 `json:"Attributes" dynamodbav:"attributes"`
	Abilities     map[string]float64 `json:"Abilities" dynamodbav:"abilities"`
	StartRoom     int64              `json:"StartRoom" dynamodbav:"startRoom"`
}
