"""Setup script for Jira Work Log Tool."""

from setuptools import setup, find_packages
from pathlib import Path

# Read version from VERSION file
version_file = Path(__file__).parent / "VERSION"
version = version_file.read_text().strip() if version_file.exists() else "0.1.0"

# Read requirements from requirements.txt
requirements_file = Path(__file__).parent / "requirements.txt"
if requirements_file.exists():
    with open(requirements_file, "r") as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]
else:
    requirements = []

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

setup(
    name="jira-worklog-tool",
    version=version,
    description="Python CLI tool for managing Jira work logs with Excel integration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Jira Work Log Tool",
    url="https://github.com/your-username/jira-worklog",
    packages=find_packages(where=".", include=["src*"]),
    package_dir={"": "."},
    py_modules=[],
    install_requires=requirements,
    python_requires=">=3.11",
    entry_points={
        "console_scripts": [
            "jira-worklog=src.main:cli",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Office/Business",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    keywords="jira worklog excel time-tracking cli",
    project_urls={
        "Bug Reports": "https://github.com/your-username/jira-worklog/issues",
        "Source": "https://github.com/your-username/jira-worklog",
    },
)

