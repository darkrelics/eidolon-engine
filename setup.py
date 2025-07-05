"""
Setup script for the Eidolon common library.
"""

"""
Setup script for the Eidolon common library.
"""
from setuptools import find_packages, setup


def parse_requirements(filename):
    """Load requirements from a pip requirements file."""
    with open(filename, "r") as f:
        lines = f.readlines()
    # Filter out comments and empty lines
    requirements = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    return requirements


requirements = parse_requirements("requirements/scripts-requirements.txt")

setup(
    name="eidolon-common",
    version="0.1.0",
    packages=find_packages(include=["eidolon", "eidolon.*"]),
    description="Common library for Eidolon MUD Engine Lambda functions and scripts.",
    author="Jason Robinson",
    license="Apache 2.0",
    install_requires=requirements,
)
