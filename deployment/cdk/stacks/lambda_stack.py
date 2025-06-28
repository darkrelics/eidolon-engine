"""Lambda stack for Eidolon Engine.

This stack creates Lambda functions and layers for the game server.
"""

import aws_cdk as cdk
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as targets
from aws_cdk import aws_s3 as s3
from constructs import Construct


class LambdaStack(cdk.Stack):
    """Creates Lambda functions and layers for Eidolon Engine."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        game_name: str,
        lambda_bucket: s3.IBucket,
        players_table_name: str,
        characters_table_name: str,
        archetypes_table_name: str,
        cognito_user_pool_arn: str,
        domain_name: str,
        hosted_zone_id: str,
        api_subdomain: str = "api",
        **kwargs,
    ) -> None:
        """Initialize the Lambda stack.

        Args:
            scope: CDK scope
            id: Stack ID
            game_name: Name of the game
            lambda_bucket: S3 bucket containing Lambda deployment packages
            players_table_name: Name of the players DynamoDB table
            characters_table_name: Name of the characters DynamoDB table
            archetypes_table_name: Name of the archetypes DynamoDB table
            cognito_user_pool_arn: ARN of the Cognito user pool
            domain_name: Domain name for API (required)
            hosted_zone_id: Route53 hosted zone ID (required)
            api_subdomain: Subdomain for API (default: "api")
            **kwargs: Additional stack properties
        """
        super().__init__(scope, id, **kwargs)

        # Create Lambda layer for shared dependencies
        self.dependencies_layer = lambda_.LayerVersion(
            self,
            f"{game_name}-lambda-dependencies",
            code=lambda_.Code.from_bucket(lambda_bucket, "lambda-layer.zip"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
            description="Shared dependencies for Eidolon Engine Lambda functions",
        )

        # Create IAM role for Cognito Lambda
        cognito_lambda_role = iam.Role(
            self,
            f"{game_name}-cognito-lambda-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )

        # Add DynamoDB permissions for players table
        cognito_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["dynamodb:GetItem", "dynamodb:PutItem"],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{players_table_name}"
                ],
            )
        )

        # Create Cognito new player Lambda function
        self.cognito_new_player_function = lambda_.Function(
            self,
            f"{game_name}-cognito-new-player",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="cognito_new_player.lambda_handler",
            code=lambda_.Code.from_bucket(lambda_bucket, "cognito_new_player.zip"),
            layers=[self.dependencies_layer],
            role=cognito_lambda_role,
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
            environment={
                "PLAYERS_TABLE_NAME": players_table_name,
            },
            description="Creates new player records after Cognito user confirmation",
        )

        # Grant Cognito permission to invoke the Lambda function
        self.cognito_new_player_function.grant_invoke(
            iam.ServicePrincipal("cognito-idp.amazonaws.com",
                conditions={
                    "ArnLike": {
                        "aws:SourceArn": cognito_user_pool_arn
                    }
                }
            )
        )

        # Create IAM role for Archetypes Lambda
        archetypes_lambda_role = iam.Role(
            self,
            f"{game_name}-archetypes-lambda-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )

        # Add DynamoDB permissions for archetypes table
        archetypes_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["dynamodb:Scan", "dynamodb:Query", "dynamodb:GetItem"],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{archetypes_table_name}"
                ],
            )
        )

        # Create get player archetypes Lambda function
        self.get_player_archetypes_function = lambda_.Function(
            self,
            f"{game_name}-get-player-archetypes",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="get_player_archetypes.lambda_handler",
            code=lambda_.Code.from_bucket(lambda_bucket, "get_player_archetypes.zip"),
            layers=[self.dependencies_layer],
            role=archetypes_lambda_role,
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
            environment={
                "ARCHETYPES_TABLE_NAME": archetypes_table_name,
            },
            description="Returns player-available archetypes from cached data",
        )


        # Create IAM role for Save Character Lambda
        save_character_lambda_role = iam.Role(
            self,
            f"{game_name}-save-character-lambda-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )

        # Add DynamoDB permissions for save character function
        save_character_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query",
                    "dynamodb:Scan"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{players_table_name}",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{characters_table_name}",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{archetypes_table_name}",
                ],
            )
        )

        # Create save character Lambda function
        self.save_character_function = lambda_.Function(
            self,
            f"{game_name}-save-character",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="save_character.lambda_handler",
            code=lambda_.Code.from_bucket(lambda_bucket, "save_character.zip"),
            layers=[self.dependencies_layer],
            role=save_character_lambda_role,
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
            environment={
                "PLAYERS_TABLE_NAME": players_table_name,
                "CHARACTERS_TABLE_NAME": characters_table_name,
                "ARCHETYPES_TABLE_NAME": archetypes_table_name,
                "MAX_CHARACTERS_PER_PLAYER": "10",
            },
            description="Creates new character for authenticated players",
        )

        # Create API Gateway
        self.api = apigateway.RestApi(
            self,
            f"{game_name}-api",
            rest_api_name=f"{game_name}-api",
            description="API for Eidolon Engine game services",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=["*"],  # Configure based on your needs
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["Content-Type", "Authorization"],
            ),
        )

        # Create Cognito authorizer
        self.cognito_authorizer = apigateway.CognitoUserPoolsAuthorizer(
            self,
            f"{game_name}-api-authorizer",
            cognito_user_pools=[
                cognito.UserPool.from_user_pool_arn(self, "imported-user-pool", cognito_user_pool_arn)
            ],
            authorizer_name=f"{game_name}-api-authorizer",
            identity_source="method.request.header.Authorization",
        )

        # Add archetypes resource and method (authenticated endpoint)
        archetypes_resource = self.api.root.add_resource("archetypes")
        archetypes_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.get_player_archetypes_function),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO_USER_POOLS,
        )

        # Add characters resource and method (authenticated endpoint)
        characters_resource = self.api.root.add_resource("characters")
        characters_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.save_character_function),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO_USER_POOLS,
        )

        # Configure custom domain (required)
        # Import the existing hosted zone
        hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
            self,
            f"{game_name}-hosted-zone",
            hosted_zone_id=hosted_zone_id,
            zone_name=domain_name,
        )

        # Create the full domain name for the API
        api_domain_name = f"{api_subdomain}.{domain_name}"

        # Create ACM certificate for the API domain
        certificate = acm.Certificate(
            self,
            f"{game_name}-api-certificate",
            domain_name=api_domain_name,
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )

        # Create custom domain for API Gateway
        custom_domain = apigateway.DomainName(
            self,
            f"{game_name}-api-domain",
            domain_name=api_domain_name,
            certificate=certificate,
            endpoint_type=apigateway.EndpointType.REGIONAL,
            security_policy=apigateway.SecurityPolicy.TLS_1_2,
        )

        # Map the API to the custom domain
        apigateway.BasePathMapping(
            self,
            f"{game_name}-api-mapping",
            domain_name=custom_domain,
            rest_api=self.api,
            base_path="",  # Map to root of domain
        )

        # Create Route53 alias record for the custom domain
        route53.ARecord(
            self,
            f"{game_name}-api-record",
            zone=hosted_zone,
            record_name=api_subdomain,
            target=route53.RecordTarget.from_alias(
                targets.ApiGatewayDomain(custom_domain)
            ),
        )

        # Output the custom domain URL
        cdk.CfnOutput(
            self,
            "ApiCustomDomainUrl",
            value=f"https://{api_domain_name}/archetypes",
            description="Custom domain URL for accessing archetypes API",
        )

        # Create CloudWatch log groups with retention
        logs.LogGroup(
            self,
            f"{game_name}-cognito-lambda-logs",
            log_group_name=f"/aws/lambda/{self.cognito_new_player_function.function_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        logs.LogGroup(
            self,
            f"{game_name}-archetypes-lambda-logs",
            log_group_name=f"/aws/lambda/{self.get_player_archetypes_function.function_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        logs.LogGroup(
            self,
            f"{game_name}-save-character-lambda-logs",
            log_group_name=f"/aws/lambda/{self.save_character_function.function_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # Output values
        cdk.CfnOutput(
            self,
            "CognitoLambdaFunctionArn",
            value=self.cognito_new_player_function.function_arn,
            description="ARN of the Cognito new player Lambda function",
        )

        cdk.CfnOutput(
            self,
            "ArchetypesLambdaFunctionArn",
            value=self.get_player_archetypes_function.function_arn,
            description="ARN of the get player archetypes Lambda function",
        )


        cdk.CfnOutput(
            self,
            "SaveCharacterLambdaFunctionArn",
            value=self.save_character_function.function_arn,
            description="ARN of the save character Lambda function",
        )

        cdk.CfnOutput(
            self,
            "ApiGatewayUrl",
            value=self.api.url,
            description="API Gateway base URL",
        )

        cdk.CfnOutput(
            self,
            "ArchetypesEndpoint",
            value=self.api.url_for_path("/archetypes"),
            description="API Gateway URL for accessing archetypes (requires authentication)",
        )

        cdk.CfnOutput(
            self,
            "CharactersEndpoint",
            value=self.api.url_for_path("/characters"),
            description="API Gateway URL for creating characters (requires authentication)",
        )