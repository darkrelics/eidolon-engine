package core

import (
	"fmt"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/aws/aws-sdk-go/service/dynamodb/dynamodbattribute"
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
