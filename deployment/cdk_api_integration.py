"""CDK Python API integration for Eidolon Engine deployment.

This module provides a programmatic interface to AWS CDK operations,
replacing subprocess calls with direct Python API usage for better
error handling, progress monitoring, and integration.
"""

import os
import subprocess
import sys
from pathlib import Path

import boto3


class CDKDeploymentError(Exception):
    """Custom exception for CDK deployment failures."""

    def __init__(self, message: str, details: dict):
        """Initialize CDK deployment error.

        Args:
            message: Error message
            details: Additional error details
        """
        super().__init__(message)
        self.details = details


class CDKApiIntegration:
    """Handles CDK operations with enhanced error handling and progress monitoring."""

    def __init__(self, cdk_dir: str, profile: str = "", region: str = ""):
        """Initialize CDK API integration.

        Args:
            cdk_dir: Directory containing CDK app
            profile: AWS profile to use
            region: AWS region to deploy to
        """
        self.cdk_dir = Path(cdk_dir)
        self.profile = profile
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")

        # Set up environment
        self._setup_environment()

        # Initialize AWS clients
        session_args = {"region_name": self.region}
        if self.profile:
            session_args["profile_name"] = self.profile
        self.session = boto3.Session(**session_args)
        self.cfn_client = self.session.client("cloudformation")

        # Check CDK installation
        if not check_cdk_installed():
            raise CDKDeploymentError("AWS CDK CLI is not installed. Please install it with: npm install -g aws-cdk", {})

        # Check and ensure CDK bootstrap
        self._ensure_cdk_bootstrap()

    def _ensure_cdk_bootstrap(self) -> None:
        """Check if CDK is bootstrapped and bootstrap if necessary."""
        try:
            # Get account ID
            account_id = self.session.client("sts").get_caller_identity().get("Account")

            # Check if bootstrap SSM parameter exists
            ssm_client = self.session.client("ssm")
            try:
                ssm_client.get_parameter(Name="/cdk-bootstrap/hnb659fds/version")
                print("✓ CDK bootstrap detected")
                return
            except ssm_client.exceptions.ParameterNotFound:
                print("\n[CDK Bootstrap Required]")
                print(f"The AWS CDK needs to be bootstrapped in account {account_id} for region {self.region}")
                print("This is a one-time setup that creates resources needed by CDK.")

                # In non-interactive mode, raise an error
                if os.environ.get("NON_INTERACTIVE"):
                    raise CDKDeploymentError(
                        f"CDK bootstrap required. Run: cdk bootstrap aws://{account_id}/{self.region}",
                        {"account": account_id, "region": self.region},
                    )

                # Ask user if they want to bootstrap
                response = input("\nDo you want to bootstrap CDK now? [Y/n]: ").strip().lower()
                if response == "" or response == "y":
                    print(f"\nBootstrapping CDK for aws://{account_id}/{self.region}...")
                    self._run_cdk_bootstrap(account_id)
                else:
                    raise CDKDeploymentError(
                        f"CDK bootstrap required. Run manually: cdk bootstrap aws://{account_id}/{self.region}",
                        {"account": account_id, "region": self.region},
                    )
        except Exception as e:
            if isinstance(e, CDKDeploymentError):
                raise
            raise CDKDeploymentError(f"Error checking CDK bootstrap: {str(e)}", {})

    def _run_cdk_bootstrap(self, account_id: str) -> None:
        """Run CDK bootstrap command."""
        try:
            # Run bootstrap command
            result = subprocess.run(
                ["cdk", "bootstrap", f"aws://{account_id}/{self.region}"],
                cwd=self.cdk_dir,
                env=os.environ.copy(),
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                # Check if it's just the bucket already exists error
                if "already exists" in result.stderr and "cdk-hnb659fds-assets" in result.stderr:
                    print("⚠️  CDK assets bucket already exists, but bootstrap incomplete")
                    print("This usually means a previous bootstrap attempt failed.")
                    print("Please manually clean up and retry:")
                    print("  1. Delete CloudFormation stack: CDKToolkit")
                    print(f"  2. Run: cdk bootstrap aws://{account_id}/{self.region}")
                    raise CDKDeploymentError("CDK bootstrap failed - manual cleanup required", {})
                else:
                    raise CDKDeploymentError(f"CDK bootstrap failed: {result.stderr}", {})

            print("✓ CDK bootstrap completed successfully")

        except subprocess.CalledProcessError as e:
            raise CDKDeploymentError(f"CDK bootstrap command failed: {str(e)}", {})

    def _setup_environment(self) -> None:
        """Configure environment for CDK operations."""
        # Set AWS profile if specified
        if self.profile:
            os.environ["AWS_PROFILE"] = self.profile

        # Set region
        os.environ["AWS_REGION"] = self.region
        os.environ["CDK_DEFAULT_REGION"] = self.region

        # Set AWS account
        try:
            account = self.session.client("sts").get_caller_identity().get("Account", "")
            os.environ["CDK_DEFAULT_ACCOUNT"] = account
        except Exception:
            pass

        # Add CDK app directory to Python path
        if str(self.cdk_dir) not in sys.path:
            sys.path.insert(0, str(self.cdk_dir))

    def _run_cdk_command(self, args: list, env: dict, capture_output: bool = False) -> subprocess.CompletedProcess:
        """Run CDK command with proper error handling.

        Args:
            args: CDK command arguments
            env: Environment variables
            capture_output: Whether to capture output

        Returns:
            Completed process result
        """
        cmd = ["cdk"] + args
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        try:
            if capture_output:
                return subprocess.run(cmd, cwd=self.cdk_dir, env=full_env, capture_output=True, text=True, check=True)
            else:
                return subprocess.run(cmd, cwd=self.cdk_dir, env=full_env, check=True)
        except subprocess.CalledProcessError as err:
            if capture_output and err.stderr:
                raise CDKDeploymentError(f"CDK command failed: {err.stderr}", {})
            raise CDKDeploymentError(f"CDK command failed with exit code {err.returncode}", {})

    def list_stacks(self) -> list:
        """List all stacks in the CDK app.

        Returns:
            List of stack names
        """
        try:
            result = self._run_cdk_command(["list"], capture_output=True, env={})
            stacks = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
            return stacks
        except CDKDeploymentError:
            raise
        except Exception as err:
            raise CDKDeploymentError(f"Failed to list stacks: {err}", {})

    def synth(self, context: dict, output_dir: str = "") -> dict:
        """Synthesize CDK app to CloudFormation templates.

        Args:
            context: Additional context values
            output_dir: Directory to output templates (optional)

        Returns:
            Synthesis result with stack information
        """
        try:
            # Build command
            args = ["synth", "--all"]

            # Add context parameters
            if context:
                for key, value in context.items():
                    args.extend(["-c", f"{key}={value}"])

            # Add output directory
            if output_dir:
                args.extend(["--output", output_dir])

            # Run synthesis
            self._run_cdk_command(args, env={})

            return {"success": True, "message": "Synthesis completed successfully", "context": context or {}}

        except CDKDeploymentError:
            raise
        except Exception as err:
            raise CDKDeploymentError(f"Synthesis failed: {err}", {})

    def deploy(
        self,
        stacks: list,
        context: dict,
        require_approval: str,
        progress_callback: object,
    ) -> dict:
        """Deploy CDK stacks with enhanced progress monitoring.

        Args:
            stacks: List of stack names to deploy (None for all)
            context: Additional context values
            require_approval: Approval level (never, any-change, broadening)
            progress_callback: Callback for deployment progress

        Returns:
            Deployment result with stack outputs
        """
        try:
            # Build command
            args = ["deploy"]

            # Add stacks or --all
            if stacks:
                args.extend(stacks)
            else:
                args.append("--all")

            # Add approval requirement
            args.extend(["--require-approval", require_approval])

            # Add context parameters
            if context:
                for key, value in context.items():
                    args.extend(["-c", f"{key}={value}"])

            # Add progress reporting
            args.append("--progress=events")

            # Run deployment with real-time output
            print("Starting CDK deployment...")
            process = subprocess.Popen(
                ["cdk"] + args,
                cwd=self.cdk_dir,
                env=os.environ.copy(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            # Monitor output and call progress callback
            deployed_stacks = []
            stack_changes = {}  # Track if each stack had changes
            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    line = line.rstrip()
                    if line:
                        print(line)

                        # Parse progress events
                        if progress_callback and callable(progress_callback):
                            event = parse_progress_event(line)
                            if event:
                                progress_callback(event)

                        # Track deployed stacks
                        if "CREATE_COMPLETE" in line or "UPDATE_COMPLETE" in line:
                            parts = line.split()
                            for part in parts:
                                if part.startswith("eidolon-") or "-stack" in part:
                                    deployed_stacks.append(part)
                                    stack_changes[part] = True
                        else:
                            # Mark stacks without CREATE/UPDATE as having no changes
                            parts = line.split()
                            for part in parts:
                                if part == "lambda" or part == "base-lambda" or part == "cognito-trigger":
                                    if part not in deployed_stacks:
                                        deployed_stacks.append(part)
                                        stack_changes[part] = False

            # Wait for completion
            return_code = process.wait()

            if return_code == 0:
                # Get outputs from deployed stacks
                outputs = {}
                for stack_name in set(deployed_stacks):
                    try:
                        outputs[stack_name] = self.get_stack_outputs(stack_name)
                    except Exception:
                        pass

                return {
                    "success": True,
                    "message": "Deployment completed successfully",
                    "stacks_deployed": list(set(deployed_stacks)),
                    "stack_changes": stack_changes,
                    "outputs": outputs,
                }
            else:
                raise CDKDeploymentError(f"Deployment failed with exit code {return_code}", {})

        except subprocess.CalledProcessError as err:
            raise CDKDeploymentError(f"Deployment failed: {err}", {})
        except Exception as err:
            raise CDKDeploymentError(f"Unexpected error during deployment: {err}", {})

    def diff(self, stacks: list, context: dict) -> dict:
        """Show differences between deployed and local stacks.

        Args:
            stacks: List of stack names to diff (None for all)
            context: Additional context values

        Returns:
            Diff results for each stack
        """
        try:
            # Build command
            args = ["diff"]

            # Add stacks or --all
            if stacks:
                args.extend(stacks)
            else:
                args.append("--all")

            # Add context parameters
            if context:
                for key, value in context.items():
                    args.extend(["-c", f"{key}={value}"])

            # Run diff
            result = self._run_cdk_command(args, capture_output=True, env={})

            # Parse output to determine if there are changes
            has_changes = "There were no differences" not in result.stdout

            return {"success": True, "has_changes": has_changes, "output": result.stdout}

        except CDKDeploymentError:
            raise
        except Exception as err:
            raise CDKDeploymentError(f"Diff failed: {err}", {})

    def destroy(self, stacks: list, context: dict, force: bool = False) -> dict:
        """Destroy CDK stacks.

        Args:
            stacks: List of stack names to destroy (None for all)
            context: Additional context values
            force: Force destroy without confirmation

        Returns:
            Destruction result
        """
        try:
            # Build command
            args = ["destroy"]

            # Add stacks or --all
            if stacks:
                args.extend(stacks)
            else:
                args.append("--all")

            # Add force flag
            if force:
                args.append("--force")

            # Add context parameters
            if context:
                for key, value in context.items():
                    args.extend(["-c", f"{key}={value}"])

            # Run destroy
            self._run_cdk_command(args, env={})

            return {"success": True, "message": "Stacks destroyed successfully", "stacks_destroyed": stacks or ["all"]}

        except CDKDeploymentError:
            raise
        except Exception as err:
            raise CDKDeploymentError(f"Destroy failed: {err}", {})

    def get_stack_outputs(self, stack_name: str) -> dict:
        """Get outputs from a deployed stack.

        Args:
            stack_name: Name of the stack

        Returns:
            Dictionary of output key-value pairs
        """
        try:
            # Use CloudFormation client to get stack outputs
            import boto3

            session = boto3.Session(profile_name=self.profile if self.profile else None, region_name=self.region)
            cfn_client = session.client("cloudformation")

            response = cfn_client.describe_stacks(StackName=stack_name)
            stack = response.get("Stacks", [{}])[0]

            outputs = {}
            for output in stack.get("Outputs", []):
                outputs[output.get("OutputKey", "")] = output.get("OutputValue", "")

            return outputs

        except Exception as err:
            raise CDKDeploymentError(f"Failed to get stack outputs: {err}", {})

    def bootstrap(self, account: str = "", region: str = "") -> dict:
        """Bootstrap CDK environment.

        Args:
            account: AWS account ID (uses current if not specified)
            region: AWS region (uses configured if not specified)

        Returns:
            Bootstrap result
        """
        try:
            # Get account if not specified
            if not account:
                account = self.session.client("sts").get_caller_identity().get("Account", "")

            # Prepare bootstrap parameters
            bootstrap_region = region or self.region

            # Build command
            args = ["bootstrap", f"aws://{account}/{bootstrap_region}"]

            # Run bootstrap
            self._run_cdk_command(args, env={})

            return {"success": True, "message": f"Bootstrap completed for {bootstrap_region}"}

        except CDKDeploymentError:
            raise
        except Exception as err:
            raise CDKDeploymentError(f"Bootstrap failed: {err}", {})


def check_cdk_installed() -> bool:
    """Check if CDK CLI is installed.

    Returns:
        True if CDK is installed
    """
    try:
        result = subprocess.run(["cdk", "--version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def parse_progress_event(line: str) -> dict:
    """Parse CDK deployment progress line into event.

    Args:
        line: Output line from CDK

    Returns:
        Parsed event or empty dict
    """
    # Parse CloudFormation events
    if " | " in line and ("CREATE_" in line or "UPDATE_" in line or "DELETE_" in line):
        parts = line.split(" | ")
        if len(parts) >= 4:
            return {
                "type": "resource",
                "stackName": parts[0].strip(),
                "logicalId": parts[2].strip(),
                "status": parts[3].strip(),
                "reason": parts[4].strip() if len(parts) > 4 else "",
            }

    # Parse stack events
    if "Stack " in line and ("CREATE_COMPLETE" in line or "UPDATE_COMPLETE" in line):
        return {"type": "stack", "status": "complete", "message": line}

    return {}


class CDKProgressReporter:
    """Reports CDK deployment progress to console."""

    def __init__(self):
        """Initialize progress reporter."""
        self.current_stack = None
        self.events_seen = set()

    def __call__(self, event: dict) -> None:
        """Handle progress event.

        Args:
            event: CDK progress event
        """
        # Extract event information
        stack_name = event.get("stackName", "")
        logical_id = event.get("logicalId", "")
        status = event.get("status", "")
        reason = event.get("reason", "")

        # Track current stack
        if stack_name and stack_name != self.current_stack:
            self.current_stack = stack_name
            print(f"\n[STACK] Deploying {stack_name}...")

        # Report resource events
        if logical_id and status:
            event_id = f"{stack_name}-{logical_id}-{status}"
            if event_id not in self.events_seen:
                self.events_seen.add(event_id)

                # Format status
                if "COMPLETE" in status:
                    status_icon = "✓"
                elif "FAILED" in status:
                    status_icon = "✗"
                elif "IN_PROGRESS" in status:
                    status_icon = "⟳"
                else:
                    status_icon = "•"

                # Print progress
                message = f"  {status_icon} {logical_id}: {status}"
                if reason and "FAILED" in status:
                    message += f" - {reason}"

                print(message)
