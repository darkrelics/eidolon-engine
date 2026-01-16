/*
Eidolon Engine

Copyright 2024-2026 Jason E. Robinson

*/

package main

import (
	"errors"
	"fmt"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cognitoidentityprovider"
	"github.com/aws/aws-sdk-go-v2/service/cognitoidentityprovider/types"
	"github.com/aws/smithy-go"
	"github.com/gofrs/uuid/v5"
)

func (s *Server) SignInUser(email, password string) (*cognitoidentityprovider.InitiateAuthOutput, error) {
	authInput := &cognitoidentityprovider.InitiateAuthInput{
		AuthFlow: types.AuthFlowTypeUserPasswordAuth,
		AuthParameters: map[string]string{
			"USERNAME": email,
			"PASSWORD": password,
		},
		ClientId: aws.String(s.config.Cognito.UserPoolClientID),
	}

	authOutput, err := s.cognito.InitiateAuth(s.ctx, authInput)
	if err != nil {
		return nil, handleCognitoError(err, email)
	}

	if authOutput.AuthenticationResult == nil {
		if authOutput.ChallengeName == types.ChallengeNameTypeNewPasswordRequired {
			return authOutput, nil
		}
		return nil, fmt.Errorf("unexpected authentication result for user %s", email)
	}

	return authOutput, nil
}

func (s *Server) SignUpUser(email, password string) (*cognitoidentityprovider.SignUpOutput, error) {
	signUpInput := &cognitoidentityprovider.SignUpInput{
		ClientId: aws.String(s.config.Cognito.UserPoolClientID),
		Username: aws.String(email),
		Password: aws.String(password),
		UserAttributes: []types.AttributeType{
			{Name: aws.String("email"), Value: aws.String(email)},
		},
	}

	signUpOutput, err := s.cognito.SignUp(s.ctx, signUpInput)
	if err != nil {
		Logger.Error("Error signing up user", "email", email, "error", err)
		return nil, fmt.Errorf("error signing up, please try again")
	}

	return signUpOutput, nil
}

func (s *Server) ConfirmUser(email, confirmationCode string) (*cognitoidentityprovider.ConfirmSignUpOutput, error) {
	confirmSignUpInput := &cognitoidentityprovider.ConfirmSignUpInput{
		ClientId:         aws.String(s.config.Cognito.UserPoolClientID),
		Username:         aws.String(email),
		ConfirmationCode: aws.String(confirmationCode),
	}

	return s.cognito.ConfirmSignUp(s.ctx, confirmSignUpInput)
}

func (s *Server) GetUserData(accessToken string) (*cognitoidentityprovider.GetUserOutput, error) {
	getUserInput := &cognitoidentityprovider.GetUserInput{
		AccessToken: aws.String(accessToken),
	}
	return s.cognito.GetUser(s.ctx, getUserInput)
}

func (s *Server) ChangePassword(player *Player, oldPassword, newPassword string) error {
	signInOutput, err := s.SignInUser(player.email, oldPassword)
	if err != nil {
		return fmt.Errorf("authentication failed: %w", err)
	}

	if signInOutput.ChallengeName == types.ChallengeNameTypeNewPasswordRequired {
		challengeInput := &cognitoidentityprovider.RespondToAuthChallengeInput{
			ChallengeName: types.ChallengeNameTypeNewPasswordRequired,
			ClientId:      aws.String(s.config.Cognito.UserPoolClientID),
			ChallengeResponses: map[string]string{
				"USERNAME":     player.email,
				"NEW_PASSWORD": newPassword,
			},
			Session: signInOutput.Session,
		}
		_, err := s.cognito.RespondToAuthChallenge(s.ctx, challengeInput)
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

	_, err = s.cognito.ChangePassword(s.ctx, input)
	return err
}

func handleCognitoError(err error, email string) error {
	var ae smithy.APIError
	if errors.As(err, &ae) {
		switch ae.ErrorCode() {
		case "UserNotFoundException",
			"NotAuthorizedException":
			Logger.Error("Auth failed", "email", email)
			return fmt.Errorf("incorrect username or password")

		case "UserNotConfirmedException":
			Logger.Error("User unconfirmed", "email", email)
			return fmt.Errorf("account not confirmed")

		case "PasswordResetRequiredException":
			Logger.Error("Password reset needed", "email", email)
			return fmt.Errorf("password reset required")

		case "InvalidParameterException":
			Logger.Error("Invalid parameters", "email", email)
			return fmt.Errorf("invalid authentication parameters")

		default:
			Logger.Error("Unknown auth error", "email", email, "code", ae.ErrorCode())
			return fmt.Errorf("authentication failed")
		}
	}

	Logger.Error("Non-AWS auth error", "email", email)
	return fmt.Errorf("authentication failed")
}

func Authenticate(username, password, mfaCode string, ssh_interface *Interface_SSH) (bool, uuid.UUID, error) {
	authOutput, err := ssh_interface.server.cognito.InitiateAuth(ssh_interface.server.ctx, &cognitoidentityprovider.InitiateAuthInput{
		AuthFlow: types.AuthFlowTypeUserPasswordAuth,
		AuthParameters: map[string]string{
			"USERNAME": username,
			"PASSWORD": password,
		},
		ClientId: aws.String(ssh_interface.config.Cognito.UserPoolClientID),
	})

	if err != nil {
		Logger.Error("authentication failed", "username", username, "error", err)
		return false, uuid.Nil, err
	}

	// Handle MFA Challenge
	if authOutput.ChallengeName == types.ChallengeNameTypeSoftwareTokenMfa {
		if mfaCode == "" {
			return false, uuid.Nil, fmt.Errorf("MFA_REQUIRED")
		}

		// Respond to MFA challenge
		challengeOutput, err := ssh_interface.server.cognito.RespondToAuthChallenge(ssh_interface.server.ctx, &cognitoidentityprovider.RespondToAuthChallengeInput{
			ChallengeName: types.ChallengeNameTypeSoftwareTokenMfa,
			ClientId:      aws.String(ssh_interface.config.Cognito.UserPoolClientID),
			ChallengeResponses: map[string]string{
				"USERNAME":                username,
				"SOFTWARE_TOKEN_MFA_CODE": mfaCode,
			},
			Session: authOutput.Session,
		})

		if err != nil {
			Logger.Error("MFA validation failed", "username", username, "error", err)
			return false, uuid.Nil, fmt.Errorf("invalid MFA code")
		}

		authOutput.AuthenticationResult = challengeOutput.AuthenticationResult
	}

	if authOutput.AuthenticationResult == nil {
		Logger.Error("no authentication result", "username", username)
		return false, uuid.Nil, fmt.Errorf("no authentication result")
	}

	// Get user data to retrieve UUID
	getUserInput := &cognitoidentityprovider.GetUserInput{
		AccessToken: authOutput.AuthenticationResult.AccessToken,
	}

	userData, err := ssh_interface.server.cognito.GetUser(ssh_interface.server.ctx, getUserInput)
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
	userUUID, err := uuid.FromString(userUUIDStr)
	if err != nil {
		Logger.Error("failed to parse user UUID", "username", username, "uuid_string", userUUIDStr, "error", err)
		return true, uuid.Nil, fmt.Errorf("failed to parse user UUID: %w", err)
	}

	Logger.Info("Player authenticated", "player_name", username, "player_uuid", userUUID)
	return true, userUUID, nil
}
