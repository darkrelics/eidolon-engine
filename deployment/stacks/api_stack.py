"""API stack for API Gateway and related resources."""

from aws_cdk import CfnOutput, Stack, Tags
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as targets
from constructs import Construct

from . import stack_utilities as utils


class ApiStack(Stack):
    """API stack for Eidolon Engine API Gateway."""

    def __init__(
        self,
        scope: Construct,
        stack_id: str,
        region_name: str,
        hosted_zone_id: str,
        domain: str,
        api_host: str = "api",
        client_host: str = "portal",
        deployment_mode: str = "hybrid",
        lambda_arns=None,
        cognito_user_pool_id: str = "",
        cognito_client_id: str = "",
        cognito_user_pool_arn: str = "",
        **kwargs,
    ) -> None:
        """Initialize API stack.

        Args:
            scope: CDK construct scope
            stack_id: Stack identifier
            region_name: AWS region
            hosted_zone_id: Route53 Hosted Zone ID
            domain: Base domain name
            api_host: Subdomain for API (default: api)
            client_host: Subdomain for client (default: portal)
            deployment_mode: Deployment mode (mud/incremental/hybrid)
            lambda_arns: Dictionary of Lambda function ARNs
            cognito_user_pool_id: Cognito User Pool ID
            cognito_client_id: Cognito Client ID
            cognito_user_pool_arn: Cognito User Pool ARN
            **kwargs: Additional stack properties
        """
        self.region_name = region_name
        self.hosted_zone_id = hosted_zone_id
        self.domain = domain
        self.api_host = api_host
        self.client_host = client_host
        self.deployment_mode = deployment_mode
        self.lambda_arns = lambda_arns or {}
        self.cognito_user_pool_id = cognito_user_pool_id
        self.cognito_client_id = cognito_client_id
        self.cognito_user_pool_arn = cognito_user_pool_arn

        super().__init__(scope, stack_id, description="API Gateway with custom domain and Lambda integrations", **kwargs)

        # Add system tag to all resources in this stack
        Tags.of(self).add("System", "Eidolon")

        # Create API Gateway
        self.api = self._create_api_gateway()

        # Add outputs
        self._add_outputs()

    def _create_api_gateway(self) -> apigateway.RestApi:
        """Create API Gateway with Lambda integrations."""
        print("  Creating API Gateway")

        # Build client origin URL
        client_origin = f"https://{self.client_host}.{self.domain}"

        # Create API
        api = apigateway.RestApi(
            self,
            "EidolonApi",
            rest_api_name="eidolon-api",
            description="Eidolon Engine API",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=[client_origin],
                allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                allow_headers=["Content-Type", "Authorization", "X-Amz-Date", "X-Api-Key", "X-Amz-Security-Token"],
                allow_credentials=True,
            ),
        )

        # Create Cognito authorizer if we have the pool ARN
        authorizer = None
        if self.cognito_user_pool_arn:
            user_pool = cognito.UserPool.from_user_pool_arn(self, "ImportedUserPool", self.cognito_user_pool_arn)
            authorizer = apigateway.CognitoUserPoolsAuthorizer(
                self,
                "ApiAuthorizer",
                cognito_user_pools=[user_pool],
                authorizer_name="eidolon-api-authorizer",
                identity_source="method.request.header.Authorization",
            )

        # Add Lambda integrations for available functions
        self._add_api_endpoints(api, authorizer)  # type: ignore

        # Configure CORS for error responses
        self._configure_gateway_responses(api, client_origin)

        # Configure custom domain
        self._configure_api_domain(api)

        return api

    def _add_api_endpoints(self, api: apigateway.RestApi, authorizer: apigateway.CognitoUserPoolsAuthorizer) -> None:
        """Add API endpoints with Lambda integrations."""
        # Archetype endpoints
        if "api-archetype-list" in self.lambda_arns:
            archetype_resource = api.root.add_resource("archetype")
            self._add_lambda_integration(archetype_resource, "GET", "api-archetype-list", authorizer)

        # Character endpoints
        character_resource = api.root.add_resource("character")

        if "api-character-add" in self.lambda_arns:
            self._add_lambda_integration(character_resource, "POST", "api-character-add", authorizer)

        if "api-character-get" in self.lambda_arns:
            self._add_lambda_integration(character_resource, "GET", "api-character-get", authorizer)

        if "api-character-delete" in self.lambda_arns:
            self._add_lambda_integration(character_resource, "DELETE", "api-character-delete", authorizer)

        if "api-character-list" in self.lambda_arns:
            list_resource = character_resource.add_resource("list")
            self._add_lambda_integration(list_resource, "GET", "api-character-list", authorizer)

        # Story endpoints (for incremental/hybrid modes)
        if self.deployment_mode in ["incremental", "hybrid"]:
            story_resource = api.root.add_resource("story")

            if "api-story-start" in self.lambda_arns:
                start_resource = story_resource.add_resource("start")
                self._add_lambda_integration(start_resource, "POST", "api-story-start", authorizer)

            if "api-story-abandon" in self.lambda_arns:
                abandon_resource = story_resource.add_resource("abandon")
                self._add_lambda_integration(abandon_resource, "POST", "api-story-abandon", authorizer)

            # Segment endpoints
            segment_resource = api.root.add_resource("segment")

            if "api-segment-decision" in self.lambda_arns:
                decision_resource = segment_resource.add_resource("decision")
                self._add_lambda_integration(decision_resource, "POST", "api-segment-decision", authorizer)

            if "api-segment-outcome" in self.lambda_arns:
                outcome_resource = segment_resource.add_resource("outcome")
                self._add_lambda_integration(outcome_resource, "GET", "api-segment-outcome", authorizer)

            if "api-segment-status" in self.lambda_arns:
                status_resource = segment_resource.add_resource("status")
                self._add_lambda_integration(status_resource, "GET", "api-segment-status", authorizer)

            if "api-segment-history" in self.lambda_arns:
                history_resource = segment_resource.add_resource("history")
                self._add_lambda_integration(history_resource, "GET", "api-segment-history", authorizer)

            if "api-segment-rest" in self.lambda_arns:
                rest_resource = segment_resource.add_resource("rest")
                self._add_lambda_integration(rest_resource, "POST", "api-segment-rest", authorizer)

    def _add_lambda_integration(
        self, resource: apigateway.Resource, method: str, function_name: str, authorizer: apigateway.CognitoUserPoolsAuthorizer
    ) -> None:
        """Add Lambda integration to API resource."""
        if function_name in self.lambda_arns:
            # Use fixed logical ID for imported Lambda functions
            logical_id = self._get_lambda_import_logical_id(function_name)
            lambda_function = lambda_.Function.from_function_arn(self, logical_id, self.lambda_arns[function_name])

            # Create integration
            integration = apigateway.LambdaIntegration(lambda_function)

            # Add method
            resource.add_method(
                method,
                integration,
                authorizer=authorizer,
                authorization_type=apigateway.AuthorizationType.COGNITO if authorizer else None,
            )

            # Grant API Gateway permission to invoke the Lambda
            lambda_function.grant_invoke(iam.ServicePrincipal("apigateway.amazonaws.com"))

    def _configure_gateway_responses(self, api: apigateway.RestApi, client_origin: str) -> None:
        """Configure CORS headers for gateway error responses."""
        # CORS headers to add to all error responses
        cors_headers = {
            "gatewayresponse.header.Access-Control-Allow-Origin": f"'{client_origin}'",
            "gatewayresponse.header.Access-Control-Allow-Headers": "'Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token'",
            "gatewayresponse.header.Access-Control-Allow-Methods": "'GET,POST,PUT,DELETE,OPTIONS'",
            "gatewayresponse.header.Access-Control-Allow-Credentials": "'true'"
        }

        # Add gateway responses with CORS headers for common error types
        # Note: DEFAULT4XX and DEFAULT5XX handle all 4xx and 5xx responses
        api.add_gateway_response(
            "GatewayResponseDefault4XX",
            type=apigateway.ResponseType.DEFAULT4XX, # type: ignore
            response_headers=cors_headers,
        )

        api.add_gateway_response(
            "GatewayResponseDefault5XX",
            type=apigateway.ResponseType.DEFAULT5XX, # type: ignore
            response_headers=cors_headers,
        )

        # Add specific error responses that might need special handling
        specific_errors = [
            (apigateway.ResponseType.UNAUTHORIZED, "Unauthorized"),
            (apigateway.ResponseType.ACCESS_DENIED, "AccessDenied"),
            (apigateway.ResponseType.EXPIRED_TOKEN, "ExpiredToken"),
            (apigateway.ResponseType.INVALID_API_KEY, "InvalidApiKey"),
            (apigateway.ResponseType.MISSING_AUTHENTICATION_TOKEN, "MissingAuthToken"),
        ]

        for response_type, name in specific_errors:
            api.add_gateway_response(
                f"GatewayResponse{name}",
                type=response_type,
                response_headers=cors_headers,
            )

    def _configure_api_domain(self, api: apigateway.RestApi) -> None:
        """Configure custom domain for API Gateway."""
        api_domain = f"{self.api_host}.{self.domain}"

        # Get hosted zone by ID
        hosted_zone = utils.get_hosted_zone_by_id(self, self.hosted_zone_id, self.domain)
        if not hosted_zone:
            raise ValueError(f"Could not find hosted zone {self.hosted_zone_id} for domain {self.domain}")

        # Create ACM certificate with fixed logical ID
        certificate = acm.Certificate(
            self,
            "ApiCertificate",  # Fixed logical ID - won't change between deployments
            domain_name=api_domain,
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )

        # Create custom domain
        custom_domain = apigateway.DomainName(
            self,
            "ApiDomain",
            domain_name=api_domain,
            certificate=certificate,
            endpoint_type=apigateway.EndpointType.REGIONAL,
            security_policy=apigateway.SecurityPolicy.TLS_1_2,
        )

        # Map API to custom domain
        apigateway.BasePathMapping(
            self,
            "ApiMapping",
            domain_name=custom_domain,
            rest_api=api,
            base_path="",
        )

        # Create Route53 record
        route53.ARecord(
            self,
            "ApiDnsRecord",
            zone=hosted_zone,
            record_name=self.api_host,
            target=route53.RecordTarget.from_alias(targets.ApiGatewayDomain(custom_domain)),  # type: ignore
        )

    def _get_lambda_import_logical_id(self, function_name: str) -> str:
        """Get fixed logical ID for imported Lambda function.

        This ensures consistent logical IDs across deployments.
        """
        # Define fixed mappings for all Lambda functions used by API
        logical_id_map = {
            "api-archetype-list": "ImportApiArchetypeList",
            "api-character-add": "ImportApiCharacterAdd",
            "api-character-delete": "ImportApiCharacterDelete",
            "api-character-get": "ImportApiCharacterGet",
            "api-character-list": "ImportApiCharacterList",
            "api-segment-decision": "ImportApiSegmentDecision",
            "api-segment-history": "ImportApiSegmentHistory",
            "api-segment-outcome": "ImportApiSegmentOutcome",
            "api-segment-rest": "ImportApiSegmentRest",
            "api-segment-status": "ImportApiSegmentStatus",
            "api-story-abandon": "ImportApiStoryAbandon",
            "api-story-start": "ImportApiStoryStart",
        }
        return logical_id_map.get(function_name, "Import" + function_name.replace("-", "").title())

    def _add_outputs(self) -> None:
        """Add stack outputs."""
        CfnOutput(self, "ApiUrl", value=f"https://{self.api_host}.{self.domain}", description="API custom domain URL")
        CfnOutput(self, "ApiId", value=self.api.rest_api_id, description="API Gateway ID")
        CfnOutput(self, "ApiGatewayUrl", value=self.api.url, description="API Gateway direct URL")
