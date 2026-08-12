"""Authoritative AD-5 capability risk vocabulary.

Re-exported from `application/contracts/capability_manifest.py`, where the name
is now defined: the manifest contract owns the vocabulary its own field is typed
by, so `application/contracts/**` never has to import `application/capabilities/**`.
This module remains the vocabulary's published import site.
"""
from application.contracts.capability_manifest import RiskClassV1

__all__ = ["RiskClassV1"]
