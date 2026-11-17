"""Background workers for Hertex ERP.

Celery is optional at runtime: the API publishes domain events in-process today,
and these tasks provide the seam for moving slow work (notifications, analytics
refreshes, campaign fan-out) onto Redis-backed workers without changing callers.
"""
