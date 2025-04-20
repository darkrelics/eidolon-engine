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

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/awserr"
	"github.com/aws/aws-sdk-go/service/cognitoidentityprovider"
	"github.com/google/uuid"
)

// Removed calculateSecretHash function

func (s *Server) SignInUser(email, password string) (*cognitoidentityprovider.InitiateAuthOutput, error) {
	// Removed secret hash calculation
	authInput := &cognitoidentityprovider.InitiateAuthInput{
		AuthFlow: aws.String(cognitoidentityprovider.AuthFlowTypeUserPasswordAuth),
		AuthParameters: map[string]*string{
			"USERNAME": aws.String(email),
			"PASSWORD": aws.String(password),
			// Removed SECRET_HASH
		},
		ClientId: aws.String(s.config.Cognito.UserPoolClientID),
	}

	authOutput, err := s.cognito.InitiateAuth(authInput)
	if err != nil {
		return nil, handleCognitoError(err, email)
	}

	if authOutput.AuthenticationResult == nil {
		// Check for challenges only if no auth result
		if authOutput.ChallengeName != nil &&
			*authOutput.ChallengeName == cognitoidentityprovider.ChallengeNameTypeNewPasswordRequired {
			return authOutput, nil
		}
		return nil, fmt.Errorf("unexpected authentication result for user %s", email)
	}

	return authOutput, nil
}

func (s *Server) SignUpUser(email, password string) (*cognitoidentityprovider.SignUpOutput, error) {
	// Removed secret hash calculation
	signUpInput := &cognitoidentityprovider.SignUpInput{
		ClientId: aws.String(s.config.Cognito.UserPoolClientID),
		Username: aws.String(email),
		Password: aws.String(password),
		// Removed SecretHash
		UserAttributes: []*cognitoidentityprovider.AttributeType{
			{Name: aws.String("email"), Value: aws.String(email)},
		},
	}

	signUpOutput, err := s.cognito.SignUp(signUpInput)
	if err != nil {
		Logger.Error("Error signing up user", "email", email, "error", err)
		return nil, fmt.Errorf("error signing up, please try again")
	}

	return signUpOutput, nil
}

func (s *Server) ConfirmUser(email, confirmationCode string) (*cognitoidentityprovider.ConfirmSignUpOutput, error) {
	// Removed secret hash calculation
	confirmSignUpInput := &cognitoidentityprovider.ConfirmSignUpInput{
		ClientId:         aws.String(s.config.Cognito.UserPoolClientID),
		Username:         aws.String(email),
		ConfirmationCode: aws.String(confirmationCode),
		// Removed SecretHash
	}

	return s.cognito.ConfirmSignUp(confirmSignUpInput)
}

func (s *Server) GetUserData(accessToken string) (*cognitoidentityprovider.GetUserOutput, error) {
	getUserInput := &cognitoidentityprovider.GetUserInput{
		AccessToken: aws.String(accessToken),
	}
	return s.cognito.GetUser(getUserInput)
}

func (s *Server) ChangePassword(player *Player, oldPassword, newPassword string) error {
	signInOutput, err := s.SignInUser(player.email, oldPassword)
	if err != nil {
		return fmt.Errorf("authentication failed: %w", err)
	}

	if signInOutput.ChallengeName != nil && *signInOutput.ChallengeName == cognitoidentityprovider.ChallengeNameTypeNewPasswordRequired {
		// Removed secret hash calculation
		challengeInput := &cognitoidentityprovider.RespondToAuthChallengeInput{
			ChallengeName: aws.String(cognitoidentityprovider.ChallengeNameTypeNewPasswordRequired),
			ClientId:      aws.String(s.config.Cognito.UserPoolClientID),
			ChallengeResponses: map[string]*string{
				"USERNAME":     aws.String(player.email),
				"NEW_PASSWORD": aws.String(newPassword),
				// Removed SECRET_HASH
			},
			Session: signInOutput.Session,
		}
		_, err := s.cognito.RespondToAuthChallenge(challengeInput)
		return err
	}

	if signInOutput.AuthenticationResult == nil || signInOutput.AuthenticationResult.AccessToken == nil {
		return fmt.Errorf("no valid access token available")
	}

	input := &cognitoidentityprovider.ChangePasswordInput{
		PreviousPassword: aws.String(oldPassword),
		ProposedPassword: aws.String(newPassword),
		AccessToken:      signInOutput.AuthenticationResult.AccessToken,
	}

	_, err = s.cognito.ChangePassword(input)
	return err
}

func handleCognitoError(err error, email string) error {
	if awsErr, ok := err.(awserr.Error); ok {
		switch awsErr.Code() {
		case cognitoidentityprovider.ErrCodeUserNotFoundException,
			cognitoidentityprovider.ErrCodeNotAuthorizedException:
			Logger.Error("Auth failed", "email", email)
			return fmt.Errorf("incorrect username or password")

		case cognitoidentityprovider.ErrCodeUserNotConfirmedException:
			Logger.Error("User unconfirmed", "email", email)
			return fmt.Errorf("account not confirmed")

		case cognitoidentityprovider.ErrCodePasswordResetRequiredException:
			Logger.Error("Password reset needed", "email", email)
			return fmt.Errorf("password reset required")

		case cognitoidentityprovider.ErrCodeInvalidParameterException:
			Logger.Error("Invalid parameters", "email", email)
			return fmt.Errorf("invalid authentication parameters")

		default:
			Logger.Error("Unknown auth error", "email", email, "code", awsErr.Code())
			return fmt.Errorf("authentication failed")
		}
	}

	Logger.Error("Non-AWS auth error", "email", email)
	return fmt.Errorf("authentication failed")
}

func Authenticate(username, password string, ssh_interface *Interface_SSH) (bool, uuid.UUID, error) {
	// Removed secret hash calculation
	authOutput, err := ssh_interface.server.cognito.InitiateAuth(&cognitoidentityprovider.InitiateAuthInput{
		AuthFlow: aws.String("USER_PASSWORD_AUTH"),
		AuthParameters: map[string]*string{
			"USERNAME": aws.String(username),
			"PASSWORD": aws.String(password),
			// Removed SECRET_HASH
		},
		ClientId: aws.String(ssh_interface.config.Cognito.UserPoolClientID),
	})

	if err != nil {
		Logger.Error("authentication failed", "username", username, "error", err)
		return false, uuid.Nil, err
	}

	if authOutput.AuthenticationResult == nil {
		Logger.Error("no authentication result", "username", username)
		return false, uuid.Nil, fmt.Errorf("no authentication result")
	}

	// Get user data to retrieve UUID
	getUserInput := &cognitoidentityprovider.GetUserInput{
		AccessToken: authOutput.AuthenticationResult.AccessToken,
	}

	userData, err := ssh_interface.server.cognito.GetUser(getUserInput)
	if err != nil {
		Logger.Error("failed to get user data", "username", username, "error", err)
		return true, uuid.Nil, fmt.Errorf("authenticated but failed to get user ID: %w", err)
	}

	// Extract the user's sub (UUID) from the attributes
	var userUUIDStr string
	for _, attr := range userData.UserAttributes {
		if *attr.Name == "sub" {
			userUUIDStr = *attr.Value
			break
		}
	}

	if userUUIDStr == "" {
		Logger.Error("user UUID not found in user attributes", "username", username)
		return true, uuid.Nil, fmt.Errorf("user UUID not found")
	}

	// Parse string UUID into uuid.UUID type
	userUUID, err := uuid.Parse(userUUIDStr)
	if err != nil {
		Logger.Error("failed to parse user UUID", "username", username, "uuid_string", userUUIDStr, "error", err)
		return true, uuid.Nil, fmt.Errorf("failed to parse user UUID: %w", err)
	}

	Logger.Info("Player authenticated", "player_name", username, "player_uuid", userUUID)
	return true, userUUID, nil
}
