from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="airgap_sns",
    version="0.0.1",
    author="Airgap SNS Team",
    author_email="john@fimbriata.dev",
    description="Secure Notification System with audio capabilities",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/airgap-sns",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "fastapi>=0.68.0",
        "uvicorn>=0.15.0",
        "websockets>=10.0",
        "pydantic>=1.8.2",
        "cryptography>=36.0.0",
        "aiohttp>=3.8.1",
        "python-dotenv>=0.19.0",
    ],
    extras_require={
        "audio": ["ggwave>=0.3.0", "sounddevice>=0.4.4", "numpy>=1.21.0"],
        "chat": ["openai>=0.27.0", "httpx>=0.24.0"],
        "tunnel": ["zrok>=0.1.0"],
        "dev": ["pytest>=6.2.5", "black>=21.9b0", "isort>=5.9.3"],
    },
    entry_points={
        "console_scripts": [
            "airgap-sns-host=airgap_sns.host.server:run_server",
            "airgap-sns-client=airgap_sns.client.client:run_client",
            "airgap-sns-chat=airgap_sns.chat.app:run_chat_app",
        ],
    },
)
