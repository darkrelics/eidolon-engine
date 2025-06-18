"""
Eidolon Engine Lua Script Deployment

Copyright 2024-2025 Jason Robinson

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Deploy Lua scripts to S3 for use by Eidolon Engine server instances.
"""

import os
import sys

import boto3
import yaml
from botocore.exceptions import ClientError

# Configuration file paths
CONFIG_PATH = "../server/config.yml"
CONFIG_TEMPLATE_PATH = "../server/config.template.yml"
SCRIPTS_PATH = "../scripts_lua"


def load_config() -> dict:
    """Load configuration from config.yml or template."""
    if not os.path.exists(CONFIG_PATH):
        if not os.path.exists(CONFIG_TEMPLATE_PATH):
            raise FileNotFoundError(f"Neither {CONFIG_PATH} nor {CONFIG_TEMPLATE_PATH} exist")
        with open(CONFIG_TEMPLATE_PATH, "r", encoding="utf-8") as template_file:
            config = yaml.safe_load(template_file)
    else:
        with open(CONFIG_PATH, "r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file)
    return config


def validate_s3_bucket(bucket_name, region="us-east-1") -> bool:
    """Check if S3 bucket exists and is accessible."""
    s3_client = boto3.client("s3", region_name=region)
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        print(f"S3 bucket '{bucket_name}' exists and is accessible")
        return True
    except ClientError as err:
        print(f"Error accessing S3 bucket '{bucket_name}': {err}")
        return False


def deploy_scripts(bucket_name, prefix="scripts") -> bool:
    """
    Deploy Lua scripts to S3.
    """
    try:
        s3_client = boto3.client("s3")

        # Check if scripts directory exists
        if not os.path.exists(SCRIPTS_PATH):
            print(f"Scripts directory not found: {SCRIPTS_PATH}")
            return False

        # Find all .lua files
        lua_files = []
        for filename in os.listdir(SCRIPTS_PATH):
            if filename.endswith(".lua"):
                lua_files.append(filename)

        if not lua_files:
            print(f"No .lua files found in {SCRIPTS_PATH}")
            return True

        print(f"Found {len(lua_files)} Lua scripts to deploy")

        # Upload each script
        success_count = 0
        for filename in lua_files:
            local_path = os.path.join(SCRIPTS_PATH, filename)
            s3_key = f"{prefix}/{filename}"

            try:
                with open(local_path, "rb") as file_data:
                    s3_client.put_object(Bucket=bucket_name, Key=s3_key, Body=file_data, ContentType="text/x-lua")
                print(f"✓ Uploaded: {filename} -> s3://{bucket_name}/{s3_key}")
                success_count += 1
            except ClientError as err:
                print(f"✗ Failed to upload {filename}: {err}")

        print(f"Script deployment complete: {success_count}/{len(lua_files)} scripts uploaded")
        return success_count == len(lua_files)

    except Exception as err:
        print(f"Error deploying scripts: {err}")
        return False


def list_deployed_scripts(bucket_name, prefix="scripts"):
    """List all deployed scripts in S3."""
    s3_client = boto3.client("s3")

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
    except ClientError as err:
        print(f"Error listing scripts: {err}")
        return False


def delete_script(bucket_name, script_name, prefix="scripts"):
    """Delete a specific script from S3."""
    s3_client = boto3.client("s3")
    s3_key = f"{prefix}/{script_name}"

    try:
        s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
        print(f"Deleted: s3://{bucket_name}/{s3_key}")
        return True
    except ClientError as err:
        print(f"Failed to delete {s3_key}: {err}")
        return False


def main():
    """Main entry point."""
    print("Eidolon Engine Lua Script Deployment")
    print("====================================\n")

    # Load configuration
    try:
        config = load_config()

        # Try to get defaults from config
        default_bucket = config.get("Game", {}).get("ScriptsS3Bucket", "mud-scripts")
        default_prefix = config.get("Game", {}).get("ScriptsS3Prefix", "scripts")
    except Exception:
        default_bucket = "mud-scripts"
        default_prefix = "scripts"

    # Get action
    print("What would you like to do?")
    print("1. Deploy scripts")
    print("2. List deployed scripts")
    print("3. Delete a script")

    choice = input("\nEnter choice (1-3) [default: 1]: ").strip()
    if not choice:
        choice = "1"

    # Get bucket name
    bucket_prompt = f"Enter S3 bucket name for scripts [default: {default_bucket}]: "

    bucket_name = input(bucket_prompt).strip()
    if not bucket_name:
        if default_bucket:
            bucket_name = default_bucket
        else:
            print("Error: Bucket name is required")
            sys.exit(1)

    # Get prefix
    prefix = input(f"Enter S3 prefix [default: {default_prefix}]: ").strip()
    if not prefix:
        prefix = default_prefix

    # Validate bucket exists
    if not validate_s3_bucket(bucket_name):
        print(f"Invalid or inaccessible S3 bucket: {bucket_name}. Exiting...")
        sys.exit(1)

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
