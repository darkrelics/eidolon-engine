"""
OpenAPI consistency checker for Eidolon Engine.

This script verifies that:
- All deployed API Gateway routes (from CDK lambda_stack.py) exist in the OpenAPI spec.
- All frontend-used API paths (from Flutter ApiService) exist in the OpenAPI spec.
- Reports any extra paths in the spec with no deployment/usage reference.

Run:
  python scripts/openapi_verify.py
"""

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_FILE = REPO_ROOT / "documentation" / "incremental-openapi.yml"
CDK_FILE = REPO_ROOT / "deployment" / "cdk" / "stacks" / "lambda_stack.py"
FLUTTER_API = REPO_ROOT / "incremental" / "lib" / "services" / "api_service.dart"


def load_spec_paths(spec_path: Path) -> set[str]:
    with spec_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    paths = data.get("paths", {}) or {}
    # Ensure leading slash
    return {p if p.startswith("/") else f"/{p}" for p in paths.keys()}


def parse_cdk_routes(cdk_path: Path) -> dict[str, set[str]]:
    """Parse lambda_stack.py to extract routes and methods.

    Returns a dict path -> set(methods)
    """
    text = cdk_path.read_text(encoding="utf-8")

    # Track variable -> path mapping as resources are created
    var_path: dict[str, str] = {}
    routes: dict[str, set[str]] = {}

    # Pattern: <var> = self.api.root.add_resource("xyz")
    root_res_re = re.compile(r"^(\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*self\.api\.root\.add_resource\(\"([^\"]+)\"\)", re.M)
    # Pattern: <child> = <parent>.add_resource("xyz")
    child_res_re = re.compile(r"^(\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([a-zA-Z_][a-zA-Z0-9_]*)\.add_resource\(\"([^\"]+)\"\)", re.M)
    # Pattern: <var>.add_method(...) where METHOD may be on next line
    method_call_re = re.compile(r"^(\s*)([a-zA-Z_][a-zA-Z0-9_]*)\.add_method\(\s*", re.M)
    method_lit_re = re.compile(r"[\"'](GET|POST|PUT|DELETE|OPTIONS)[\"']")

    # Seed top-level known base resource if needed
    for m in root_res_re.finditer(text):
        var, seg = m.group(2), m.group(3)
        var_path[var] = f"/{seg}"

    # Iteratively resolve nested resources (simple single-pass works for this file)
    for m in child_res_re.finditer(text):
        child, parent, seg = m.group(2), m.group(3), m.group(4)
        base = var_path.get(parent)
        if base:
            var_path[child] = f"{base}/{seg}"

    # Collect methods, scanning ahead after each add_method(
    for m in method_call_re.finditer(text):
        var = m.group(2)
        # Look ahead up to the closing parenthesis or a reasonable window
        window = text[m.end() : m.end() + 200]
        mm = method_lit_re.search(window)
        if not mm:
            continue
        method = mm.group(1)
        path = var_path.get(var)
        if path:
            routes.setdefault(path, set()).add(method)

    return routes


def parse_flutter_paths(api_path: Path) -> set[str]:
    text = api_path.read_text(encoding="utf-8")
    # Find Uri.parse('$baseUrl/<path>') occurrences
    # Handles both single-quoted and double-quoted, and string interpolation
    uri_re = re.compile(r"Uri\.parse\(\$?['\"]\$?{?baseUrl}?/?([^'\"]+)['\"]\)")
    paths: set[str] = set()
    for m in uri_re.finditer(text):
        raw = m.group(1)
        # Strip query params for path comparison
        path = raw.split("?")[0]
        if not path.startswith("/"):
            path = f"/{path}"
        paths.add(path)
    return paths


def main() -> int:
    missing_from_spec: list[str] = []
    extra_in_spec: list[str] = []

    spec_paths = load_spec_paths(SPEC_FILE)
    cdk_routes = parse_cdk_routes(CDK_FILE)
    cdk_paths = set(cdk_routes.keys())
    flutter_paths = parse_flutter_paths(FLUTTER_API)

    # Spec vs CDK
    for path in sorted(cdk_paths):
        if path not in spec_paths:
            methods = ",".join(sorted(cdk_routes.get(path, set())))
            missing_from_spec.append(f"{path} [{methods}] (CDK)")

    # Spec vs Flutter
    for path in sorted(flutter_paths):
        if path not in spec_paths:
            missing_from_spec.append(f"{path} (Flutter)")

    # Extra in spec
    for path in sorted(spec_paths):
        if path not in cdk_paths and path not in flutter_paths:
            extra_in_spec.append(path)

    print("OpenAPI Consistency Report")
    print("-" * 80)
    print(f"Spec paths: {len(spec_paths)} | CDK routes: {len(cdk_paths)} | Flutter paths: {len(flutter_paths)}")

    if missing_from_spec:
        print("\nMissing from spec (must add these paths to OpenAPI):")
        for item in missing_from_spec:
            print(f"  - {item}")
    else:
        print("\nNo missing paths from spec.")

    if extra_in_spec:
        print("\nExtra in spec (not referenced by CDK or Flutter):")
        for p in extra_in_spec:
            print(f"  - {p}")
    else:
        print("\nNo extra paths in spec.")

    # Exit non-zero if inconsistencies found
    if missing_from_spec or extra_in_spec:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
