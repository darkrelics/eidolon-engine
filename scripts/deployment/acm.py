"""ACM certificate operations."""

import time

import boto3
from botocore.exceptions import ClientError


def certificate_exists(domain_name: str, region: str) -> bool:
    """Check if ACM certificate exists for domain.

    Args:
        domain_name: Domain name to check
        region: AWS region

    Returns:
        bool: True if certificate exists and is issued
    """
    acm_client = boto3.client("acm", region_name=region)
    try:
        paginator = acm_client.get_paginator("list_certificates")
        for page in paginator.paginate(CertificateStatuses=["ISSUED"]):
            for cert in page.get("CertificateSummaryList", []):
                if cert.get("DomainName") == domain_name:
                    return True
        return False
    except ClientError as err:
        print(f"Error checking certificate: {err}")
        return False


def wait_for_certificate_validation(cert_arn: str, region: str, timeout_minutes: int = 30) -> bool:
    """Wait for ACM certificate to be validated and issued.

    Args:
        cert_arn: ACM certificate ARN
        region: AWS region
        timeout_minutes: Maximum time to wait in minutes

    Returns:
        bool: True if certificate is issued, False if timeout or error
    """
    acm_client = boto3.client("acm", region_name=region)
    max_attempts = timeout_minutes * 6
    attempt = 0

    while attempt < max_attempts:
        try:
            response = acm_client.describe_certificate(CertificateArn=cert_arn)
            certificate = response.get("Certificate", {})
            status = certificate.get("Status", "")
            domain_name = certificate.get("DomainName", "")

            if status == "ISSUED":
                return True
            elif status == "FAILED":
                print(f"    Certificate validation failed for {domain_name}")
                return False
            elif status == "PENDING_VALIDATION":
                if attempt == 0:
                    print(f"    Waiting for DNS validation: {domain_name}", end="", flush=True)
                else:
                    print(".", end="", flush=True)
            else:
                print(f"    Certificate status: {status}")

        except ClientError as err:
            print(f"    Error checking certificate: {err}")
            return False

        time.sleep(10)
        attempt += 1

    print()
    print("    Timeout waiting for certificate validation")
    return False
