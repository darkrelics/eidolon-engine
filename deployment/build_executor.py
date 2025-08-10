"""CodeBuild execution and monitoring functionality."""

import time

import boto3
from botocore.exceptions import ClientError


class BuildExecutor:
    """Manages CodeBuild project execution and monitoring."""

    def __init__(self, session: boto3.Session) -> None:
        """Initialize build executor with AWS session.

        Args:
            session: Boto3 session to use for AWS API calls
        """
        self.session = session
        self.codebuild_client = session.client("codebuild")

    def start_build(self, project_name: str) -> str | None:
        """Start a CodeBuild project build.

        Args:
            project_name: Name of the CodeBuild project

        Returns:
            Build ID if successful, None if failed
        """
        try:
            print(f"\nStarting build for project: {project_name}")
            response = self.codebuild_client.start_build(projectName=project_name)
            build_id = response["build"]["id"]
            print(f"Build started successfully: {build_id}")
            return build_id
        except ClientError as err:
            print(f"Failed to start build for {project_name}: {err}")
            return None

    def get_build_status(self, build_id: str) -> dict:
        """Get current status of a build.

        Args:
            build_id: Build ID to check

        Returns:
            Dictionary with status and phase information
        """
        try:
            response = self.codebuild_client.batch_get_builds(ids=[build_id])
            if response["builds"]:
                build = response["builds"][0]
                return {
                    "status": build.get("buildStatus", "UNKNOWN"),
                    "phase": build.get("currentPhase", "UNKNOWN"),
                    "phase_status": build.get("phases", [{}])[-1].get("phaseStatus", "") if build.get("phases") else "",
                }
            return {"status": "NOT_FOUND", "phase": "", "phase_status": ""}
        except ClientError as err:
            print(f"Error getting build status: {err}")
            return {"status": "ERROR", "phase": "", "phase_status": ""}

    def wait_for_build(self, build_id: str, timeout_minutes: int = 30) -> bool:
        """Wait for a build to complete.

        Args:
            build_id: Build ID to monitor
            timeout_minutes: Maximum time to wait for build completion

        Returns:
            True if build succeeded, False otherwise
        """
        start_time: float = time.time()
        timeout_seconds = timeout_minutes * 60
        last_phase = ""

        print(f"\nMonitoring build: {build_id}")
        print(f"Timeout: {timeout_minutes} minutes")

        while True:
            status_info: dict = self.get_build_status(build_id)
            status = status_info["status"]
            phase = status_info["phase"]

            # Print phase changes
            if phase != last_phase:
                print(f"  Phase: {phase}")
                last_phase = phase

            # Check terminal states
            if status == "SUCCEEDED":
                print("Build completed successfully!")
                return True
            elif status in ["FAILED", "FAULT", "TIMED_OUT", "STOPPED"]:
                print(f"Build failed with status: {status}")
                self._print_build_logs(build_id)
                return False

            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                print(f"Build timed out after {timeout_minutes} minutes")
                return False

            # Wait before next check
            time.sleep(10)

    def _print_build_logs(self, build_id: str, tail_lines: int = 50) -> None:
        """Print the last N lines of build logs for debugging.

        Args:
            build_id: Build ID to get logs for
            tail_lines: Number of lines to print from the end
        """
        try:
            print(f"\nLast {tail_lines} lines of build logs:")
            print("-" * 60)

            # Get build details to find log info
            response = self.codebuild_client.batch_get_builds(ids=[build_id])
            if not response["builds"]:
                print("Could not retrieve build information")
                return

            build = response["builds"][0]
            log_info = build.get("logs", {})

            if not log_info.get("streamName"):
                print("No log stream available")
                return

            # Get logs from CloudWatch
            logs_client = self.session.client("logs")
            group_name = log_info.get("groupName", "/aws/codebuild/project-logs")
            stream_name = log_info["streamName"]

            try:
                response = logs_client.get_log_events(
                    logGroupName=group_name, logStreamName=stream_name, limit=tail_lines, startFromHead=False
                )

                events = response.get("events", [])
                for event in events[-tail_lines:]:
                    print(event["message"].rstrip())

            except ClientError as err:
                print(f"Could not retrieve logs: {err}")

            print("-" * 60)

        except Exception as err:
            print(f"Error printing build logs: {err}")

    def execute_builds(self, project_names: list, parallel: bool = True, timeout_minutes: int = 30) -> bool:
        """Execute multiple CodeBuild projects.

        Args:
            project_names: List of CodeBuild project names to execute
            parallel: Whether to run builds in parallel or sequentially
            timeout_minutes: Timeout for each build

        Returns:
            True if all builds succeeded, False otherwise
        """
        if not project_names:
            print("No build projects to execute")
            return True

        print(f"\n{'='*60}")
        print(f"Executing {len(project_names)} build(s)")
        print(f"Mode: {'Parallel' if parallel else 'Sequential'}")
        print(f"{'='*60}")

        if parallel:
            return self._execute_parallel_builds(project_names, timeout_minutes)
        else:
            return self._execute_sequential_builds(project_names, timeout_minutes)

    def _execute_parallel_builds(self, project_names: list[str], timeout_minutes: int) -> bool:
        """Execute builds in parallel.

        Args:
            project_names: List of project names
            timeout_minutes: Timeout for builds

        Returns:
            True if all builds succeeded
        """
        # Start all builds
        builds: dict = {}
        for project_name in project_names:
            build_id = self.start_build(project_name)
            if build_id:
                builds[project_name] = build_id
            else:
                print(f"[ERROR] Failed to start build for {project_name}, aborting")
                return False

        # Monitor all builds
        start_time: float = time.time()
        timeout_seconds: int = timeout_minutes * 60
        completed: set = set()
        failed: set = set()

        print(f"\nMonitoring {len(builds)} parallel builds...")

        while len(completed) + len(failed) < len(builds):
            for project_name, build_id in builds.items():
                if project_name in completed or project_name in failed:
                    continue

                status_info: dict = self.get_build_status(build_id)
                status = status_info["status"]

                if status == "SUCCEEDED":
                    print(f"{project_name}: Build completed successfully")
                    completed.add(project_name)
                elif status in ["FAILED", "FAULT", "TIMED_OUT", "STOPPED"]:
                    print(f"{project_name}: Build failed with status: {status}")
                    self._print_build_logs(build_id)
                    failed.add(project_name)

            # Check overall timeout
            if time.time() - start_time > timeout_seconds:
                print(f"\nBuild execution timed out after {timeout_minutes} minutes")
                return False

            if len(completed) + len(failed) < len(builds):
                time.sleep(10)

        # Summary
        print(f"\n{'='*60}")
        print("Build Summary:")
        print(f"  Succeeded: {len(completed)}")
        print(f"  Failed: {len(failed)}")
        print(f"{'='*60}")

        return len(failed) == 0

    def _execute_sequential_builds(self, project_names: list, timeout_minutes: int) -> bool:
        """Execute builds sequentially.

        Args:
            project_names: List of project names
            timeout_minutes: Timeout for each build

        Returns:
            True if all builds succeeded
        """
        for i, project_name in enumerate(project_names, 1):
            print(f"\nBuild {i}/{len(project_names)}: {project_name}")

            build_id = self.start_build(project_name)
            if not build_id:
                return False

            if not self.wait_for_build(build_id, timeout_minutes):
                print("Build failed, aborting remaining builds")
                return False

        print(f"\nAll {len(project_names)} builds completed successfully")
        return True
