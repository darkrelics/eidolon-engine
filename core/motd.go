package core

import (
	"fmt"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/aws/aws-sdk-go/service/dynamodb/dynamodbattribute"
	"github.com/google/uuid"
)

func (k *KeyPair) GetAllMOTDs() ([]*MOTD, error) {
	input := &dynamodb.ScanInput{
		TableName:        aws.String("motd"),
		FilterExpression: aws.String("active = :active"),
		ExpressionAttributeValues: map[string]*dynamodb.AttributeValue{
			":active": {
				BOOL: aws.Bool(true),
			},
		},
	}

	result, err := k.db.Scan(input)
	if err != nil {
		return nil, fmt.Errorf("error scanning MOTDs: %w", err)
	}

	var motds []*MOTD
	err = dynamodbattribute.UnmarshalListOfMaps(result.Items, &motds)
	if err != nil {
		return nil, fmt.Errorf("error unmarshalling MOTDs: %w", err)
	}

	return motds, nil
}

func DisplayUnseenMOTDs(server *Server, player *Player) {
	if server == nil || player == nil {
		Logger.Error("Invalid server or player object")
		return
	}

	Logger.Debug("Displaying MOTDs for player", "playerName", player.PlayerID)

	defaultMOTDID, _ := uuid.Parse("00000000-0000-0000-0000-000000000000")
	welcomeDisplayed := false

	// First, look for and display the welcome message
	for _, motd := range server.ActiveMotDs {
		if motd != nil && motd.MotdID == defaultMOTDID {
			player.ToPlayer <- fmt.Sprintf("\n\r%s\n\r", motd.Message)
			welcomeDisplayed = true
			break
		}
	}

	// If no welcome message was found, display a generic one
	if !welcomeDisplayed {
		player.ToPlayer <- "\n\rWelcome to the game!\n\r"
	}

	// Then display other unseen MOTDs
	for _, motd := range server.ActiveMotDs {
		if motd == nil || motd.MotdID == defaultMOTDID {
			continue
		}

		// Check if the player has already seen this MOTD
		seenMOTD := false
		for _, seenID := range player.SeenMotD {
			if seenID == motd.MotdID {
				seenMOTD = true
				break
			}
		}

		if !seenMOTD {
			// Display the MOTD to the player
			player.ToPlayer <- fmt.Sprintf("\n\r%s\n\r", motd.Message)

			// Mark the MOTD as seen
			player.SeenMotD = append(player.SeenMotD, motd.MotdID)
		}
	}

	// Save the updated player data
	err := server.Database.WritePlayer(player)
	if err != nil {
		Logger.Error("Error saving player data after displaying MOTDs", "playerName", player.PlayerID, "error", err)
	}
}
