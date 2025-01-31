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
	"fmt"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/awserr"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/aws/aws-sdk-go/service/dynamodb/dynamodbattribute"
)

type KeyPair struct {
	db          *dynamodb.DynamoDB
	maxRetries  int
	baseBackoff time.Duration
}

// NewKeyPair initializes a new DynamoDB client.
func NewKeyPair(config *Configuration) (*KeyPair, error) {
	Logger.Info("Initializing DynamoDB client", "region", config.AWS.Region)

	sess, err := session.NewSession(&aws.Config{
		Region: aws.String(config.AWS.Region),
	})
	if err != nil {
		return nil, fmt.Errorf("error creating AWS session: %w", err)
	}

	svc := dynamodb.New(sess)

	return &KeyPair{
		db:          svc,
		maxRetries:  3,
		baseBackoff: time.Second,
	}, nil
}

func (k *KeyPair) Put(tableName string, item interface{}) error {
	av, err := dynamodbattribute.MarshalMap(item)
	if err != nil {
		return fmt.Errorf("error marshalling item: %w", err)
	}

	input := &dynamodb.PutItemInput{
		Item:      av,
		TableName: aws.String(tableName),
	}

	// Implement retries with exponential backoff
	const maxRetries = 3
	for attempt := 0; attempt < maxRetries; attempt++ {
		_, err = k.db.PutItem(input)
		if err != nil {
			if isRetryableError(err) && attempt < maxRetries-1 {
				backoffDuration := time.Duration(attempt+1) * time.Second
				Logger.Warn("Retryable error in PutItem, will retry", "attempt", attempt+1, "backoff", backoffDuration, "error", err)
				time.Sleep(backoffDuration)
				continue
			}
			return fmt.Errorf("error putting item into table %s: %w", tableName, err)
		}
		Logger.Debug("Successfully put item into table", "tableName", tableName)
		return nil
	}

	return fmt.Errorf("failed to put item into table %s after %d attempts", tableName, maxRetries)
}

// Get retrieves an item from the DynamoDB table.
func (k *KeyPair) Get(tableName string, key map[string]*dynamodb.AttributeValue, item interface{}) error {
	input := &dynamodb.GetItemInput{
		Key:       key,
		TableName: aws.String(tableName),
	}

	const maxRetries = 3
	var result *dynamodb.GetItemOutput
	var err error
	for attempt := 0; attempt < maxRetries; attempt++ {
		result, err = k.db.GetItem(input)
		if err != nil {
			if isRetryableError(err) && attempt < maxRetries-1 {
				backoffDuration := time.Duration(attempt+1) * time.Second
				Logger.Warn("Retryable error in GetItem, will retry", "attempt", attempt+1, "backoff", backoffDuration, "error", err)
				time.Sleep(backoffDuration)
				continue
			}
			return fmt.Errorf("error getting item from table %s: %w", tableName, err)
		}
		break
	}

	if result.Item == nil {
		return fmt.Errorf("item not found in table %s", tableName)
	}

	err = dynamodbattribute.UnmarshalMap(result.Item, item)
	if err != nil {
		return fmt.Errorf("error unmarshalling item: %w", err)
	}

	return nil
}

// Delete removes an item from the DynamoDB table.
func (k *KeyPair) Delete(tableName string, key map[string]*dynamodb.AttributeValue) error {
	input := &dynamodb.DeleteItemInput{
		Key:       key,
		TableName: aws.String(tableName),
	}

	const maxRetries = 3
	for attempt := 0; attempt < maxRetries; attempt++ {
		_, err := k.db.DeleteItem(input)
		if err != nil {
			if isRetryableError(err) && attempt < maxRetries-1 {
				backoffDuration := time.Duration(attempt+1) * time.Second
				Logger.Warn("Retryable error in DeleteItem, will retry", "attempt", attempt+1, "backoff", backoffDuration, "error", err)
				time.Sleep(backoffDuration)
				continue
			}
			return fmt.Errorf("error deleting item from table %s: %w", tableName, err)
		}
		Logger.Info("Successfully deleted item from table", "tableName", tableName)
		return nil
	}

	return fmt.Errorf("failed to delete item from table %s after %d attempts", tableName, maxRetries)
}

// Query performs a query operation on the DynamoDB table.
func (k *KeyPair) Query(tableName string, keyConditionExpression string, expressionAttributeValues map[string]*dynamodb.AttributeValue, items interface{}) error {
	input := &dynamodb.QueryInput{
		TableName:                 aws.String(tableName),
		KeyConditionExpression:    aws.String(keyConditionExpression),
		ExpressionAttributeValues: expressionAttributeValues,
	}

	// Implement retries with exponential backoff
	const maxRetries = 3
	var result *dynamodb.QueryOutput
	var err error
	for attempt := 0; attempt < maxRetries; attempt++ {
		result, err = k.db.Query(input)
		if err != nil {
			if isRetryableError(err) && attempt < maxRetries-1 {
				backoffDuration := time.Duration(attempt+1) * time.Second
				Logger.Warn("Retryable error in Query, will retry", "attempt", attempt+1, "backoff", backoffDuration, "error", err)
				time.Sleep(backoffDuration)
				continue
			}
			return fmt.Errorf("error querying table %s: %w", tableName, err)
		}
		break
	}

	err = dynamodbattribute.UnmarshalListOfMaps(result.Items, items)
	if err != nil {
		return fmt.Errorf("error unmarshalling query results: %w", err)
	}

	return nil
}

// Scan performs a scan operation on the DynamoDB table.
func (k *KeyPair) Scan(tableName string, items interface{}) error {
	input := &dynamodb.ScanInput{
		TableName: aws.String(tableName),
	}

	// Implement retries with exponential backoff
	const maxRetries = 3
	var result *dynamodb.ScanOutput
	var err error
	for attempt := 0; attempt < maxRetries; attempt++ {
		result, err = k.db.Scan(input)
		if err != nil {
			if isRetryableError(err) && attempt < maxRetries-1 {
				backoffDuration := time.Duration(attempt+1) * time.Second
				Logger.Warn("Retryable error in Scan, will retry", "attempt", attempt+1, "backoff", backoffDuration, "error", err)
				time.Sleep(backoffDuration)
				continue
			}
			return fmt.Errorf("error scanning table %s: %w", tableName, err)
		}
		break
	}

	err = dynamodbattribute.UnmarshalListOfMaps(result.Items, items)
	if err != nil {
		return fmt.Errorf("error unmarshalling scan results: %w", err)
	}

	return nil
}

// isRetryableError checks if the error is retryable based on AWS error codes.
func isRetryableError(err error) bool {
	if awsErr, ok := err.(awserr.Error); ok {
		switch awsErr.Code() {
		case dynamodb.ErrCodeProvisionedThroughputExceededException,
			dynamodb.ErrCodeInternalServerError,
			"ThrottlingException",
			"RequestLimitExceeded":
			return true
		}
	}
	return false
}
