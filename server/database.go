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
	"context"
	"fmt"
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
}

// NewKeyPair initializes a new DynamoDB client.
func NewKeyPair(ctx context.Context, cfg *Configuration) (*KeyPair, error) {

	Logger.Info("Initializing DynamoDB client", "region", cfg.AWS.Region)

	awsConfig, err := config.LoadDefaultConfig(ctx,
		config.WithRegion(cfg.AWS.Region),
	)
	if err != nil {
		return nil, fmt.Errorf("error creating AWS config: %w", err)
	}

	client := dynamodb.NewFromConfig(awsConfig)

	return &KeyPair{
		db:          client,
		maxRetries:  3,
		baseBackoff: time.Second,
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

	Logger.Info("Performing batch delete of items", "itemCount", len(itemIDs))

	// DynamoDB TransactWriteItems has a limit of 25 items per transaction
	const batchSize = 25
	
	for i := 0; i < len(itemIDs); i += batchSize {
		end := i + batchSize
		if end > len(itemIDs) {
			end = len(itemIDs)
		}
		
		batch := itemIDs[i:end]
		transactItems := make([]types.TransactWriteItem, 0, len(batch))
		
		for _, itemID := range batch {
			transactItems = append(transactItems, types.TransactWriteItem{
				Delete: &types.Delete{
					TableName: aws.String("items"),
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
	Logger.Debug("Saving character with inventory transactionally", "characterID", characterData.CharacterID, "itemCount", len(items))

	// Build transaction items
	transactItems := make([]types.TransactWriteItem, 0, len(items)+1)

	// Add all inventory items to transaction
	for _, item := range items {
		if item != nil {
			// Create item data for storage
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

			// Add item to transaction
			transactItems = append(transactItems, types.TransactWriteItem{
				Put: &types.Put{
					TableName: aws.String("items"),
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

	// Add character to transaction
	transactItems = append(transactItems, types.TransactWriteItem{
		Put: &types.Put{
			TableName: aws.String("characters"),
			Item:      charAV,
		},
	})

	// Execute transaction
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

// Delete removes an item from the DynamoDB table.
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
		// Set the exclusive start key for pagination
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
		// Set the exclusive start key for pagination
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

	// Handle the case of no items found
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
