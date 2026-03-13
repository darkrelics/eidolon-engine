"""CloudFront distribution operations."""

import ssl
import time
import urllib.error
import urllib.request


def wait_for_cloudfront_operational(domain: str, timeout_minutes: int = 35) -> bool:
    """Wait for CloudFront distribution to be operational.

    Args:
        domain: Domain name to check (e.g., portal.darkrelics.net)
        timeout_minutes: Maximum time to wait in minutes

    Returns:
        bool: True if distribution is operational, False if timeout
    """
    url = f"https://{domain}/"
    max_attempts = timeout_minutes * 6
    attempt = 0
    last_error = None
    last_error_type = None
    start_time = time.time()

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    print(f"    Verifying CloudFront operational: {domain}")
    print("    [NOTE] TLS verification disabled for reachability check (certificate may still be propagating)")
    print(f"    Timeout: {timeout_minutes} minutes, checking every 10 seconds")

    while attempt < max_attempts:
        elapsed = int(time.time() - start_time)
        elapsed_min = elapsed // 60
        elapsed_sec = elapsed % 60

        try:
            request = urllib.request.Request(url, method="HEAD")
            request.add_header("User-Agent", "EidolonDeployment/1.0")
            with urllib.request.urlopen(request, timeout=10, context=ssl_context) as response:
                status_code = response.getcode()
                if 200 <= status_code < 400:
                    print(f"    OK - CloudFront operational after {elapsed_min}m {elapsed_sec}s")
                    return True
        except urllib.error.HTTPError as err:
            if 400 <= err.code < 500:
                print(f"    OK - CloudFront operational after {elapsed_min}m {elapsed_sec}s (HTTP {err.code} - content pending)")
                return True
            last_error = f"HTTP {err.code}: {err.reason}"
            last_error_type = "http_5xx"
        except urllib.error.URLError as err:
            error_str = str(err.reason)
            last_error = f"Connection error: {error_str}"
            if "CERTIFICATE_VERIFY_FAILED" in error_str:
                last_error_type = "ssl_cert"
            elif "Name or service not known" in error_str or "getaddrinfo failed" in error_str:
                last_error_type = "dns"
            else:
                last_error_type = "connection"
        except TimeoutError:
            last_error = "Request timeout"
            last_error_type = "timeout"

        if attempt % 3 == 0:
            status_msg = {
                "ssl_cert": "SSL certificate not yet propagated to edge locations",
                "dns": "DNS not yet resolving",
                "connection": "Connection refused - distribution deploying",
                "http_5xx": "CloudFront returning 5xx - distribution deploying",
                "timeout": "Request timeout - distribution deploying",
            }.get(last_error_type, "Waiting for distribution")
            print(f"    [{elapsed_min:02d}:{elapsed_sec:02d}] {status_msg}")

        time.sleep(10)
        attempt += 1

    elapsed = int(time.time() - start_time)
    elapsed_min = elapsed // 60
    elapsed_sec = elapsed % 60
    print(f"    TIMEOUT after {elapsed_min}m {elapsed_sec}s - CloudFront not ready")
    print(f"    Last error: {last_error}")
    print("    This is normal for new distributions. You can:")
    print("      1. Re-run this script (it will skip completed steps)")
    print(f"      2. Wait and manually verify: curl -I https://{domain}/")
    return False
