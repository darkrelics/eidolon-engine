package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"fmt"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/awserr"
	"github.com/aws/aws-sdk-go/service/cognitoidentityprovider"
)

func (s *Server) calculateSecretHash(email string) string {
	message := []byte(email + s.config.Cognito.ClientID)
	key := []byte(s.config.Cognito.ClientSecret)
	hash := hmac.New(sha256.New, key)
	hash.Write(message)
	return base64.StdEncoding.EncodeToString(hash.Sum(nil))
}

func (s *Server) SignInUser(email, password string) (*cognitoidentityprovider.InitiateAuthOutput, error) {
	secretHash := s.calculateSecretHash(email)

	authInput := &cognitoidentityprovider.InitiateAuthInput{
		AuthFlow: aws.String(cognitoidentityprovider.AuthFlowTypeUserPasswordAuth),
		AuthParameters: map[string]*string{
			"USERNAME":    aws.String(email),
			"PASSWORD":    aws.String(password),
			"SECRET_HASH": aws.String(secretHash),
		},
		ClientId: aws.String(s.config.Cognito.ClientID),
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
	secretHash := s.calculateSecretHash(email)

	signUpInput := &cognitoidentityprovider.SignUpInput{
		ClientId:   aws.String(s.config.Cognito.ClientID),
		Username:   aws.String(email),
		Password:   aws.String(password),
		SecretHash: aws.String(secretHash),
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
	secretHash := s.calculateSecretHash(email)

	confirmSignUpInput := &cognitoidentityprovider.ConfirmSignUpInput{
		ClientId:         aws.String(s.config.Cognito.ClientID),
		Username:         aws.String(email),
		ConfirmationCode: aws.String(confirmationCode),
		SecretHash:       aws.String(secretHash),
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
	signInOutput, err := s.SignInUser(player.playerID, oldPassword)
	if err != nil {
		return fmt.Errorf("authentication failed: %w", err)
	}

	if signInOutput.ChallengeName != nil && *signInOutput.ChallengeName == cognitoidentityprovider.ChallengeNameTypeNewPasswordRequired {
		secretHash := s.calculateSecretHash(player.playerID)
		challengeInput := &cognitoidentityprovider.RespondToAuthChallengeInput{
			ChallengeName: aws.String(cognitoidentityprovider.ChallengeNameTypeNewPasswordRequired),
			ClientId:      aws.String(s.config.Cognito.ClientID),
			ChallengeResponses: map[string]*string{
				"USERNAME":     aws.String(player.playerID),
				"NEW_PASSWORD": aws.String(newPassword),
				"SECRET_HASH":  aws.String(secretHash),
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

func Authenticate(username, password string, ssh_interface *Interface_SSH) bool {
	secretHash := ssh_interface.server.calculateSecretHash(username)

	authOutput, err := ssh_interface.server.cognito.InitiateAuth(&cognitoidentityprovider.InitiateAuthInput{
		AuthFlow: aws.String("USER_PASSWORD_AUTH"),
		AuthParameters: map[string]*string{
			"USERNAME":    aws.String(username),
			"PASSWORD":    aws.String(password),
			"SECRET_HASH": aws.String(secretHash),
		},
		ClientId: aws.String(ssh_interface.config.Cognito.ClientID),
	})

	if err != nil {
		Logger.Error("authentication failed", "username", username, "error", err)
		return false
	}

	if authOutput.AuthenticationResult == nil {
		Logger.Error("no authentication result", "username", username)
		return false
	}

	return true
}
