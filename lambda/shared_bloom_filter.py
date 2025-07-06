"""
Shared Bloom Filter Management for Character Names

This Lambda manages a bloom filter shared between the Incremental game
and MUD server for character name validation using S3 storage.
"""

import base64
import json
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from eidolon.logger import get_logger

logger = get_logger(__name__)

# Environment variables
BLOOM_BUCKET = os.environ.get("BLOOM_BUCKET", "eidolon-shared-data")
BLOOM_KEY = os.environ.get("BLOOM_KEY", "bloom-filters/character-names/current.bloom")
METADATA_KEY = os.environ.get("METADATA_KEY", "bloom-filters/character-names/metadata.json")
CACHE_TTL = 300  # 5 minutes

# Initialize clients
s3 = boto3.client("s3")

# In-memory cache
_filter_cache = {
    "filter": None,
    "version": 0,
    "expires_at": datetime.min
}


class BloomFilter:
    """Simple bloom filter implementation for character names."""
    
    def __init__(self, size: int = 1000000, hash_functions: int = 7):
        self.size = size
        self.hash_functions = hash_functions
        self.bit_array = bytearray(size // 8 + 1)
        
    def _hash(self, item: str, seed: int) -> int:
        """Generate hash for string with seed."""
        hash_val = seed
        for char in item.lower():
            hash_val = ((hash_val * 31) + ord(char)) % self.size
        return hash_val
    
    def add(self, item: str) -> None:
        """Add item to bloom filter."""
        for i in range(self.hash_functions):
            pos = self._hash(item, i)
            byte_idx = pos // 8
            bit_idx = pos % 8
            self.bit_array[byte_idx] |= (1 << bit_idx)
    
    def contains(self, item: str) -> bool:
        """Check if item might be in the filter."""
        for i in range(self.hash_functions):
            pos = self._hash(item, i)
            byte_idx = pos // 8
            bit_idx = pos % 8
            if not (self.bit_array[byte_idx] & (1 << bit_idx)):
                return False
        return True
    
    def to_base64(self) -> str:
        """Serialize filter to base64."""
        return base64.b64encode(self.bit_array).decode('utf-8')
    
    @classmethod
    def from_base64(cls, data: str, size: int, hash_functions: int) -> 'BloomFilter':
        """Deserialize filter from base64."""
        filter_obj = cls(size, hash_functions)
        filter_obj.bit_array = bytearray(base64.b64decode(data))
        return filter_obj


def get_bloom_filter():
    """
    Get bloom filter from cache or S3.
    
    Returns:
        Tuple of (BloomFilter or None, metadata dict)
    """
    now = datetime.now(timezone.utc)
    
    # Check cache
    if _filter_cache["filter"] and _filter_cache["expires_at"] > now:
        return _filter_cache["filter"], _filter_cache.get("metadata", {})
    
    try:
        # Load metadata from S3
        metadata_response = s3.get_object(Bucket=BLOOM_BUCKET, Key=METADATA_KEY)
        metadata = json.loads(metadata_response["Body"].read())
        
        # Load bloom filter data from S3
        filter_response = s3.get_object(Bucket=BLOOM_BUCKET, Key=BLOOM_KEY)
        filter_data = filter_response["Body"].read()
        
        # Decode bloom filter
        bloom_filter = BloomFilter.from_base64(
            base64.b64encode(filter_data).decode('utf-8'),
            metadata["size"],
            metadata["hash_functions"]
        )
        
        # Update cache
        _filter_cache["filter"] = bloom_filter
        _filter_cache["version"] = metadata.get("version", 0)
        _filter_cache["metadata"] = metadata
        _filter_cache["expires_at"] = now.replace(second=now.second + CACHE_TTL)
        
        return bloom_filter, metadata
        
    except ClientError as err:
        if err.response['Error']['Code'] == 'NoSuchKey':
            logger.warning("Bloom filter not found in S3")
            return None, {}
        logger.error("Error loading bloom filter from S3", error=err)
        return None, {}


def check_character_name(name):
    """
    Check if character name is available.
    
    Args:
        name: Character name to check
        
    Returns:
        Dict with 'available' bool and 'reason' if not available
    """
    # Basic validation
    if len(name) < 4:
        return {"available": False, "reason": "Name too short (min 4 characters)"}
    
    if len(name) > 20:
        return {"available": False, "reason": "Name too long (max 20 characters)"}
    
    # Get bloom filter
    bloom_filter, metadata = get_bloom_filter()
    
    if not bloom_filter:
        # If filter unavailable, allow name (fail open)
        logger.warning("Bloom filter unavailable, allowing name", name=name)
        return {"available": True, "version": 0}
    
    # Check bloom filter
    if bloom_filter.contains(name):
        return {
            "available": False,
            "reason": "Name is already taken or reserved",
            "version": metadata.get("version", 0)
        }
    
    return {"available": True, "version": metadata.get("version", 0)}


def add_character_name(name):
    """
    Add character name to bloom filter.
    
    Args:
        name: Character name to add
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get current filter
        bloom_filter, metadata = get_bloom_filter()
        
        if not bloom_filter:
            # Create new filter if none exists
            bloom_filter = BloomFilter()
            metadata = {
                "version": 0,
                "size": bloom_filter.size,
                "hash_functions": bloom_filter.hash_functions,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        
        # Add name to filter
        bloom_filter.add(name.lower())
        
        # Update metadata
        new_version = metadata.get("version", 0) + 1
        new_metadata = {
            "version": new_version,
            "size": bloom_filter.size,
            "hash_functions": bloom_filter.hash_functions,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "last_added_name": name,
            "name_count": metadata.get("name_count", 0) + 1
        }
        
        # Save to S3
        # First save the bloom filter data
        filter_data = base64.b64decode(bloom_filter.to_base64())
        s3.put_object(
            Bucket=BLOOM_BUCKET,
            Key=BLOOM_KEY,
            Body=filter_data,
            ContentType="application/octet-stream",
            Metadata={"version": str(new_version)}
        )
        
        # Then save the metadata
        s3.put_object(
            Bucket=BLOOM_BUCKET,
            Key=METADATA_KEY,
            Body=json.dumps(new_metadata, indent=2),
            ContentType="application/json"
        )
        
        # Invalidate cache
        _filter_cache["filter"] = None
        _filter_cache["expires_at"] = datetime.min
        
        logger.info("Added name to bloom filter", name=name, version=new_version)
        return True
        
    except ClientError as err:
        logger.error("Error adding name to bloom filter", name=name, error=err)
        return False


def lambda_handler(event, context):
    """
    Lambda handler for bloom filter operations.
    
    Supports:
    - GET /bloom/check?name=CharacterName
    - POST /bloom/add {"name": "CharacterName"}
    """
    logger.log_lambda_event(event, context)
    
    method = event.get("httpMethod", "")
    path = event.get("path", "")
    
    if method == "GET" and path == "/bloom/check":
        # Check character name
        params = event.get("queryStringParameters", {})
        name = params.get("name", "").strip()
        
        if not name:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Name parameter required"})
            }
        
        result = check_character_name(name)
        
        return {
            "statusCode": 200,
            "body": json.dumps(result)
        }
    
    elif method == "POST" and path == "/bloom/add":
        # Add character name
        try:
            body = json.loads(event.get("body", "{}"))
        except json.JSONDecodeError:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Invalid JSON"})
            }
        
        name = body.get("name", "").strip()
        
        if not name:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Name field required"})
            }
        
        success = add_character_name(name)
        
        return {
            "statusCode": 200 if success else 500,
            "body": json.dumps({"success": success})
        }
    
    else:
        return {
            "statusCode": 404,
            "body": json.dumps({"error": "Not found"})
        }