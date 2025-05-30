#!/usr/bin/env python3
"""
Deploy Lua scripts to S3

This script uploads Lua scripts from the scripts_lua directory to S3
for use by the Eidolon Engine server instances.
"""

import os
import sys

import boto3
from botocore.exceptions import ClientError


def get_s3_client():
    """Create and return an S3 client."""
    return boto3.client("s3")


def validate_s3_bucket(s3_client, bucket_name):
    """Check if S3 bucket exists and is accessible."""
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        return True
    except ClientError:
        return False


def upload_script(s3_client, bucket_name, local_path, s3_key):
    """Upload a single script file to S3."""
    try:
        with open(local_path, "rb") as file_data:
            s3_client.put_object(Bucket=bucket_name, Key=s3_key, Body=file_data, ContentType="text/x-lua")
        print(f"✓ Uploaded: {os.path.basename(local_path)} -> s3://{bucket_name}/{s3_key}")
        return True
    except ClientError as e:
        print(f"✗ Failed to upload {os.path.basename(local_path)}: {e}")
        return False


def deploy_scripts(bucket_name, prefix):
    """Deploy all Lua scripts to S3."""
    # Find scripts_lua directory using relative path
    script_dir = os.path.join(os.path.dirname(__file__), "..", "scripts_lua")
    script_dir = os.path.abspath(script_dir)

    if not os.path.exists(script_dir):
        print(f"Error: Scripts directory not found: {script_dir}")
        return False

    # Get S3 client
    s3_client = get_s3_client()

    # Validate bucket
    if not validate_s3_bucket(s3_client, bucket_name):
        print(f"Error: S3 bucket '{bucket_name}' does not exist or is not accessible")
        return False

    # Find all .lua files
    lua_files = []
    for root, dirs, files in os.walk(script_dir):
        for file in files:
            if file.endswith(".lua"):
                lua_files.append(os.path.join(root, file))

    if not lua_files:
        print(f"No .lua files found in {script_dir}")
        return True

    print(f"\nFound {len(lua_files)} Lua scripts to deploy:")
    for file in lua_files:
        print(f"  - {os.path.basename(file)}")

    # Upload each script
    print(f"\nUploading to s3://{bucket_name}/{prefix}/")
    success_count = 0
    for lua_file in lua_files:
        filename = os.path.basename(lua_file)
        s3_key = f"{prefix}/{filename}"

        if upload_script(s3_client, bucket_name, lua_file, s3_key):
            success_count += 1

    print(f"\nDeployment complete: {success_count}/{len(lua_files)} scripts uploaded")
    return success_count == len(lua_files)


def list_deployed_scripts(bucket_name, prefix):
    """List all deployed scripts in S3."""
    s3_client = get_s3_client()

    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

        scripts = []
        if "Contents" in response:
            for obj in response["Contents"]:
                if obj["Key"].endswith(".lua"):
                    scripts.append({"key": obj["Key"], "size": obj["Size"], "modified": obj["LastModified"]})

        if scripts:
            print(f"\nDeployed scripts in s3://{bucket_name}/{prefix}:")
            for script in sorted(scripts, key=lambda x: x["key"]):
                print(f"  {script['key']} ({script['size']} bytes)")
        else:
            print(f"\nNo scripts found in s3://{bucket_name}/{prefix}")

        return True
    except ClientError as e:
        print(f"Error listing scripts: {e}")
        return False


def delete_script(bucket_name, script_name, prefix):
    """Delete a specific script from S3."""
    s3_client = get_s3_client()
    s3_key = f"{prefix}/{script_name}"

    try:
        s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
        print(f"✓ Deleted: s3://{bucket_name}/{s3_key}")
        return True
    except ClientError as e:
        print(f"✗ Failed to delete {s3_key}: {e}")
        return False


def main():
    """Main entry point."""
    print("Eidolon Engine Lua Script Deployment")
    print("====================================\n")

    # Get bucket name
    bucket_name = input("Enter S3 bucket name for scripts: ").strip()
    if not bucket_name:
        print("Error: Bucket name is required")
        sys.exit(1)

    # Get prefix
    prefix = input("Enter S3 prefix [default: scripts]: ").strip()
    if not prefix:
        prefix = "scripts"

    # Get action
    print("\nWhat would you like to do?")
    print("1. Deploy scripts")
    print("2. List deployed scripts")
    print("3. Delete a script")

    choice = input("\nEnter choice (1-3) [default: 1]: ").strip()
    if not choice:
        choice = "1"

    # Execute action
    if choice == "1":
        success = deploy_scripts(bucket_name, prefix)
    elif choice == "2":
        success = list_deployed_scripts(bucket_name, prefix)
    elif choice == "3":
        script_name = input("Enter script name to delete (e.g., room_tavern.lua): ").strip()
        if not script_name:
            print("Error: Script name is required")
            sys.exit(1)
        success = delete_script(bucket_name, script_name, prefix)
    else:
        print(f"Invalid choice: {choice}")
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
