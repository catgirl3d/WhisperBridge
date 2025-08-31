"""
Setup script for WhisperBridge.

This script handles the installation and packaging of the WhisperBridge application.
"""

from setuptools import setup, find_packages
import os

# Read README
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Read requirements
def read_requirements(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

install_requires = read_requirements("requirements.txt")

setup(
    name="whisperbridge",
    version="1.0.0",
    author="WhisperBridge Team",
    author_email="team@whisperbridge.dev",
    description="Desktop application for quick text translation using OCR and GPT API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/whisperbridge",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Utilities",
        "Topic :: Multimedia :: Graphics :: Capture :: Screen Capture",
        "Topic :: Text Processing :: Linguistic",
    ],
    python_requires=">=3.8",
    install_requires=install_requires,
    extras_require={
        "dev": read_requirements("requirements-dev.txt"),
        "build": ["build", "twine"],
        "docs": ["sphinx", "sphinx-rtd-theme"],
    },
    entry_points={
        "console_scripts": [
            "whisperbridge=whisperbridge.main:main",
        ],
    },
    package_data={
        "whisperbridge": [
            "assets/*",
            "config/*",
            "assets/icons/*",
            "assets/sounds/*",
            "assets/themes/*",
        ],
    },
    include_package_data=True,
    zip_safe=False,
    keywords="ocr translation gpt desktop-application screen-capture",
    project_urls={
        "Bug Reports": "https://github.com/yourusername/whisperbridge/issues",
        "Source": "https://github.com/yourusername/whisperbridge",
        "Documentation": "https://whisperbridge.readthedocs.io/",
    },
)