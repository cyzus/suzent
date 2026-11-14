"""All inbox clients consume the same server-owned thread identity."""

import json
from pathlib import Path

import pytest

from suzent.core.mailbox_threads import mailbox_presentation
from suzent.core.webhooks import format_webhook_payload
from suzent.database.models import MailboxItemModel
from suzent.routes.mailbox_routes import _item_to_dict

ROOT = Path(__file__).resolve().parents[2]


def event(**changes: object) -> MailboxItemModel:
    return MailboxItemModel(
        **(
            dict(
                id=1,
                source_kind="webhook",
                source_name="custom",
                signature="custom:event",
                summary="An event",
            )
            | changes
        )
    )


def test_shared_contract_fixtures() -> None:
    fixtures = json.loads(
        (ROOT / "packages/mobile-contract/mailbox-thread-fixtures.json").read_text()
    )
    for fixture in fixtures:
        item = MailboxItemModel(**fixture["input"])
        assert mailbox_presentation(item).model_dump() == fixture["presentation"]
        assert _item_to_dict(item)["presentation"] == fixture["presentation"]
    assert (
        fixtures[0]["presentation"]["threadKey"]
        == fixtures[1]["presentation"]["threadKey"]
    )
    assert (
        fixtures[7]["presentation"]["threadKey"]
        == fixtures[8]["presentation"]["threadKey"]
    )


def test_any_webhook_can_thread_across_event_types_and_title_changes() -> None:
    first = event(
        payload='{"thread_id":"ticket-123","subject":"First title"}',
        signature="custom:created",
    )
    second = event(
        id=2,
        payload=format_webhook_payload(
            b'{"thread_id":"ticket-123","subject":"New title"}',
            {"content-type": "application/json"},
        ),
        signature="custom:updated",
    )
    assert (
        mailbox_presentation(first).threadKey == mailbox_presentation(second).threadKey
    )
    assert mailbox_presentation(second).title == "New title"
    assert (
        mailbox_presentation(first).threadKey
        != mailbox_presentation(
            first.model_copy(update={"source_name": "other"})
        ).threadKey
    )
    assert (
        mailbox_presentation(first).threadKey
        != mailbox_presentation(
            first.model_copy(update={"payload": '{"thread_id":"ticket-124"}'})
        ).threadKey
    )


@pytest.mark.parametrize(
    "payload",
    ["broken", "[]", '{"thread_id":42}', '{"thread_id":{}}', '{"thread_id":" "}'],
)
def test_bad_metadata_falls_back_to_source_signature(payload: str) -> None:
    assert (
        mailbox_presentation(event(payload=payload)).threadKey
        == mailbox_presentation(event()).threadKey
    )


def test_source_kind_and_signature_are_separate_namespaces() -> None:
    base = mailbox_presentation(event()).threadKey
    for changes in [
        {"source_kind": "email"},
        {"source_name": "other"},
        {"signature": "different"},
    ]:
        assert mailbox_presentation(event(**changes)).threadKey != base


def test_agent_replies_share_participant_thread() -> None:
    first = event(
        source_kind="agent_inbox",
        source_name="A",
        headers_json='{"from":"a"}',
        target_chat_id="b",
    )
    second = event(
        source_kind="agent_inbox",
        source_name="B",
        headers_json='{"from":"b"}',
        target_chat_id="a",
    )
    assert (
        mailbox_presentation(first).threadKey == mailbox_presentation(second).threadKey
    )
    assert (
        mailbox_presentation(first).threadKey
        != mailbox_presentation(
            first.model_copy(update={"target_chat_id": "c"})
        ).threadKey
    )


def test_github_adapter_is_only_on_server_and_keeps_subjects_separate() -> None:
    first = event(
        source_name="github",
        event_type="pull_request.labeled",
        summary="owner/repo — #12 Fix (labeled)",
        payload='{"label":{"name":"dependencies"}}',
    )
    display = mailbox_presentation(first)
    assert display.title == "Fix"
    assert display.detail == "dependencies"
    assert display.activity == "label_added"
    for changes in [
        {"event_type": "issues.labeled"},
        {"summary": "other/repo — #12 Fix (labeled)"},
        {"summary": "owner/repo — #13 Fix (labeled)"},
    ]:
        assert (
            mailbox_presentation(first.model_copy(update=changes)).threadKey
            != display.threadKey
        )


def test_legacy_github_presentation_cases_move_to_server() -> None:
    fixtures = json.loads(
        (
            ROOT / "packages/mobile-contract/mailbox-presentation-fixtures.json"
        ).read_text()
    )
    for fixture in fixtures:
        result = mailbox_presentation(
            event(
                source_name=fixture["source"],
                event_type=fixture["eventType"],
                summary=fixture["summary"],
                payload=fixture.get("payload", ""),
            )
        )
        assert result.title == fixture["title"]
        assert result.detail == fixture.get("labelName")
