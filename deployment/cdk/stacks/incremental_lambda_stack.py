"""Incremental-specific Lambda stack for Eidolon Engine.

This stack creates Lambda functions specific to the Incremental game application.
"""

import aws_cdk as cdk
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as targets
from aws_cdk import aws_s3 as s3
from constructs import Construct


class IncrementalLambdaStack(cdk.Stack):
    """Creates Incremental-specific Lambda functions for Eidolon Engine."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        lambda_bucket: s3.IBucket,
        shared_players_table: str,
        incremental_progress_table_name: str,
        incremental_resources_table_name: str,
        cognito_user_pool_arn: str,
        shared_dependencies_layer_arn: str,
        domain_name: str,
        hosted_zone_id: str,
        api_subdomain: str = "incremental-api",
        allowed_cors_origins: list[str] | None = None,
        **kwargs,
    ) -> None:
        """Initialize the Incremental Lambda stack.

        Args:
            scope: CDK scope
            id: Stack ID
            lambda_bucket: S3 bucket containing Lambda deployment packages
            shared_players_table: Name of the shared players DynamoDB table
            incremental_progress_table_name: Name of the Incremental progress DynamoDB table
            incremental_resources_table_name: Name of the Incremental resources DynamoDB table
            cognito_user_pool_arn: ARN of the Cognito user pool
            shared_dependencies_layer_arn: ARN of the shared Lambda dependencies layer
            domain_name: Domain name for API (required)
            hosted_zone_id: Route53 hosted zone ID (required)
            api_subdomain: Subdomain for API (default: "incremental-api")
            allowed_cors_origins: List of allowed CORS origins
            **kwargs: Additional stack properties
        """
        super().__init__(scope, id, **kwargs)

        # Store CORS origins for Lambda environment
        self.cors_origins_str = ",".join(allowed_cors_origins) if allowed_cors_origins else ""

        # Import the shared dependencies layer
        # shared_dependencies_layer = lambda_.LayerVersion.from_layer_version_arn(
        #     self, "imported-shared-layer", shared_dependencies_layer_arn
        # )

        # Create API Gateway
        self.api = apigateway.RestApi(
            self,
            "incremental-api",
            rest_api_name="incremental-game-api",
            description="API for Incremental game services",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=allowed_cors_origins if allowed_cors_origins else ["*"],
                allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                allow_headers=["Content-Type", "Authorization"],
                allow_credentials=True if allowed_cors_origins else False,
            ),
        )

        # Create Cognito authorizer
        self.cognito_authorizer = apigateway.CognitoUserPoolsAuthorizer(
            self,
            "incremental-api-authorizer",
            cognito_user_pools=[cognito.UserPool.from_user_pool_arn(self, "imported-user-pool", cognito_user_pool_arn)],
            authorizer_name="incremental-api-authorizer",
            identity_source="method.request.header.Authorization",
        )

        # Example: Create get progress Lambda function
        # This is a template - actual functions will be added as the Incremental game is developed

        # # Create IAM role for Get Progress Lambda
        # get_progress_lambda_role = iam.Role(
        #     self,
        #     "incremental-get-progress-lambda",
        #     assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        #     managed_policies=[
        #         iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
        #     ],
        # )

        # # Add DynamoDB permissions
        # get_progress_lambda_role.add_to_policy(
        #     iam.PolicyStatement(
        #         effect=iam.Effect.ALLOW,
        #         actions=["dynamodb:GetItem", "dynamodb:Query"],
        #         resources=[
        #             f"arn:aws:dynamodb:{self.region}:{self.account}:table/{shared_players_table}",
        #             f"arn:aws:dynamodb:{self.region}:{self.account}:table/{incremental_progress_table_name}",
        #         ],
        #     )
        # )

        # # Create get progress Lambda function
        # self.get_progress_function = lambda_.Function(
        #     self,
        #     "incremental-get-progress",
        #     runtime=lambda_.Runtime.PYTHON_3_11,
        #     handler="incremental_get_progress.lambda_handler",
        #     code=lambda_.Code.from_bucket(lambda_bucket, "incremental_get_progress.zip"),
        #     layers=[shared_dependencies_layer],
        #     role=get_progress_lambda_role,
        #     timeout=cdk.Duration.seconds(30),
        #     memory_size=256,
        #     environment={
        #         "players_table": shared_players_table,
        #         "PROGRESS_TABLE_NAME": incremental_progress_table_name,
        #     },
        #     description="Gets player progress for Incremental game",
        # )

        # # Add progress resource and method
        # progress_resource = self.api.root.add_resource("progress")
        # progress_resource.add_method(
        #     "GET",
        #     apigateway.LambdaIntegration(self.get_progress_function),
        #     authorizer=self.cognito_authorizer,
        #     authorization_type=apigateway.AuthorizationType.COGNITO_USER_POOLS,
        # )

        # Configure custom domain
        # Import the existing hosted zone
        hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
            self,
            "incremental-hosted-zone",
            hosted_zone_id=hosted_zone_id,
            zone_name=domain_name,
        )

        # Create the full domain name for the API
        api_domain_name = f"{api_subdomain}.{domain_name}"

        # Create ACM certificate for the API domain
        certificate = acm.Certificate(
            self,
            "incremental-api-certificate",
            domain_name=api_domain_name,
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )

        # Create custom domain for API Gateway
        custom_domain = apigateway.DomainName(
            self,
            "incremental-api-domain",
            domain_name=api_domain_name,
            certificate=certificate,
            endpoint_type=apigateway.EndpointType.REGIONAL,
            security_policy=apigateway.SecurityPolicy.TLS_1_2,
        )

        # Map the API to the custom domain
        apigateway.BasePathMapping(
            self,
            "incremental-api-mapping",
            domain_name=custom_domain,
            rest_api=self.api,
            base_path="",  # Map to root of domain
        )

        # Create Route53 alias record for the custom domain
        route53.ARecord(
            self,
            "incremental-api-record",
            zone=hosted_zone,
            record_name=api_subdomain,
            target=route53.RecordTarget.from_alias(targets.ApiGatewayDomain(custom_domain)),
        )

        # Output values
        cdk.CfnOutput(
            self,
            "IncrementalApiCustomDomainUrl",
            value=f"https://{api_domain_name}",
            description="Custom domain URL for Incremental game API",
        )

        cdk.CfnOutput(
            self,
            "IncrementalApiGatewayUrl",
            value=self.api.url,
            description="Incremental game API Gateway base URL",
        )
