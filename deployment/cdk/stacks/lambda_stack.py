"""Unified Lambda stack for Eidolon Engine.

This stack creates Lambda functions for both MUD Portal and Incremental game applications.
"""

import aws_cdk as cdk
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as route53_targets
from aws_cdk import aws_s3 as s3
from constructs import Construct


class ApiGatewayDomainTarget(route53.IAliasRecordTarget):
    """Wrapper for ApiGatewayDomain to fix parameter naming issue."""
    
    def __init__(self, domain_name):
        self._target = route53_targets.ApiGatewayDomain(domain_name)
    
    def bind(self, record: route53.IRecordSet, zone=None) -> route53.AliasRecordTargetConfig:
        """Bind the target to a record set with correct parameter names."""
        return self._target.bind(record, zone)


def create_api_gateway(
    scope: Construct, api_id: str, api_name: str, api_description: str, allowed_cors_origins: list
) -> apigateway.RestApi:
    """Create an API Gateway with CORS configuration.

    Args:
        scope: CDK construct scope
        api_id: Unique identifier for the API
        api_name: Name of the REST API
        api_description: Description of the API
        allowed_cors_origins: List of allowed CORS origins

    Returns:
        Configured API Gateway
    """
    return apigateway.RestApi(
        scope,
        api_id,
        rest_api_name=api_name,
        description=api_description,
        default_cors_preflight_options=apigateway.CorsOptions(
            allow_origins=allowed_cors_origins if allowed_cors_origins else ["*"],
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-Amz-Date", "X-Api-Key", "X-Amz-Security-Token"],
            allow_credentials=True if allowed_cors_origins else False,
        ),
    )


def setup_custom_domain(
    scope: Construct, prefix: str, api: apigateway.RestApi, domain_name: str, hosted_zone_id: str, api_subdomain: str
) -> None:
    """Configure custom domain for API Gateway.

    Args:
        scope: CDK construct scope
        prefix: Prefix for resource names
        api: API Gateway to map to domain
        domain_name: Base domain name
        hosted_zone_id: Route53 hosted zone ID
        api_subdomain: Subdomain for the API
    """
    # Import the existing hosted zone
    hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
        scope,
        f"{prefix}-hosted-zone",
        hosted_zone_id=hosted_zone_id,
        zone_name=domain_name,
    )

    # Create the full domain name for the API
    api_domain_name: str = f"{api_subdomain}.{domain_name}"

    # Create ACM certificate for the API domain
    certificate = acm.Certificate(
        scope,
        f"{prefix}-api-certificate",
        domain_name=api_domain_name,
        validation=acm.CertificateValidation.from_dns(hosted_zone),
    )

    # Create custom domain for API Gateway
    custom_domain = apigateway.DomainName(
        scope,
        f"{prefix}-api-domain",
        domain_name=api_domain_name,
        certificate=certificate,
        endpoint_type=apigateway.EndpointType.REGIONAL,
        security_policy=apigateway.SecurityPolicy.TLS_1_2,
    )

    # Map the API to the custom domain
    apigateway.BasePathMapping(
        scope,
        f"{prefix}-api-mapping",
        domain_name=custom_domain,
        rest_api=api,
        base_path="",  # Map to root of domain
    )

    # Create Route53 alias record for the custom domain
    route53.ARecord(
        scope,
        f"{prefix}-api-record",
        zone=hosted_zone,
        record_name=api_subdomain,
        target=route53.RecordTarget.from_alias(ApiGatewayDomainTarget(custom_domain)),
    )


def validate_config(config: dict) -> None:
    """Validate required configuration parameters.

    Args:
        config: Configuration dictionary to validate

    Raises:
        ValueError: If required configuration is missing
    """
    required_fields: list = [
        "lambda_bucket",
        "players_table",
        "characters_table",
        "archetypes_table",
        "cognito_user_pool_arn",
        "dependencies_layer_arn",
        "domain_name",
        "hosted_zone_id",
        "lambda_execution_role_arn",
    ]

    missing_fields: list = [field for field in required_fields if not config.get(field)]
    if missing_fields:
        raise ValueError(f"Missing required configuration fields: {', '.join(missing_fields)}")


class LambdaStack(cdk.Stack):
    """Creates Lambda functions for Eidolon Engine applications."""

    def __init__(
        self,
        scope: Construct,
        lambda_id: str,
        config: dict,
        **kwargs,
    ) -> None:
        """Initialize the Lambda stack.

        Args:
            scope: CDK scope
            lambda_id: Stack ID
            config: Configuration dictionary containing all required parameters
            **kwargs: Additional stack properties
        """
        super().__init__(scope, lambda_id, **kwargs)

        # Validate configuration
        validate_config(config)

        # Extract common configuration
        lambda_bucket_name = config.get("lambda_bucket", "")
        if not lambda_bucket_name:
            raise ValueError("lambda_bucket must be specified in configuration")

        self.lambda_bucket = s3.Bucket.from_bucket_name(self, "lambda-bucket", lambda_bucket_name)
        self.players_table = config.get("players_table", "")
        self.characters_table = config.get("characters_table", "")
        self.archetypes_table = config.get("archetypes_table", "")
        self.items_table = config.get("items_table", "")
        self.cognito_user_pool_arn = config.get("cognito_user_pool_arn", "")
        self.dependencies_layer_arn = config.get("dependencies_layer_arn", "")
        self.domain_name = config.get("domain_name", "darkrelics.net")
        self.hosted_zone_id = config.get("hosted_zone_id", "")
        self.lambda_execution_role_arn = config.get("lambda_execution_role_arn", "")

        # Import the shared Lambda execution role
        self.lambda_execution_role = iam.Role.from_role_arn(self, "imported-lambda-execution-role", self.lambda_execution_role_arn)

        # Extract API configuration
        self.api_subdomain = config.get("api_subdomain", "api")
        self.allowed_cors_origins = config.get("allowed_cors_origins", [])

        # Extract game configuration defaults
        self.default_health = config.get("default_health", 10)
        self.default_essence = config.get("default_essence", 3)

        # Store CORS origins for Lambda environment
        self.cors_origins_str: str = ",".join(self.allowed_cors_origins) if self.allowed_cors_origins else ""

        # Import the dependencies layer
        dependencies_layer = lambda_.LayerVersion.from_layer_version_arn(self, "imported-layer", self.dependencies_layer_arn)

        # Create API Gateway
        self.api = create_api_gateway(
            self, "eidolon-api", "eidolon-engine-api", "API for Eidolon Engine game services", self.allowed_cors_origins
        )

        # Create Cognito authorizer
        self.cognito_authorizer = apigateway.CognitoUserPoolsAuthorizer(
            self,
            "eidolon-api-authorizer",
            cognito_user_pools=[cognito.UserPool.from_user_pool_arn(self, "imported-user-pool", self.cognito_user_pool_arn)],
            authorizer_name="eidolon-api-authorizer",
            identity_source="method.request.header.Authorization",
        )

        # Create all Lambda functions
        self.create_character_management_functions(dependencies_layer)
        self.create_cognito_trigger_functions(dependencies_layer)

        # Configure API routes
        self.configure_api_routes()

        # Configure custom domain
        setup_custom_domain(self, "eidolon", self.api, self.domain_name, self.hosted_zone_id, self.api_subdomain)

        # Create CloudWatch log groups
        self.create_log_groups()

        # Output values
        self.create_outputs()

    def create_lambda_function(
        self, function_id: str, handler: str, environment: dict, description: str, dependencies_layer
    ) -> lambda_.Function:
        """Create a Lambda function with standard settings.

        Args:
            function_id: CDK construct ID and function name
            handler: Lambda handler (e.g., 'api_get_archetypes.lambda_handler')
            environment: Environment variables
            description: Function description
            dependencies_layer: Lambda layer for dependencies

        Returns:
            The created Lambda function
        """
        return lambda_.Function(
            self,
            function_id,
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler=handler,
            code=lambda_.Code.from_bucket(self.lambda_bucket, f"{function_id}.zip"),
            layers=[dependencies_layer],
            role=self.lambda_execution_role,
            timeout=cdk.Duration.seconds(30),
            memory_size=128,
            environment=environment,
            description=description,
            function_name=function_id,
        )

    def create_character_management_functions(self, dependencies_layer: lambda_.ILayerVersion) -> None:
        """Create Lambda functions for character management.

        Args:
            dependencies_layer: Lambda layer
        """
        # Get Archetypes Lambda
        self.get_archetypes_function = self.create_lambda_function(
            "api-get-archetypes",
            "api_get_archetypes.lambda_handler",
            {
                "ARCHETYPES_TABLE": self.archetypes_table,
                "ALLOWED_ORIGINS": self.cors_origins_str,
            },
            "Returns available archetypes",
            dependencies_layer,
        )

        # Add Character Lambda
        self.add_character_function = self.create_lambda_function(
            "api-add-character",
            "api_add_character.lambda_handler",
            {
                "PLAYERS_TABLE": self.players_table,
                "CHARACTERS_TABLE": self.characters_table,
                "ARCHETYPES_TABLE": self.archetypes_table,
                "MAX_CHARACTERS_PER_PLAYER": "10",
                "ALLOWED_ORIGINS": self.cors_origins_str,
                "DEFAULT_HEALTH": str(self.default_health),
                "DEFAULT_ESSENCE": str(self.default_essence),
            },
            "Creates new character for players",
            dependencies_layer,
        )

        # Get Character Lambda
        self.get_character_function = self.create_lambda_function(
            "api-get-character",
            "api_get_character.lambda_handler",
            {
                "PLAYERS_TABLE": self.players_table,
                "CHARACTERS_TABLE": self.characters_table,
                "ALLOWED_ORIGINS": self.cors_origins_str,
            },
            "Gets a specific character",
            dependencies_layer,
        )

        # List Characters Lambda
        self.list_characters_function = self.create_lambda_function(
            "api-list-characters",
            "api_list_characters.lambda_handler",
            {
                "PLAYERS_TABLE": self.players_table,
                "CHARACTERS_TABLE": self.characters_table,
                "ALLOWED_ORIGINS": self.cors_origins_str,
            },
            "Lists all characters for players",
            dependencies_layer,
        )

        # Delete Character Lambda
        self.delete_character_function = self.create_lambda_function(
            "api-delete-character",
            "api_delete_character.lambda_handler",
            {
                "PLAYERS_TABLE": self.players_table,
                "CHARACTERS_TABLE": self.characters_table,
                "ITEMS_TABLE": self.items_table,
                "ALLOWED_ORIGINS": self.cors_origins_str,
            },
            "Deletes a character for players",
            dependencies_layer,
        )

    def create_cognito_trigger_functions(self, dependencies_layer: lambda_.ILayerVersion) -> None:
        """Create Lambda functions for Cognito triggers.

        Args:
            dependencies_layer: Lambda layer
        """
        # New Player Trigger Lambda
        self.cognito_new_player_function = self.create_lambda_function(
            "cognito-new-player",
            "cognito_new_player.lambda_handler",
            {
                "PLAYERS_TABLE": self.players_table,
            },
            "Creates new player entry when user signs up",
            dependencies_layer,
        )

        # Delete Player Trigger Lambda
        self.cognito_delete_player_function = self.create_lambda_function(
            "cognito-delete-player",
            "cognito_delete_player.lambda_handler",
            {
                "PLAYERS_TABLE": self.players_table,
                "CHARACTERS_TABLE": self.characters_table,
                "ITEMS_TABLE": self.items_table,
            },
            "Cleans up player data when user account is deleted",
            dependencies_layer,
        )

    def configure_api_routes(self) -> None:
        """Configure API Gateway routes and methods."""
        # Archetypes endpoint
        archetypes_resource = self.api.root.add_resource("archetypes")
        archetypes_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.get_archetypes_function),  # type: ignore
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO,
        )

        # Characters endpoints
        characters_resource = self.api.root.add_resource("characters")

        # POST /characters - Add new character
        characters_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.add_character_function),  # type: ignore
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO,
        )

        # GET /characters - List all characters
        characters_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.list_characters_function),  # type: ignore
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO,
        )

        # Single character resource
        character_resource = characters_resource.add_resource("{characterId}")

        # GET /characters/{characterId} - Get specific character
        character_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.get_character_function),  # type: ignore
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO,
        )

        # DELETE /characters/{characterId} - Delete specific character
        character_resource.add_method(
            "DELETE",
            apigateway.LambdaIntegration(self.delete_character_function),  # type: ignore
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO,
        )

    def create_log_groups(self) -> None:
        """Create CloudWatch log groups for all Lambda functions."""
        log_configs: list = [
            ("get-archetypes-logs", self.get_archetypes_function),
            ("add-character-logs", self.add_character_function),
            ("get-character-logs", self.get_character_function),
            ("list-characters-logs", self.list_characters_function),
            ("delete-character-logs", self.delete_character_function),
            ("cognito-new-player-logs", self.cognito_new_player_function),
            ("cognito-delete-player-logs", self.cognito_delete_player_function),
        ]

        for log_id, function in log_configs:
            logs.LogGroup(
                self,
                log_id,
                log_group_name=f"/aws/lambda/{function.function_name}",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=cdk.RemovalPolicy.DESTROY,
            )

    def create_outputs(self) -> None:
        """Create CloudFormation outputs."""
        api_domain_name: str = f"{self.api_subdomain}.{self.domain_name}"

        cdk.CfnOutput(
            self,
            "ApiCustomDomainUrl",
            value=f"https://{api_domain_name}",
            description="Custom domain URL for Eidolon Engine API",
        )

        cdk.CfnOutput(
            self,
            "ApiGatewayUrl",
            value=self.api.url,
            description="Eidolon Engine API Gateway base URL",
        )

        cdk.CfnOutput(
            self,
            "ArchetypesEndpoint",
            value=self.api.url_for_path("/archetypes"),
            description="API endpoint for archetypes",
        )

        cdk.CfnOutput(
            self,
            "CharactersEndpoint",
            value=self.api.url_for_path("/characters"),
            description="API endpoint for characters",
        )
