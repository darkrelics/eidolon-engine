/*
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

*/

package main

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type KeyPair struct {
	db          *dynamodb.Client
	maxRetries  int
	baseBackoff time.Duration
	tableNames  map[string]string
}

func NewKeyPair(ctx context.Context, cfg *Configuration) (*KeyPair, error) {

	Logger.Info("Initializing DynamoDB client", "region", cfg.AWS.Region)

	awsConfig, err := config.LoadDefaultConfig(ctx,
		config.WithRegion(cfg.AWS.Region),
	)
	if err != nil {
		return nil, fmt.Errorf("error creating AWS config: %w", err)
	}

	client := dynamodb.NewFromConfig(awsConfig)

	// Test AWS credentials by attempting to list tables
	// This works with both IAM users and EC2 instance profiles
	_, err = client.ListTables(ctx, &dynamodb.ListTablesInput{
		Limit: aws.Int32(1),
	})
	if err != nil {
		return nil, fmt.Errorf("insufficient AWS credentials or permissions for DynamoDB: %w", err)
	}

	// Create table name mapping from configuration
	tableNames := map[string]string{
		"players":    cfg.DynamoDB.Tables.Players,
		"characters": cfg.DynamoDB.Tables.Characters,
		"rooms":      cfg.DynamoDB.Tables.Rooms,
		"exits":      cfg.DynamoDB.Tables.Exits,
		"items":      cfg.DynamoDB.Tables.Items,
		"prototypes": cfg.DynamoDB.Tables.Prototypes,
		"archetypes": cfg.DynamoDB.Tables.Archetypes,
		"motd":       cfg.DynamoDB.Tables.Motd,
	}

	// Use defaults if not configured
	for key, value := range tableNames {
		if value == "" {
			tableNames[key] = key // Use the key as the table name if not configured
		}
	}

	return &KeyPair{
		db:          client,
		maxRetries:  3,
		baseBackoff: time.Second,
		tableNames:  tableNames,
	}, nil
}

func (k *KeyPair) Put(ctx context.Context, tableName string, item interface{}) error {

	Logger.Info("Putting item into table", "tableName", tableName)

	av, err := attributevalue.MarshalMap(item)
	if err != nil {
		return fmt.Errorf("error marshalling item: %w", err)
	}

	input := &dynamodb.PutItemInput{
		Item:      av,
		TableName: aws.String(tableName),
	}

	_, err = k.db.PutItem(ctx, input)
	if err != nil {
		return fmt.Errorf("error putting item into table %s: %w", tableName, err)
	}

	Logger.Debug("Successfully put item into table", "tableName", tableName)
	return nil

}

// TransactWrite performs multiple write operations in a single transaction
func (k *KeyPair) TransactWrite(ctx context.Context, items []types.TransactWriteItem) error {
	Logger.Info("Performing transactional write", "itemCount", len(items))

	input := &dynamodb.TransactWriteItemsInput{
		TransactItems: items,
	}

	_, err := k.db.TransactWriteItems(ctx, input)
	if err != nil {
		return fmt.Errorf("error performing transactional write: %w", err)
	}

	Logger.Debug("Successfully completed transactional write", "itemCount", len(items))
	return nil
}

// BatchDeleteItems deletes multiple items in a single transaction to minimize DB access
func (k *KeyPair) BatchDeleteItems(ctx context.Context, itemIDs []string) error {
	if len(itemIDs) == 0 {
		return nil
	}

	// Check context at start
	select {
	case <-ctx.Done():
		return ctx.Err()
	default:
	}

	Logger.Info("Performing batch delete of items", "itemCount", len(itemIDs))

	// DynamoDB TransactWriteItems has a limit of 25 items per transaction
	const batchSize = 25

	for i := 0; i < len(itemIDs); i += batchSize {
		// Check context before each batch
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		end := i + batchSize
		if end > len(itemIDs) {
			end = len(itemIDs)
		}

		batch := itemIDs[i:end]
		transactItems := make([]types.TransactWriteItem, 0, len(batch))

		for _, itemID := range batch {
			transactItems = append(transactItems, types.TransactWriteItem{
				Delete: &types.Delete{
					TableName: aws.String(k.tableNames["items"]),
					Key: map[string]types.AttributeValue{
						"ItemID": &types.AttributeValueMemberS{Value: itemID},
					},
				},
			})
		}

		err := k.TransactWrite(ctx, transactItems)
		if err != nil {
			Logger.Error("Error deleting batch of items", "batchStart", i, "batchEnd", end, "error", err)
			return fmt.Errorf("error deleting items batch: %w", err)
		}
	}

	Logger.Debug("Successfully deleted items", "itemCount", len(itemIDs))
	return nil
}

// SaveCharacterWithInventory saves character and inventory items in a single transaction
func (k *KeyPair) SaveCharacterWithInventory(ctx context.Context, characterData *CharacterData, items map[string]*Item) error {
	// Check context at start
	select {
	case <-ctx.Done():
		return ctx.Err()
	default:
	}

	Logger.Debug("Saving character with inventory transactionally", "characterID", characterData.CharacterID, "itemCount", len(items))

	// Build transaction items
	transactItems := make([]types.TransactWriteItem, 0, len(items)+1)

	// Batch processing minimizes database round trips
	itemCount := 0
	for _, item := range items {
		// Check context periodically to handle cancellation gracefully
		// During shutdown, context should remain valid until after all saves complete
		if itemCount%10 == 0 {
			select {
			case <-ctx.Done():
				return ctx.Err()
			default:
			}
		}
		itemCount++

		if item != nil {
			// Item data conversion prepares for DynamoDB
			itemData := &ItemData{
				ItemID:      item.id.String(),
				PrototypeID: item.prototypeID.String(),
				Name:        item.name,
				Description: item.description,
				Mass:        item.mass,
				Value:       item.value,
				Stackable:   item.stackable,
				MaxStack:    item.maxStack,
				Quantity:    item.quantity,
				Wearable:    item.wearable,
				WornOn:      item.wornOn,
				Verbs:       item.verbs,
				Overrides:   item.overrides,
				TraitMods:   item.traitMods,
				Container:   item.container,
				Contents:    make([]string, 0), // Handle container contents separately if needed
				IsWorn:      item.isWorn,
				CanPickUp:   item.canPickUp,
				Metadata:    item.metadata,
			}

			// Marshal item data
			itemAV, err := attributevalue.MarshalMap(itemData)
			if err != nil {
				return fmt.Errorf("error marshalling item %s: %w", item.id, err)
			}

			// Transaction accumulation enables atomic writes
			transactItems = append(transactItems, types.TransactWriteItem{
				Put: &types.Put{
					TableName: aws.String(k.tableNames["items"]),
					Item:      itemAV,
				},
			})
		}
	}

	// Marshal character data
	charAV, err := attributevalue.MarshalMap(characterData)
	if err != nil {
		return fmt.Errorf("error marshalling character data: %w", err)
	}

	// Character inclusion completes atomic save operation
	transactItems = append(transactItems, types.TransactWriteItem{
		Put: &types.Put{
			TableName: aws.String(k.tableNames["characters"]),
			Item:      charAV,
		},
	})

	// Transaction execution atomically saves all items
	return k.TransactWrite(ctx, transactItems)
}

// Get retrieves an item from the DynamoDB table.
func (k *KeyPair) Get(ctx context.Context, tableName string, key map[string]types.AttributeValue, item interface{}) error {

	Logger.Info("Getting item from table", "tableName", tableName)

	input := &dynamodb.GetItemInput{
		Key:       key,
		TableName: aws.String(tableName),
	}

	result, err := k.db.GetItem(ctx, input)
	if err != nil {
		return fmt.Errorf("error getting item from table %s: %w", tableName, err)
	}

	if result.Item == nil {
		return fmt.Errorf("item not found in table %s", tableName)
	}

	err = attributevalue.UnmarshalMap(result.Item, item)
	if err != nil {
		return fmt.Errorf("error unmarshalling item: %w", err)
	}

	return nil
}

// Delete performs single-item removal from DynamoDB
func (k *KeyPair) Delete(ctx context.Context, tableName string, key map[string]types.AttributeValue) error {

	Logger.Info("Deleting item from table", "tableName", tableName)

	input := &dynamodb.DeleteItemInput{
		Key:       key,
		TableName: aws.String(tableName),
	}

	_, err := k.db.DeleteItem(ctx, input)
	if err != nil {
		return fmt.Errorf("error deleting item from table %s: %w", tableName, err)
	}

	Logger.Info("Successfully deleted item from table", "tableName", tableName)
	return nil
}

// Query performs a query operation on the DynamoDB table with pagination.
func (k *KeyPair) Query(ctx context.Context, tableName string, keyConditionExpression string, expressionAttributeValues map[string]types.AttributeValue, items interface{}) error {
	Logger.Info("Querying table", "tableName", tableName)

	input := &dynamodb.QueryInput{
		TableName:                 aws.String(tableName),
		KeyConditionExpression:    aws.String(keyConditionExpression),
		ExpressionAttributeValues: expressionAttributeValues,
	}

	var allItems []map[string]types.AttributeValue
	var lastEvaluatedKey map[string]types.AttributeValue

	for {
		// Pagination key enables processing large result sets
		if lastEvaluatedKey != nil {
			input.ExclusiveStartKey = lastEvaluatedKey
		}

		// Perform the query operation
		result, err := k.db.Query(ctx, input)
		if err != nil {
			return fmt.Errorf("error querying table %s: %w", tableName, err)
		}

		// Append the current page of results
		allItems = append(allItems, result.Items...)

		// Get the last evaluated key for the next page
		lastEvaluatedKey = result.LastEvaluatedKey

		if lastEvaluatedKey == nil {
			break
		}

		Logger.Debug("Retrieved query page",
			"tableName", tableName,
			"itemCount", len(result.Items),
			"continuingPagination", true)
	}

	Logger.Info("Query completed", "tableName", tableName, "totalItems", len(allItems))

	if len(allItems) == 0 {
		err := attributevalue.UnmarshalListOfMaps([]map[string]types.AttributeValue{}, items)
		if err != nil {
			return fmt.Errorf("error unmarshalling empty query results: %w", err)
		}
		return nil
	}

	// Unmarshal all the collected items
	err := attributevalue.UnmarshalListOfMaps(allItems, items)
	if err != nil {
		return fmt.Errorf("error unmarshalling query results: %w", err)
	}

	return nil
}

// Scan performs a scan operation on the DynamoDB table with pagination..
func (k *KeyPair) Scan(ctx context.Context, tableName string, items interface{}) error {
	Logger.Info("Scanning table", "tableName", tableName)

	input := &dynamodb.ScanInput{
		TableName: aws.String(tableName),
	}

	var allItems []map[string]types.AttributeValue
	var lastEvaluatedKey map[string]types.AttributeValue

	for {
		// Pagination key enables processing large result sets
		if lastEvaluatedKey != nil {
			input.ExclusiveStartKey = lastEvaluatedKey
		}

		// Perform the scan operation
		result, err := k.db.Scan(ctx, input)
		if err != nil {
			return fmt.Errorf("error scanning table %s: %w", tableName, err)
		}

		allItems = append(allItems, result.Items...)

		lastEvaluatedKey = result.LastEvaluatedKey

		if lastEvaluatedKey == nil {
			break
		}

		Logger.Debug("Retrieved scan page",
			"tableName", tableName,
			"itemCount", len(result.Items),
			"continuingPagination", true)
	}

	Logger.Info("Scan completed", "tableName", tableName, "totalItems", len(allItems))

	// Empty results require special handling for unmarshalling
	if len(allItems) == 0 {
		err := attributevalue.UnmarshalListOfMaps([]map[string]types.AttributeValue{}, items)
		if err != nil {
			return fmt.Errorf("error unmarshalling empty scan results: %w", err)
		}
		return nil
	}

	// Unmarshal all the collected items
	err := attributevalue.UnmarshalListOfMaps(allItems, items)
	if err != nil {
		return fmt.Errorf("error unmarshalling scan results: %w", err)
	}

	return nil
}

// CharacterInfo holds minimal character data for bloom filter loading
type CharacterInfo struct {
	CharacterID   string `dynamodbav:"character_id"`
	CharacterName string `dynamodbav:"character_name"`
	PlayerID      string `dynamodbav:"player_id"`
}

// PlayerInfo holds minimal player data for bloom filter loading
type PlayerInfo struct {
	PlayerID      string            `dynamodbav:"player_id"`
	CharacterList map[string]string `dynamodbav:"character_list"`
}

// LoadCharactersAndPlayers loads all characters and players in a single operation for bloom filter initialization
func (k *KeyPair) LoadCharactersAndPlayers(ctx context.Context) ([]CharacterInfo, []PlayerInfo, error) {
	Logger.Info("Loading characters and players for bloom filter initialization")

	// Character scan populates bloom filter data
	var characters []CharacterInfo
	err := k.Scan(ctx, k.tableNames["characters"], &characters)
	if err != nil {
		return nil, nil, fmt.Errorf("error scanning characters: %w", err)
	}

	// Player scan enables account-character mapping
	var players []PlayerInfo
	err = k.Scan(ctx, k.tableNames["players"], &players)
	if err != nil {
		return nil, nil, fmt.Errorf("error scanning players: %w", err)
	}

	Logger.Info("Loaded characters and players",
		"characterCount", len(characters),
		"playerCount", len(players))

	return characters, players, nil
}

// LoadCharacterNames loads only character names for bloom filter initialization
func (k *KeyPair) LoadCharacterNames(ctx context.Context) ([]string, error) {
	Logger.Info("Loading character names for bloom filter")

	// Only need to scan for character names
	var characters []CharacterInfo
	err := k.Scan(ctx, k.tableNames["characters"], &characters)
	if err != nil {
		return nil, fmt.Errorf("error scanning characters: %w", err)
	}

	names := make([]string, 0, len(characters))
	for _, character := range characters {
		names = append(names, strings.ToLower(character.CharacterName))
	}

	return names, nil
}

// DeleteCharacter removes a character from the database
func (k *KeyPair) DeleteCharacter(ctx context.Context, characterID string) error {
	key := map[string]types.AttributeValue{
		"CharacterID": &types.AttributeValueMemberS{Value: characterID},
	}
	return k.Delete(ctx, k.tableNames["characters"], key)
}

// RemoveCharacterFromPlayer removes a character from a player's character list
func (k *KeyPair) RemoveCharacterFromPlayer(ctx context.Context, playerID, characterName string) error {
	// Player data required for character list modification
	var playerData PlayerData
	key := map[string]types.AttributeValue{
		"PlayerID": &types.AttributeValueMemberS{Value: playerID},
	}

	err := k.Get(ctx, k.tableNames["players"], key, &playerData)
	if err != nil {
		return fmt.Errorf("failed to get player data: %w", err)
	}

	// List removal breaks character-player association
	delete(playerData.CharacterList, characterName)

	// Record update persists association changes
	err = k.Put(ctx, k.tableNames["players"], &playerData)
	if err != nil {
		return fmt.Errorf("failed to update player data: %w", err)
	}

	Logger.Info("Removed character from player",
		"playerID", playerID,
		"characterName", characterName)

	return nil
}
