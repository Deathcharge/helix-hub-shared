#!/usr/bin/env python3
"""
Setup configuration for Helix LLM Agent Engine
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="helix-llm-agent-engine",
    version="1.0.0",
    author="Deathcharge",
    author_email="contact@helix-collective.ai",
    description="Production-ready framework for building multi-LLM agent systems with consciousness modulation",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Deathcharge/helix-llm-agent-engine",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.11",
    install_requires=[
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "aiohttp>=3.8.0",
        "httpx>=0.24.0",
        "openai>=1.0.0",
        "anthropic>=0.7.0",
        "redis>=4.5.0",
        "prometheus-client>=0.17.0",
        "python-dotenv>=1.0.0",
        "pyyaml>=6.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "isort>=5.12.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
        "grok": [
            "xai-sdk>=0.1.0",
        ],
        "local": [
            "ollama>=0.1.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "helix-agent=helix_llm_agent_engine.cli:main",
        ],
    },
)
