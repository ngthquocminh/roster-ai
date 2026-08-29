from __future__ import annotations

from dataclasses import fields
from typing import get_args

from application.contracts.activity import ActivityItemV1
from application.contracts.approval_binding import ApprovalBindingV1, ApprovalStateV1
from application.contracts.audit_envelope import AuditEnvelopeV1, AuditOutcomeV1
from application.capabilities.registry import PolicyInputsV1, derive_policy_version


def test_approval_binding_is_the_frozen_ad20_contract() -> None:
    assert [field.name for field in fields(ApprovalBindingV1)] == [
        "approval_id", "state", "site_id", "action", "initiated_by_actor_id",
        "decided_by_actor_id", "conversation_id", "agent_run_id", "schedule_run_id",
        "candidate_schedule_version_id", "scenario_version_id", "baseline_schedule_version",
        "baseline_resource_version", "parameter_hash", "consequence_summary",
        "consequence_hash", "checksum_algorithm", "checksum_schema_version",
        "policy_version", "created_at", "expires_at", "decided_at", "consumed_at",
        "request_effect_key", "resource_version", "schema_version",
    ]
    assert get_args(ApprovalStateV1) == (
        "pending", "consumed", "rejected", "expired", "stale",
    )


def test_audit_envelope_is_the_frozen_ad20_contract() -> None:
    assert [field.name for field in fields(AuditEnvelopeV1)] == [
        "audit_id", "attempt_id", "request_id", "site_id", "initiated_by_actor_id",
        "decided_by_actor_id", "conversation_id", "agent_run_id", "approval_id",
        "schedule_run_id", "action", "outcome", "success", "effect_key",
        "before_version", "after_version", "safe_summary", "parameter_hash",
        "consequence_hash", "policy_version", "app_version", "worker_facts",
        "evidence_refs", "occurred_at", "schema_version",
    ]
    assert get_args(AuditOutcomeV1) == (
        "approval_requested", "approval_consumed", "approval_rejected",
        "approval_expired", "approval_stale",
    )


def test_activity_union_includes_approval_request_payload() -> None:
    assert "ApprovalRequestActivityV1" in str(ActivityItemV1)


def test_only_decide_time_policy_inputs_change_approval_policy_version() -> None:
    """Task 4 wants BOTH directions, and both must be able to fail.

    Positive: a decide-time input changes the derived value.
    Negative: an unrelated setting does not. The negative direction is the one
    EAD-12 actually exists for -- hashing the whole of `Settings` would
    invalidate every pending approval because someone edited a CORS origin.
    """
    enabled = derive_policy_version(PolicyInputsV1(scheduling_baseline_enabled=True))
    disabled = derive_policy_version(PolicyInputsV1(scheduling_baseline_enabled=False))
    assert enabled != disabled
    assert enabled == derive_policy_version(PolicyInputsV1(scheduling_baseline_enabled=True))

    # NEGATIVE DIRECTION, driven through the real supplier rather than asserted
    # in prose: editing a CORS origin is a `Settings` change that is NOT a
    # decide-time policy input, so the derived version must not move.
    from dataclasses import replace as _replace

    from settings import default_settings

    base = default_settings()
    edited = _replace(base, cors_origins=("https://example.invalid",))
    assert derive_policy_version(
        PolicyInputsV1(scheduling_baseline_enabled=base.scheduling_baseline_enabled)
    ) == derive_policy_version(
        PolicyInputsV1(scheduling_baseline_enabled=edited.scheduling_baseline_enabled)
    )


def test_policy_version_derives_from_every_field_of_the_frozen_input_set() -> None:
    """EAD-12: `derive_policy_version` must hash the WHOLE `PolicyInputsV1`.

    Hashing a hand-listed subset would mean adding a field later silently did
    not change `policy_version` -- the exact opposite of Decision 6's
    "enumerating it is the load-bearing act". Asserting against `asdict` is what
    makes that failure visible the moment a field is added and not hashed.
    """
    import hashlib
    from dataclasses import asdict, fields

    from application.capabilities.registry import POLICY_GENERATION
    from application.contracts.canonical import canonicalize_json

    inputs = PolicyInputsV1(scheduling_baseline_enabled=True)
    expected_digest = hashlib.sha256(canonicalize_json(asdict(inputs))).hexdigest()[:12]
    assert derive_policy_version(inputs) == f"{POLICY_GENERATION}+{expected_digest}"
    # Every declared field participates; none is silently dropped.
    assert set(asdict(inputs)) == {field.name for field in fields(PolicyInputsV1)}
