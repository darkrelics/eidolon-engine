"""MUD-specific Lambda stack for Eidolon Engine.

This stack creates Lambda functions specific to the MUD Portal application.
"""

import aws_cdk as cdk
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as targets
from aws_cdk import aws_s3 as s3
from constructs import Construct


class MudLambdaStack(cdk.Stack):
    """Creates MUD-specific Lambda functions for Eidolon Engine."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        lambda_bucket: s3.IBucket,
        shared_players_table: str,
        mud_characters_table: str,
        mud_items_table: str,
        mud_ARCHETYPES_TABLE: str,
        cognito_user_pool_arn: str,
        shared_dependencies_layer_arn: str,
        domain_name: str,
        hosted_zone_id: str,
        api_subdomain: str = "mud-api",
        **kwargs,
    ) -> None:
        """Initialize the MUD Lambda stack.

        Args:
            scope: CDK scope
            id: Stack ID
            lambda_bucket: S3 bucket containing Lambda deployment packages
            shared_players_table: Name of the shared players DynamoDB table
            mud_characters_table: Name of the MUD characters DynamoDB table
            mud_items_table: Name of the MUD items DynamoDB table
            mud_ARCHETYPES_TABLE: Name of the MUD archetypes DynamoDB table
            cognito_user_pool_arn: ARN of the Cognito user pool
            shared_dependencies_layer_arn: ARN of the shared Lambda dependencies layer
            domain_name: Domain name for API (required)
            hosted_zone_id: Route53 hosted zone ID (required)
            api_subdomain: Subdomain for API (default: "mud-api")
            **kwargs: Additional stack properties
        """
        super().__init__(scope, id, **kwargs)

        # Import the shared dependencies layer
        shared_dependencies_layer = lambda_.LayerVersion.from_layer_version_arn(
            self, "imported-shared-layer", shared_dependencies_layer_arn
        )

        # Create IAM role for Archetypes Lambda
        archetypes_lambda_role = iam.Role(
            self,
            "mud-archetypes-lambda",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
            ],
        )

        # Add DynamoDB permissions for archetypes table
        archetypes_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["dynamodb:Scan", "dynamodb:Query", "dynamodb:GetItem"],
                resources=[f"arn:aws:dynamodb:{self.region}:{self.account}:table/{mud_ARCHETYPES_TABLE}"],
            )
        )

        # Create get player archetypes Lambda function
        self.api_get_archetypes_function = lambda_.Function(
            self,
            "mud-get-player-archetypes",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="api_get_archetypes.lambda_handler",
            code=lambda_.Code.from_bucket(lambda_bucket, "api_get_archetypes.zip"),
            layers=[shared_dependencies_layer],
            role=archetypes_lambda_role,
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
            environment={
                "ARCHETYPES_TABLE": mud_ARCHETYPES_TABLE,
            },
            description="Returns player-available archetypes for MUD",
        )

        # Create IAM role for Save Character Lambda
        api_save_character_lambda_role = iam.Role(
            self,
            "mud-save-character-lambda",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
            ],
        )

        # Add DynamoDB permissions for save character function
        api_save_character_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query", "dynamodb:Scan"],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{shared_players_table}",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{mud_characters_table}",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{mud_ARCHETYPES_TABLE}",
                ],
            )
        )

        # Create save character Lambda function
        self.api_save_character_function = lambda_.Function(
            self,
            "mud-save-character",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="api_save_character.lambda_handler",
            code=lambda_.Code.from_bucket(lambda_bucket, "api_save_character.zip"),
            layers=[shared_dependencies_layer],
            role=api_save_character_lambda_role,
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
            environment={
                "players_table": shared_players_table,
                "characters_table": mud_characters_table,
                "ARCHETYPES_TABLE": mud_ARCHETYPES_TABLE,
                "MAX_CHARACTERS_PER_PLAYER": "10",
            },
            description="Creates new character for MUD players",
        )

        # Create IAM role for List Characters Lambda
        api_list_characters_lambda_role = iam.Role(
            self,
            "mud-list-characters-lambda",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
            ],
        )

        # Add DynamoDB permissions for list characters function
        api_list_characters_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["dynamodb:GetItem", "dynamodb:Query"],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{shared_players_table}",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{mud_characters_table}",
                ],
            )
        )

        # Create list characters Lambda function
        self.list_characters_function = lambda_.Function(
            self,
            "mud-list-characters",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="api_list_characters.lambda_handler",
            code=lambda_.Code.from_bucket(lambda_bucket, "api_list_characters.zip"),
            layers=[shared_dependencies_layer],
            role=api_list_characters_lambda_role,
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
            environment={
                "players_table": shared_players_table,
                "characters_table": mud_characters_table,
            },
            description="Lists all characters for MUD players",
        )

        # Create IAM role for Delete Character Lambda
        api_delete_character_lambda_role = iam.Role(
            self,
            "mud-delete-character-lambda",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
            ],
        )

        # Add DynamoDB permissions for delete character function
        api_delete_character_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["dynamodb:GetItem", "dynamodb:DeleteItem", "dynamodb:UpdateItem"],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{shared_players_table}",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{mud_characters_table}",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{mud_items_table}",
                ],
            )
        )

        # Create delete character Lambda function
        self.api_delete_character_function = lambda_.Function(
            self,
            "mud-delete-character",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="api_delete_character.lambda_handler",
            code=lambda_.Code.from_bucket(lambda_bucket, "api_delete_character.zip"),
            layers=[shared_dependencies_layer],
            role=api_delete_character_lambda_role,
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
            environment={
                "players_table": shared_players_table,
                "characters_table": mud_characters_table,
                "items_table": mud_items_table,
            },
            description="Deletes a character for MUD players",
        )

        # Create API Gateway
        self.api = apigateway.RestApi(
            self,
            "mud-api",
            rest_api_name="mud-portal-api",
            description="API for MUD Portal game services",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=["*"],  # Configure based on your needs
                allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                allow_headers=["Content-Type", "Authorization"],
            ),
        )

        # Create Cognito authorizer
        self.cognito_authorizer = apigateway.CognitoUserPoolsAuthorizer(
            self,
            "mud-api-authorizer",
            cognito_user_pools=[cognito.UserPool.from_user_pool_arn(self, "imported-user-pool", cognito_user_pool_arn)],
            authorizer_name="mud-api-authorizer",
            identity_source="method.request.header.Authorization",
        )

        # Add archetypes resource and method (authenticated endpoint)
        archetypes_resource = self.api.root.add_resource("archetypes")
        archetypes_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.api_get_archetypes_function),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO_USER_POOLS,
        )

        # Add characters resource and methods (authenticated endpoints)
        characters_resource = self.api.root.add_resource("characters")

        # POST /characters - Create new character
        characters_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.api_save_character_function),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO_USER_POOLS,
        )

        # GET /characters - List player's characters
        characters_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.list_characters_function),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO_USER_POOLS,
        )

        # DELETE /characters - Delete a character
        characters_resource.add_method(
            "DELETE",
            apigateway.LambdaIntegration(self.api_delete_character_function),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO_USER_POOLS,
        )

        # Configure custom domain (required)
        # Import the existing hosted zone
        hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
            self,
            "mud-hosted-zone",
            hosted_zone_id=hosted_zone_id,
            zone_name=domain_name,
        )

        # Create the full domain name for the API
        api_domain_name = f"{api_subdomain}.{domain_name}"

        # Create ACM certificate for the API domain
        certificate = acm.Certificate(
            self,
            "mud-api-certificate",
            domain_name=api_domain_name,
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )

        # Create custom domain for API Gateway
        custom_domain = apigateway.DomainName(
            self,
            "mud-api-domain",
            domain_name=api_domain_name,
            certificate=certificate,
            endpoint_type=apigateway.EndpointType.REGIONAL,
            security_policy=apigateway.SecurityPolicy.TLS_1_2,
        )

        # Map the API to the custom domain
        apigateway.BasePathMapping(
            self,
            "mud-api-mapping",
            domain_name=custom_domain,
            rest_api=self.api,
            base_path="",  # Map to root of domain
        )

        # Create Route53 alias record for the custom domain
        route53.ARecord(
            self,
            "mud-api-record",
            zone=hosted_zone,
            record_name=api_subdomain,
            target=route53.RecordTarget.from_alias(targets.ApiGatewayDomain(custom_domain)),
        )

        # Create CloudWatch log groups with retention
        logs.LogGroup(
            self,
            "mud-archetypes-lambda-logs",
            log_group_name=f"/aws/lambda/{self.api_get_archetypes_function.function_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        logs.LogGroup(
            self,
            "mud-save-character-lambda-logs",
            log_group_name=f"/aws/lambda/{self.api_save_character_function.function_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        logs.LogGroup(
            self,
            "mud-list-characters-lambda-logs",
            log_group_name=f"/aws/lambda/{self.list_characters_function.function_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        logs.LogGroup(
            self,
            "mud-delete-character-lambda-logs",
            log_group_name=f"/aws/lambda/{self.api_delete_character_function.function_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # Output values
        cdk.CfnOutput(
            self,
            "MudApiCustomDomainUrl",
            value=f"https://{api_domain_name}",
            description="Custom domain URL for MUD Portal API",
        )

        cdk.CfnOutput(
            self,
            "MudApiGatewayUrl",
            value=self.api.url,
            description="MUD Portal API Gateway base URL",
        )

        cdk.CfnOutput(
            self,
            "MudArchetypesEndpoint",
            value=self.api.url_for_path("/archetypes"),
            description="MUD Portal API endpoint for archetypes",
        )

        cdk.CfnOutput(
            self,
            "MudCharactersEndpoint",
            value=self.api.url_for_path("/characters"),
            description="MUD Portal API endpoint for characters",
        )
