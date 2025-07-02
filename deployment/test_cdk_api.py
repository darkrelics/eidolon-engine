#!/usr/bin/env python3
"""Test script for CDK API integration.

This script tests the new CDK Python API integration
to ensure it works correctly.
"""

import sys
from pathlib import Path

# Add deployment directory to path
sys.path.insert(0, str(Path(__file__).parent))

from cdk_api_integration import CDKApiIntegration, CDKDeploymentError


def test_cdk_api():
    """Test CDK API integration."""
    print("Testing CDK API Integration...")
    
    try:
        # Initialize CDK API
        cdk_api = CDKApiIntegration(
            cdk_dir=str(Path(__file__).parent / "cdk"),
            region="us-east-1"
        )
        print("✓ CDK API initialized successfully")
        
        # Test listing stacks
        print("\nListing CDK stacks...")
        stacks = cdk_api.list_stacks()
        print(f"✓ Found {len(stacks)} stacks:")
        for stack in stacks:
            print(f"  - {stack}")
        
        # Test synthesis
        print("\nTesting CDK synthesis...")
        result = cdk_api.synth(
            context={
                "deploy_mud": "true",
                "deploy_incremental": "false"
            }
        )
        if result["success"]:
            print("✓ Synthesis completed successfully")
        else:
            print("✗ Synthesis failed")
        
        # Test diff (non-destructive)
        print("\nTesting CDK diff...")
        diff_result = cdk_api.diff(
            context={
                "deploy_mud": "true",
                "deploy_incremental": "false"
            }
        )
        if diff_result["success"]:
            print(f"✓ Diff completed successfully")
            if diff_result["has_changes"]:
                print("  Changes detected between local and deployed stacks")
            else:
                print("  No changes detected")
        else:
            print("✗ Diff failed")
        
        print("\n✓ All tests passed!")
        
    except CDKDeploymentError as err:
        print(f"\n✗ CDK deployment error: {err}")
        if hasattr(err, 'details') and err.details:
            print(f"  Details: {err.details}")
        return 1
    except Exception as err:
        print(f"\n✗ Unexpected error: {err}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(test_cdk_api())