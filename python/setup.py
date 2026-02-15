from setuptools import setup, find_packages

setup(
    name="mynitor",
    version="0.2.6",
    packages=find_packages(),
    install_requires=[
        "requests>=2.25.0",
    ],
    description="FinOps for AI - Python SDK",
    author="MyNitor AI",
)
