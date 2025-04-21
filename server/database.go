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
func NewKeyPair(cfg *Configuration) (*KeyPair, error) {

	Logger.Info("Initializing DynamoDB client", "region", cfg.AWS.Region)

	awsConfig, err := config.LoadDefaultConfig(context.TODO(),
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

func (k *KeyPair) Put(tableName string, item interface{}) error {

	Logger.Info("Putting item into table", "tableName", tableName)

	av, err := attributevalue.MarshalMap(item)
	if err != nil {
		return fmt.Errorf("error marshalling item: %w", err)
	}

	input := &dynamodb.PutItemInput{
		Item:      av,
		TableName: aws.String(tableName),
	}

	_, err = k.db.PutItem(context.TODO(), input)
	if err != nil {
		return fmt.Errorf("error putting item into table %s: %w", tableName, err)
	}

	Logger.Debug("Successfully put item into table", "tableName", tableName)
	return nil

}

// Get retrieves an item from the DynamoDB table.
func (k *KeyPair) Get(tableName string, key map[string]types.AttributeValue, item interface{}) error {

	Logger.Info("Getting item from table", "tableName", tableName)

	input := &dynamodb.GetItemInput{
		Key:       key,
		TableName: aws.String(tableName),
	}

	result, err := k.db.GetItem(context.TODO(), input)
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
func (k *KeyPair) Delete(tableName string, key map[string]types.AttributeValue) error {

	Logger.Info("Deleting item from table", "tableName", tableName)

	input := &dynamodb.DeleteItemInput{
		Key:       key,
		TableName: aws.String(tableName),
	}

	_, err := k.db.DeleteItem(context.TODO(), input)
	if err != nil {
		return fmt.Errorf("error deleting item from table %s: %w", tableName, err)
	}

	Logger.Info("Successfully deleted item from table", "tableName", tableName)
	return nil
}

// Query performs a query operation on the DynamoDB table with pagination.
func (k *KeyPair) Query(tableName string, keyConditionExpression string, expressionAttributeValues map[string]types.AttributeValue, items interface{}) error {
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
		result, err := k.db.Query(context.TODO(), input)
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
func (k *KeyPair) Scan(tableName string, items interface{}) error {
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
		result, err := k.db.Scan(context.TODO(), input)
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
