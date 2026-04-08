"""
Core backend utilities package marker.

Keeping this module importable ensures request-scoped context (e.g. user id) is
available to telemetry and Firestore sync in all deployment environments.
"""

