"""The employee profile resource is read as the employee and kept for a few minutes."""

import logging

import pytest

from domain import EmployeeProfile
from tools.mcp_client import (
    PROFILE_RETRY_SECONDS,
    PROFILE_TTL_SECONDS,
    EmployeeProfiles,
    McpProfileError,
    read_employee_profile,
)

PROFILE = EmployeeProfile(
    full_name="Asha Raman", department="Engineering", office_location="Seattle"
)


def _connection(running) -> tuple[str, str]:
    return running.settings.mcp_url, running.settings.mcp_secret


def test_profile_matches_what_the_server_holds(mcp_service) -> None:
    url, secret = _connection(mcp_service)
    held = mcp_service.repository.get_my_profile("E104")

    profile = read_employee_profile(url, secret, "E104")

    assert profile.model_dump() == held.model_dump(exclude={"employee_id"})
    assert profile.summary() == "Asha Raman · Engineering · Seattle"


def test_an_employee_without_a_manager_has_none(mcp_service) -> None:
    url, secret = _connection(mcp_service)

    assert read_employee_profile(url, secret, "E101").manager_name is None


@pytest.mark.parametrize("subject", ["helpdesk-agent", "E999"])
def test_only_an_active_employee_can_read_a_profile(mcp_service, subject) -> None:
    url, secret = _connection(mcp_service)

    with pytest.raises(McpProfileError, match="No active employee for this token"):
        read_employee_profile(url, secret, subject)


def test_unreachable_service_is_reported(mcp_service) -> None:
    secret = mcp_service.settings.mcp_secret

    with pytest.raises(McpProfileError, match="Cannot read the employee profile"):
        read_employee_profile("http://127.0.0.1:9/mcp", secret, "E104")


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_a_profile_is_read_once_then_kept_for_a_while(monkeypatch) -> None:
    reads = []

    def read(url, secret, employee_id):
        reads.append(employee_id)
        return PROFILE

    monkeypatch.setattr("tools.mcp_client.read_employee_profile", read)
    clock = _Clock()
    profiles = EmployeeProfiles("http://x/mcp", "secret", clock=clock)

    assert profiles.get("E104") == PROFILE
    assert profiles.get("E104") == PROFILE
    assert reads == ["E104"]

    profiles.get("E105")
    assert reads == ["E104", "E105"]  # every employee has their own entry

    clock.now = PROFILE_TTL_SECONDS + 1
    profiles.get("E104")
    assert reads == ["E104", "E105", "E104"]


def test_a_failed_read_gives_none_and_is_retried_after_a_pause(monkeypatch, caplog) -> None:
    attempts = []

    def failing(url, secret, employee_id):
        attempts.append(employee_id)
        raise McpProfileError("Cannot read the employee profile (service down).")

    monkeypatch.setattr("tools.mcp_client.read_employee_profile", failing)
    clock = _Clock()
    profiles = EmployeeProfiles("http://x/mcp", "secret", clock=clock)

    with caplog.at_level(logging.WARNING):
        assert profiles.get("E104") is None
        assert profiles.get("E104") is None
    assert attempts == ["E104"]  # no second attempt during the pause
    assert "service down" in caplog.text

    clock.now = PROFILE_RETRY_SECONDS + 1
    profiles.get("E104")
    assert attempts == ["E104", "E104"]
