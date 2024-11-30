package game

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

// DisplayUnseenMOTDs shows unseen Messages of the Day to the player
func DisplayUnseenMOTDs(server *Server, player *Player) error {
	if server == nil {
		return fmt.Errorf("server instance is nil")
	}
	if player == nil {
		return fmt.Errorf("player instance is nil")
	}

	Logger.Debug("Displaying MOTDs for player", "playerName", player.PlayerID)

	// Protect player state during MOTD processing
	player.Mutex.Lock()
	defer player.Mutex.Unlock()

	defaultMOTDID, err := uuid.Parse("00000000-0000-0000-0000-000000000000")
	if err != nil {
		return fmt.Errorf("failed to parse default MOTD ID: %w", err)
	}

	// First display welcome message
	if err := displayWelcomeMessage(server, player, defaultMOTDID); err != nil {
		return fmt.Errorf("failed to display welcome message: %w", err)
	}

	// Then display other unseen MOTDs
	if err := displayUnseenMessages(server, player, defaultMOTDID); err != nil {
		return fmt.Errorf("failed to display unseen messages: %w", err)
	}

	// Save the updated player data
	if err := server.Database.WritePlayer(player); err != nil {
		return fmt.Errorf("failed to save player data after displaying MOTDs: %w", err)
	}

	return nil
}

// displayWelcomeMessage shows the default welcome message or a generic one
func displayWelcomeMessage(server *Server, player *Player, defaultMOTDID uuid.UUID) error {
	welcomeDisplayed := false

	server.Mutex.RLock()
	for _, motd := range server.ActiveMotDs {
		if motd != nil && motd.MotdID == defaultMOTDID {
			select {
			case player.ToPlayer <- fmt.Sprintf("\n\r%s\n\r", motd.Message):
				welcomeDisplayed = true
			default:
				server.Mutex.RUnlock()
				return fmt.Errorf("failed to send welcome MOTD to player %s: channel full", player.PlayerID)
			}
			break
		}
	}
	server.Mutex.RUnlock()

	if !welcomeDisplayed {
		select {
		case player.ToPlayer <- "\n\rWelcome to the game!\n\r":
			// Successfully sent generic welcome message
		default:
			return fmt.Errorf("failed to send generic welcome message to player %s: channel full", player.PlayerID)
		}
	}

	return nil
}

// displayUnseenMessages shows MOTDs that the player hasn't seen yet
func displayUnseenMessages(server *Server, player *Player, defaultMOTDID uuid.UUID) error {
	server.Mutex.RLock()
	defer server.Mutex.RUnlock()

	for _, motd := range server.ActiveMotDs {
		if motd == nil || motd.MotdID == defaultMOTDID {
			continue
		}

		if !hasSeenMOTD(player, motd.MotdID) {
			// Display the MOTD to the player
			select {
			case player.ToPlayer <- fmt.Sprintf("\n\r%s\n\r", motd.Message):
				// Successfully sent MOTD
			default:
				return fmt.Errorf("failed to send MOTD to player %s: channel full", player.PlayerID)
			}

			// Mark the MOTD as seen
			player.SeenMotD = append(player.SeenMotD, motd.MotdID)
		}
	}

	return nil
}

// hasSeenMOTD checks if the player has already seen a specific MOTD
func hasSeenMOTD(player *Player, motdID uuid.UUID) bool {
	for _, seenID := range player.SeenMotD {
		if seenID == motdID {
			return true
		}
	}
	return false
}
