"""Route53 DNS operations."""

import boto3
from botocore.exceptions import ClientError


def route53_zone_exists(zone_id: str) -> bool:
    """Check if Route53 hosted zone exists.

    Args:
        zone_id: Route53 hosted zone ID

    Returns:
        bool: True if zone exists
    """
    route53 = boto3.client("route53")
    try:
        route53.get_hosted_zone(Id=zone_id)
        return True
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code in ["NoSuchHostedZone", "HostedZoneNotFound"]:
            return False
        raise err from err


def create_cname_record(route53_client, zone_id: str, record_name: str, record_value: str, ttl: int = 300) -> bool:
    """Create or update a CNAME record in Route53.

    Args:
        route53_client: boto3 Route53 client
        zone_id: Route53 hosted zone ID
        record_name: DNS record name
        record_value: CNAME target value
        ttl: Time to live in seconds

    Returns:
        bool: True if record created successfully
    """
    try:
        route53_client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                "Changes": [
                    {
                        "Action": "UPSERT",
                        "ResourceRecordSet": {
                            "Name": record_name,
                            "Type": "CNAME",
                            "TTL": ttl,
                            "ResourceRecords": [{"Value": record_value}],
                        },
                    }
                ]
            },
        )
        return True
    except ClientError as err:
        print(f"    Warning: Failed to create CNAME {record_name}: {err}")
        return False


def create_validation_record(route53_client, zone_id: str, record_name: str, record_value: str, record_type: str = "CNAME") -> bool:
    """Create a DNS validation record in Route53.

    Args:
        route53_client: boto3 Route53 client
        zone_id: Route53 hosted zone ID
        record_name: DNS record name
        record_value: Record value
        record_type: DNS record type (default: CNAME)

    Returns:
        bool: True if record created successfully
    """
    try:
        route53_client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                "Changes": [
                    {
                        "Action": "UPSERT",
                        "ResourceRecordSet": {
                            "Name": record_name,
                            "Type": record_type,
                            "TTL": 300,
                            "ResourceRecords": [{"Value": record_value}],
                        },
                    }
                ]
            },
        )
        print(f"    Created: {record_name}")
        return True
    except ClientError as err:
        print(f"    Warning: Failed to create {record_name}: {err}")
        return False
