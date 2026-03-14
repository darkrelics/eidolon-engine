"""Deployment progress tracking."""


class DeploymentTracker:
    """Track deployment progress for failure summary."""

    def __init__(self):
        self.completed_steps = []
        self.current_step = None

    def start_step(self, step_num: int, description: str):
        """Mark a step as started."""
        self.current_step = (step_num, description)

    def complete_step(self):
        """Mark current step as completed."""
        if self.current_step:
            self.completed_steps.append(self.current_step)
            self.current_step = None

    def print_summary(self, success: bool = False):
        """Print deployment summary.

        Args:
            success: True if deployment completed successfully
        """
        if success:
            print("\n=== Deployment Summary ===")
        else:
            print("\n=== Deployment Failed ===")

        if self.completed_steps:
            print("Completed steps:")
            for step_num, description in self.completed_steps:
                print(f"  Step {step_num}: {description}")
        if self.current_step:
            step_num, description = self.current_step
            print(f"Failed during: Step {step_num}: {description}")
        if not self.completed_steps and not self.current_step:
            print("  No steps completed")
