from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.models import ChangeRequestStatus, Customer, Enquiry, EnquiryAuditEvent, EnquiryChangeRequest, FollowUp, UserRole
from app.retention import purge_expired_deleted_enquiries

PASSWORD = "correct horse battery staple"


def sign_in(client: TestClient, user_id: str) -> str:
    response = client.post("/auth/login", json={"user_id": user_id, "password": PASSWORD})
    assert response.status_code == 200
    return response.json()["csrf_token"]


def new_enquiry_payload() -> dict:
    return {
        "customer": {"name": "Riya Shah", "phone": "+91 98765 43210", "email": "riya@example.com"},
        "service_type": "Finance/Loans",
        "source": "Phone",
    }


def create_enquiry(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post("/enquiries", headers=headers, json=new_enquiry_payload())
    assert response.status_code == 201
    return response.json()


def test_staff_edit_request_is_pending_until_manager_approval(client: TestClient, make_user) -> None:
    make_user()
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    staff_headers = {"X-CSRF-Token": sign_in(client, staff.user_id)}
    enquiry = create_enquiry(client, staff_headers)

    submitted = client.post(
        f"/enquiries/{enquiry['id']}/change-requests",
        headers=staff_headers,
        json={"request_type": "edit", "proposed_changes": {"service_type": "Real Estate"}},
    )
    assert submitted.status_code == 201
    assert submitted.json()["status"] == "pending"
    assert client.get("/enquiries").json()["items"][0]["service_type"] == "Finance/Loans"

    manager_headers = {"X-CSRF-Token": sign_in(client, "manager")}
    pending = client.get("/change-requests", headers=manager_headers)
    assert pending.status_code == 200
    assert pending.json()["total"] == 1
    decision = client.patch(
        f"/change-requests/{submitted.json()['id']}",
        headers=manager_headers,
        json={"decision": "approve"},
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "completed"
    assert client.get("/enquiries").json()["items"][0]["service_type"] == "Real Estate"
    assert client.patch(
        f"/change-requests/{submitted.json()['id']}",
        headers=manager_headers,
        json={"decision": "approve"},
    ).status_code == 409


def test_rejection_keeps_enquiry_unchanged_and_staff_cannot_review(client: TestClient, make_user) -> None:
    manager = make_user()
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    staff_headers = {"X-CSRF-Token": sign_in(client, staff.user_id)}
    enquiry = create_enquiry(client, staff_headers)
    request = client.post(
        f"/enquiries/{enquiry['id']}/change-requests",
        headers=staff_headers,
        json={"request_type": "edit", "proposed_changes": {"source": "Referral"}},
    ).json()
    assert client.get("/change-requests", headers=staff_headers).status_code == 403
    manager_headers = {"X-CSRF-Token": sign_in(client, manager.user_id)}
    rejected = client.patch(
        f"/change-requests/{request['id']}",
        headers=manager_headers,
        json={"decision": "reject", "note": "Please verify the lead source"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    current = client.get("/enquiries", headers=manager_headers).json()["items"][0]
    assert current["id"] == enquiry["id"]
    assert current["source"] == "Phone"


def test_stale_edit_request_cannot_overwrite_newer_enquiry_data(client: TestClient, make_user) -> None:
    manager = make_user()
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    staff_headers = {"X-CSRF-Token": sign_in(client, staff.user_id)}
    enquiry = create_enquiry(client, staff_headers)
    request = client.post(
        f"/enquiries/{enquiry['id']}/change-requests",
        headers=staff_headers,
        json={"request_type": "edit", "proposed_changes": {"source": "Referral"}},
    ).json()
    manager_headers = {"X-CSRF-Token": sign_in(client, manager.user_id)}
    assert client.patch(
        f"/enquiries/{enquiry['id']}/status",
        headers=manager_headers,
        json={"status": "Attended"},
    ).status_code == 200
    response = client.patch(
        f"/change-requests/{request['id']}",
        headers=manager_headers,
        json={"decision": "approve"},
    )
    assert response.status_code == 409
    assert client.get("/change-requests?status=stale", headers=manager_headers).json()["total"] == 1
    current = client.get("/enquiries", headers=manager_headers).json()["items"][0]
    assert current["source"] == "Phone"
    assert current["status"] == "Attended"


def test_manager_confirms_deletion_in_one_decision_and_preserves_record(client: TestClient, make_user, test_session_factory) -> None:
    from app.models import EnquiryAuditEvent

    manager = make_user()
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    staff_headers = {"X-CSRF-Token": sign_in(client, staff.user_id)}
    enquiry = create_enquiry(client, staff_headers)
    submitted = client.post(
        f"/enquiries/{enquiry['id']}/change-requests",
        headers=staff_headers,
        json={"request_type": "delete"},
    )
    assert submitted.status_code == 201
    request = submitted.json()
    staff_status = client.get(f"/enquiries/{enquiry['id']}/change-requests", headers=staff_headers)
    assert staff_status.status_code == 200
    assert staff_status.json()["status"] == "pending"
    assert client.get("/enquiries").json()["total"] == 1
    manager_headers = {"X-CSRF-Token": sign_in(client, manager.user_id)}
    manager_pending = client.get("/change-requests?status=pending", headers=manager_headers)
    assert manager_pending.status_code == 200
    assert any(item["id"] == request["id"] for item in manager_pending.json()["items"])
    completed = client.patch(
        f"/change-requests/{request['id']}", headers=manager_headers, json={"decision": "approve"}
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["confirmed_by_user_id"] == str(manager.id)
    assert client.get("/enquiries").json()["total"] == 0
    deleted_page = client.get("/enquiries/deleted", headers=manager_headers)
    assert deleted_page.status_code == 200
    assert deleted_page.json()["total"] == 1
    deleted_row = deleted_page.json()["items"][0]
    assert datetime.fromisoformat(deleted_row["purge_at"]) - datetime.fromisoformat(deleted_row["deleted_at"]) == timedelta(days=5)
    with test_session_factory() as db:
        stored = db.get(Enquiry, UUID(enquiry["id"]))
        retained_request = db.get(EnquiryChangeRequest, UUID(request["id"]))
        audit_event = db.query(EnquiryAuditEvent).one()
        assert stored is not None and stored.deleted_at is not None
        assert retained_request is not None and retained_request.status == ChangeRequestStatus.COMPLETED.value
        assert audit_event.action == "manager_confirmed_soft_deletion"
    assert client.post(
        f"/change-requests/{request['id']}/confirm-deletion", headers=manager_headers
    ).status_code == 409


def test_manager_can_restore_enquiry_during_recovery_window(client: TestClient, make_user, test_session_factory) -> None:
    manager = make_user()
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    staff_headers = {"X-CSRF-Token": sign_in(client, staff.user_id)}
    enquiry = create_enquiry(client, staff_headers)
    next_follow_up = datetime.now(timezone.utc) + timedelta(days=2)
    with test_session_factory() as db:
        stored = db.get(Enquiry, UUID(enquiry["id"]))
        assert stored is not None
        stored.status = "Follow-ups"
        stored.handled_by_id = staff.id
        stored.next_follow_up_at = next_follow_up
        db.commit()
    request = client.post(
        f"/enquiries/{enquiry['id']}/change-requests",
        headers=staff_headers,
        json={"request_type": "delete"},
    ).json()
    manager_headers = {"X-CSRF-Token": sign_in(client, manager.user_id)}
    removed = client.patch(
        f"/change-requests/{request['id']}", headers=manager_headers, json={"decision": "approve"}
    )
    assert removed.status_code == 200
    assert client.get("/enquiries").json()["total"] == 0

    restored = client.post(f"/enquiries/{enquiry['id']}/restore", headers=manager_headers)
    assert restored.status_code == 200
    assert restored.json()["status"] == "Follow-ups"
    restored_follow_up = datetime.fromisoformat(restored.json()["next_follow_up_at"].replace("Z", "+00:00"))
    if restored_follow_up.tzinfo is None:
        restored_follow_up = restored_follow_up.replace(tzinfo=timezone.utc)
    assert restored_follow_up == next_follow_up
    assert client.get("/enquiries").json()["total"] == 1
    assert client.get("/enquiries/deleted", headers=manager_headers).json()["total"] == 0


def test_permanent_purge_removes_linked_history_and_only_unshared_customer(client: TestClient, make_user, test_session_factory) -> None:
    manager = make_user()
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    staff_headers = {"X-CSRF-Token": sign_in(client, staff.user_id)}
    first = create_enquiry(client, staff_headers)
    second_response = client.post(
        "/enquiries",
        headers=staff_headers,
        json={"customer_id": first["customer"]["id"], "service_type": "Real Estate", "source": "Referral"},
    )
    assert second_response.status_code == 201
    second = second_response.json()
    assert second["customer"]["id"] == first["customer"]["id"]
    with test_session_factory() as db:
        db.add(FollowUp(enquiry_id=UUID(first["id"]), completed_at=datetime.now(timezone.utc)))
        db.add(EnquiryAuditEvent(
            enquiry_id=UUID(first["id"]), action="test_history", before_values={}, after_values={}
        ))
        db.commit()
    first_request = client.post(
        f"/enquiries/{first['id']}/change-requests", headers=staff_headers, json={"request_type": "delete"}
    ).json()
    manager_headers = {"X-CSRF-Token": sign_in(client, manager.user_id)}
    assert client.patch(
        f"/change-requests/{first_request['id']}", headers=manager_headers, json={"decision": "approve"}
    ).status_code == 200
    purged = client.delete(f"/enquiries/{first['id']}/permanent", headers=manager_headers)
    assert purged.status_code == 200
    assert purged.json()["customer_deleted"] is False
    with test_session_factory() as db:
        assert db.get(Enquiry, UUID(first["id"])) is None
        assert db.get(Enquiry, UUID(second["id"])) is not None
        assert db.get(Customer, UUID(first["customer"]["id"])) is not None
        assert db.query(FollowUp).filter_by(enquiry_id=UUID(first["id"])).count() == 0
        assert db.query(EnquiryChangeRequest).filter_by(enquiry_id=UUID(first["id"])).count() == 0
        assert db.query(EnquiryAuditEvent).filter_by(enquiry_id=UUID(first["id"])).count() == 0

    second_request = client.post(
        f"/enquiries/{second['id']}/change-requests", headers=staff_headers, json={"request_type": "delete"}
    ).json()
    assert client.patch(
        f"/change-requests/{second_request['id']}", headers=manager_headers, json={"decision": "approve"}
    ).status_code == 200
    final_purge = client.delete(f"/enquiries/{second['id']}/permanent", headers=manager_headers)
    assert final_purge.status_code == 200
    assert final_purge.json()["customer_deleted"] is True
    with test_session_factory() as db:
        assert db.get(Customer, UUID(first["customer"]["id"])) is None


def test_retention_sweeper_purges_only_expired_records(client: TestClient, make_user, test_session_factory) -> None:
    manager = make_user()
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    staff_headers = {"X-CSRF-Token": sign_in(client, staff.user_id)}
    expired = create_enquiry(client, staff_headers)
    recent = client.post(
        "/enquiries",
        headers=staff_headers,
        json={"customer": {"name": "Recent", "phone": "+91 90000 00000"}, "service_type": "Real Estate", "source": "Phone"},
    ).json()
    manager_headers = {"X-CSRF-Token": sign_in(client, manager.user_id)}
    for enquiry in (expired, recent):
        request = client.post(
            f"/enquiries/{enquiry['id']}/change-requests", headers=staff_headers, json={"request_type": "delete"}
        ).json()
        assert client.patch(
            f"/change-requests/{request['id']}", headers=manager_headers, json={"decision": "approve"}
        ).status_code == 200
    now = datetime.now(timezone.utc)
    with test_session_factory() as db:
        stored = db.get(Enquiry, UUID(expired["id"]))
        assert stored is not None
        stored.deleted_at = now - timedelta(days=6)
        db.commit()
    assert purge_expired_deleted_enquiries(test_session_factory, now=now) == 1
    with test_session_factory() as db:
        assert db.get(Enquiry, UUID(expired["id"])) is None
        assert db.get(Enquiry, UUID(recent["id"])) is not None


def test_manager_direct_edit_is_audited_and_staff_cannot_use_it(client: TestClient, make_user, test_session_factory) -> None:
    from app.models import EnquiryAuditEvent

    manager = make_user()
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    staff_headers = {"X-CSRF-Token": sign_in(client, staff.user_id)}
    enquiry = create_enquiry(client, staff_headers)
    denied = client.patch(
        f"/enquiries/{enquiry['id']}",
        headers=staff_headers,
        json={"service_type": "Real Estate"},
    )
    assert denied.status_code == 403
    manager_headers = {"X-CSRF-Token": sign_in(client, manager.user_id)}
    updated = client.patch(
        f"/enquiries/{enquiry['id']}",
        headers=manager_headers,
        json={"service_type": "Real Estate"},
    )
    assert updated.status_code == 200
    assert updated.json()["service_type"] == "Real Estate"
    with test_session_factory() as db:
        event = db.query(EnquiryAuditEvent).one()
        assert event.action == "manager_direct_edit"
        assert event.before_values["service_type"] == "Finance/Loans"
        assert event.after_values["service_type"] == "Real Estate"
