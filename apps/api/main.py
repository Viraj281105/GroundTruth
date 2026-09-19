"""ASGI entrypoint for the GroundTruth API.

**Owner: Bhumi.**

Deliberately thin. All application logic lives in
``groundtruth.platform.api``; this file exists so the deployment target has a
stable import path that does not change when the package is reorganised.

Run locally::

    uvicorn apps.api.main:app --reload --port 8000
"""

from groundtruth.platform.api.app import app

__all__ = ["app"]
