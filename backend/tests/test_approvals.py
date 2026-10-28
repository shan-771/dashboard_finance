from fastapi.testclient import TestClient
from uuid import UUID

from app.models import ChangeRequestStatus, Enquiry, EnquiryChangeRequest, UserRole

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


def test_deletion_request_requires_approval_then_confirmation_and_preserves_record(client: TestClient, make_user, test_session_factory) -> None:
    manager = make_user()
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    staff_headers = {"X-CSRF-Token": sign_in(client, staff.user_id)}
    enquiry = create_enquiry(client, staff_headers)
    request = client.post(
        f"/enquiries/{enquiry['id']}/change-requests",
        headers=staff_headers,
        json={"request_type": "delete", "reason": "Duplicate record confirmed by customer"},
    ).json()
    assert client.get("/enquiries").json()["total"] == 1
    manager_headers = {"X-CSRF-Token": sign_in(client, manager.user_id)}
    approved = client.patch(
        f"/change-requests/{request['id']}", headers=manager_headers, json={"decision": "approve"}
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert client.get("/enquiries").json()["total"] == 1
    completed = client.post(
        f"/change-requests/{request['id']}/confirm-deletion", headers=manager_headers
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["confirmed_by_user_id"] == str(manager.id)
    assert client.get("/enquiries").json()["total"] == 0
    with test_session_factory() as db:
        stored = db.get(Enquiry, UUID(enquiry["id"]))
        retained_request = db.get(EnquiryChangeRequest, UUID(request["id"]))
        assert stored is not None and stored.deleted_at is not None
        assert retained_request is not None and retained_request.status == ChangeRequestStatus.COMPLETED.value
    assert client.post(
        f"/change-requests/{request['id']}/confirm-deletion", headers=manager_headers
    ).status_code == 409


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
