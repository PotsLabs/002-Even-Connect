from setuptools import setup, find_packages

setup(
    name="g1_sdk",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "bleak>=0.21.1",
        "rich>=13.7.0",
        "asyncio>=3.4.3"
    ]
) 