package main

import (
	"fmt"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/dynamodb"
)

type KeyPair struct {
	db          *dynamodb.DynamoDB
	maxRetries  int
	baseBackoff time.Duration
}

// NewKeyPair initializes a new DynamoDB client.
func NewKeyPair(config *Configuration) (*KeyPair, error) {
	Logger.Info("Initializing DynamoDB client", "region", config.aws.region)

	sess, err := session.NewSession(&aws.Config{
		Region: aws.String(config.aws.region),
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
