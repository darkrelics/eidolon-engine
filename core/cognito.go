package core

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"fmt"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/awserr"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/cognitoidentityprovider"
)

func calculateSecretHash(cognitoAppClientID, clientSecret, email string) string {
	message := []byte(email + cognitoAppClientID)
	key := []byte(clientSecret)
	hash := hmac.New(sha256.New, key)
	hash.Write(message)
	hashedMessage := hash.Sum(nil)
	encodedMessage := base64.StdEncoding.EncodeToString(hashedMessage)
	return encodedMessage
}

func handleCognitoError(err error, email string) error {
	if awsErr, ok := err.(awserr.Error); ok {
		switch awsErr.Code() {
		case cognitoidentityprovider.ErrCodeNotAuthorizedException:
			return fmt.Errorf("incorrect username or password")
		case cognitoidentityprovider.ErrCodeUserNotConfirmedException:
			return fmt.Errorf("user is not confirmed")
		case cognitoidentityprovider.ErrCodePasswordResetRequiredException:
			return fmt.Errorf("password reset required")
		default:
			return fmt.Errorf("authentication failed for user %s: %w", email, awsErr)
		}
	}
	return fmt.Errorf("unexpected error during authentication for user %s: %w", email, err)
}

// SignInUser attempts to sign in a user with the provided credentials
func SignInUser(email, password string, config *Configuration) (*cognitoidentityprovider.InitiateAuthOutput, error) {
	sess, err := session.NewSession(&aws.Config{Region: aws.String(config.Aws.Region)})
	if err != nil {
		return nil, fmt.Errorf("create AWS session: %w", err)
	}

	cognitoClient := cognitoidentityprovider.New(sess)
	secretHash := calculateSecretHash(config.Cognito.ClientID, config.Cognito.ClientSecret, email)

	authInput := &cognitoidentityprovider.InitiateAuthInput{
		AuthFlow: aws.String(cognitoidentityprovider.AuthFlowTypeUserPasswordAuth),
		AuthParameters: map[string]*string{
			"USERNAME":    aws.String(email),
			"PASSWORD":    aws.String(password),
			"SECRET_HASH": aws.String(secretHash),
		},
		ClientId: aws.String(config.Cognito.ClientID),
	}

	authOutput, err := cognitoClient.InitiateAuth(authInput)
	if err != nil {
		return nil, handleCognitoError(err, email)
	}

	// Check for NEW_PASSWORD_REQUIRED challenge
	if authOutput.ChallengeName != nil && *authOutput.ChallengeName == cognitoidentityprovider.ChallengeNameTypeNewPasswordRequired {
		return authOutput, nil // Return the challenge, not an error
	}

	if authOutput.AuthenticationResult == nil {
		return nil, fmt.Errorf("unexpected authentication result for user %s", email)
	}

	return authOutput, nil
}

func SignUpUser(email, password string, config Configuration) (*cognitoidentityprovider.SignUpOutput, error) {
	sess, err := session.NewSession(&aws.Config{Region: aws.String(config.Aws.Region)})
	if err != nil {
		Logger.Error("Error creating AWS session for sign-up", "error", err)
		return nil, fmt.Errorf("an internal error occurred while creating AWS session")
	}

	cognitoClient := cognitoidentityprovider.New(sess)
	secretHash := calculateSecretHash(config.Cognito.ClientID, config.Cognito.ClientSecret, email)

	signUpInput := &cognitoidentityprovider.SignUpInput{
		ClientId:   aws.String(config.Cognito.ClientID),
		Username:   aws.String(email),
		Password:   aws.String(password),
		SecretHash: aws.String(secretHash),
		UserAttributes: []*cognitoidentityprovider.AttributeType{
			{Name: aws.String("email"), Value: aws.String(email)},
		},
	}

	signUpOutput, err := cognitoClient.SignUp(signUpInput)
	if err != nil {
		Logger.Error("Error signing up user with Cognito", "email", email, "error", err)
		return nil, fmt.Errorf("error signing up, please try again")
	}

	return signUpOutput, nil
}

func ConfirmUser(email, confirmationCode string, config Configuration) (*cognitoidentityprovider.ConfirmSignUpOutput, error) {
	sess, err := session.NewSession(&aws.Config{Region: aws.String(config.Aws.Region)})
	if err != nil {
		Logger.Error("Error creating AWS session for user confirmation", "error", err)
		return nil, fmt.Errorf("an internal error occurred while creating AWS session")
	}

	cognitoClient := cognitoidentityprovider.New(sess)
	secretHash := calculateSecretHash(config.Cognito.ClientID, config.Cognito.ClientSecret, email)

	confirmSignUpInput := &cognitoidentityprovider.ConfirmSignUpInput{
		ClientId:         aws.String(config.Cognito.ClientID),
		Username:         aws.String(email),
		ConfirmationCode: aws.String(confirmationCode),
		SecretHash:       aws.String(secretHash),
	}

	confirmSignUpOutput, err := cognitoClient.ConfirmSignUp(confirmSignUpInput)
	if err != nil {
		Logger.Error("Error confirming sign-up for user", "email", email, "error", err)
		return nil, fmt.Errorf("error confirming sign up, please check your code and try again")
	}

	return confirmSignUpOutput, nil
}

func GetUserData(accessToken string, config Configuration) (*cognitoidentityprovider.GetUserOutput, error) {
	sess, err := session.NewSession(&aws.Config{Region: aws.String(config.Aws.Region)})
	if err != nil {
		Logger.Error("Error creating AWS session for getting user data", "error", err)
		return nil, fmt.Errorf("an internal error occurred while creating AWS session")
	}

	cognitoClient := cognitoidentityprovider.New(sess)

	getUserInput := &cognitoidentityprovider.GetUserInput{AccessToken: aws.String(accessToken)}
	userOutput, err := cognitoClient.GetUser(getUserInput)
	if err != nil {
		Logger.Error("Error getting user data with access token", "error", err)
		return nil, fmt.Errorf("error retrieving user data, please try again")
	}

	return userOutput, nil
}

func ChangePassword(player *Player, oldPassword, newPassword string) error {

	username := player.PlayerID

	Logger.Debug("Attempting to change password for user", "username", username)

	// Step 1: Authenticate the user
	Logger.Debug("Step 1: Authenticating user", "username", username)
	signInOutput, err := SignInUser(username, oldPassword, player.Game.Config)
	if err != nil {
		Logger.Error("Authentication failed for user", "username", username, "error", err)
		return fmt.Errorf("authentication failed: %v", err)
	}
	Logger.Debug("Authentication successful for user", "username", username)
	Logger.Debug("SignInOutput for user", "username", username, "signInOutput", signInOutput)

	// Step 2: Handle NEW_PASSWORD_REQUIRED challenge if present
	if signInOutput.ChallengeName != nil && *signInOutput.ChallengeName == cognitoidentityprovider.ChallengeNameTypeNewPasswordRequired {
		Logger.Debug("NEW_PASSWORD_REQUIRED challenge detected for user", "username", username)

		// Create a new AWS session
		sess, err := session.NewSession(&aws.Config{
			Region: aws.String(player.Game.Config.Aws.Region),
		})
		if err != nil {
			Logger.Error("Failed to create AWS session for user", "username", username, "error", err)
			return fmt.Errorf("failed to create AWS session: %v", err)
		}

		// Create Cognito Identity Provider client
		cognitoClient := cognitoidentityprovider.New(sess)

		// Calculate SECRET_HASH
		secretHash := calculateSecretHash(player.Game.Config.Cognito.ClientID, player.Game.Config.Cognito.ClientSecret, username)

		// Respond to the NEW_PASSWORD_REQUIRED challenge
		challengeResponseInput := &cognitoidentityprovider.RespondToAuthChallengeInput{
			ChallengeName: aws.String(cognitoidentityprovider.ChallengeNameTypeNewPasswordRequired),
			ClientId:      aws.String(player.Game.Config.Cognito.ClientID),
			ChallengeResponses: map[string]*string{
				"USERNAME":     aws.String(username),
				"NEW_PASSWORD": aws.String(newPassword),
				"SECRET_HASH":  aws.String(secretHash),
			},
			Session: signInOutput.Session,
		}

		Logger.Debug("Sending challenge response for user", "username", username)
		challengeResponse, err := cognitoClient.RespondToAuthChallenge(challengeResponseInput)
		if err != nil {
			Logger.Error("Failed to respond to NEW_PASSWORD_REQUIRED challenge for user", "username", username, "error", err)
			return fmt.Errorf("failed to set new password: %v", err)
		}

		Logger.Debug("Successfully responded to NEW_PASSWORD_REQUIRED challenge for user", "username", username)
		Logger.Debug("Challenge response", "challengeResponse", challengeResponse)

		// Password has been changed successfully
		return nil
	}

	// If we're here, it means there was no NEW_PASSWORD_REQUIRED challenge
	// In this case, we need to use the ChangePassword API as before

	if signInOutput.AuthenticationResult == nil || signInOutput.AuthenticationResult.AccessToken == nil {
		Logger.Warn("No valid access token for user", "username", username)
		return fmt.Errorf("no valid access token available")
	}

	// Create a new AWS session
	sess, err := session.NewSession(&aws.Config{
		Region: aws.String(player.Game.Config.Aws.Region),
	})
	if err != nil {
		Logger.Error("Failed to create AWS session for user", "username", username, "error", err)
		return fmt.Errorf("failed to create AWS session: %v", err)
	}

	// Create Cognito Identity Provider client
	cognitoClient := cognitoidentityprovider.New(sess)

	// Perform the change password operation
	input := &cognitoidentityprovider.ChangePasswordInput{
		PreviousPassword: aws.String(oldPassword),
		ProposedPassword: aws.String(newPassword),
		AccessToken:      signInOutput.AuthenticationResult.AccessToken,
	}

	_, err = cognitoClient.ChangePassword(input)
	if err != nil {
		Logger.Error("Failed to change password for user", "username", username, "error", err)
		return fmt.Errorf("failed to change password: %v", err)
	}

	Logger.Info("Password successfully changed for user", "username", username)
	return nil
}
