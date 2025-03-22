"""
Email notification module for Airgap SNS.

This module provides functionality for monitoring email accounts and
sending notifications through the Airgap SNS system when new emails arrive.
"""

from airgap_sns.email.notification import EmailListener, EmailNotificationModule

__all__ = ['EmailListener', 'EmailNotificationModule']
