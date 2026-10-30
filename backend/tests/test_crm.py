import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from app.models import UserRole
from app.notifications import NotificationHub


PASSWORD = "correct horse battery staple"


def sign_in(client: TestClient, user_id: str) -> str:
    response = client.post("/auth/login", json={"user_id": user_id, "password": PASSWORD})
    assert response.status_code == 200
    return response.json()["csrf_token"]


def new_enquiry_payload(name: str = "Riya Shah") -> dict:
    return {
        "customer": {"name": name, "phone": "+91 98765 43210", "email": "riya@example.com"},
        "service_type": "Finance/Loans",
        "source": "Phone",
    }


def test_notification_hub_pushes_events_to_connected_user() -> None:
    async def receive_event() -> None:
        hub = NotificationHub()
        user_id = uuid4()
        loop = asyncio.get_running_loop()
        first_session: asyncio.Queue[str] = asyncio.Queue(maxsize=5)
        second_session: asyncio.Queue[str] = asyncio.Queue(maxsize=5)
        hub.subscribe(user_id, loop, first_session)
        hub.subscribe(user_id, loop, second_session)

        hub.publish(user_id, {"title": "New enquiry"})

        first = await asyncio.wait_for(first_session.get(), timeout=1)
        second = await asyncio.wait_for(second_session.get(), timeout=1)
        assert first == second == '{"title":"New enquiry"}'
        hub.unsubscribe(user_id, loop, first_session)
        hub.unsubscribe(user_id, loop, second_session)

    asyncio.run(receive_event())


def test_enquiry_creation_and_multiple_enquiries_per_customer(client: TestClient, make_user) -> None:
    user = make_user()
    csrf = sign_in(client, user.user_id)
    headers = {"X-CSRF-Token": csrf}

    first = client.post("/enquiries", headers=headers, json=new_enquiry_payload())
    assert first.status_code == 201
    first_body = first.json()
    assert first_body["status"] == "New"
    assert first_body["handled_by_id"] is None

    second = client.post(
        "/enquiries",
        headers=headers,
        json={"customer_id": first_body["customer"]["id"], "service_type": "Real Estate", "source": "Referral"},
    )
    assert second.status_code == 201
    assert second.json()["customer"]["id"] == first_body["customer"]["id"]

    response = client.get("/enquiries?limit=1")
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 1
    assert len(client.get("/customers").json()) == 1
    filtered = client.get("/enquiries?service_type=Real%20Estate&source=Referral&status=New&search=Riya")
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["customer"]["id"] == first_body["customer"]["id"]
    closed = client.patch(
        f"/enquiries/{first_body['id']}/status",
        headers=headers,
        json={"status": "Closed"},
    )
    assert closed.status_code == 200
    remaining = client.get("/enquiries?status=New")
    assert remaining.json()["total"] == 1
    assert remaining.json()["items"][0]["id"] == second.json()["id"]


def test_crm_requires_authentication_and_csrf_for_writes(client: TestClient, make_user) -> None:
    assert client.get("/customers").status_code == 401
    assert client.post("/enquiries", json=new_enquiry_payload()).status_code == 401
    user = make_user()
    sign_in(client, user.user_id)
    assert client.post("/enquiries", json=new_enquiry_payload()).status_code == 403


def test_staff_can_view_and_create_enquiries(client: TestClient, make_user) -> None:
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    csrf = sign_in(client, staff.user_id)
    created = client.post(
        "/enquiries", headers={"X-CSRF-Token": csrf}, json=new_enquiry_payload()
    )
    assert created.status_code == 201
    assert client.get("/enquiries").json()["total"] == 1


def test_notifications_follow_recipient_rules_and_can_be_marked_read(client: TestClient, make_user) -> None:
    manager = make_user()
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    other_staff = make_user(email="other.staff@example.com", role=UserRole.STAFF)
    manager_csrf = sign_in(client, manager.user_id)
    staff_csrf = sign_in(client, staff.user_id)
    other_staff_csrf = sign_in(client, other_staff.user_id)

    created = client.post(
        "/enquiries",
        headers={"X-CSRF-Token": manager_csrf},
        json=new_enquiry_payload(),
    )
    assert created.status_code == 201
    enquiry_id = created.json()["id"]

    client.cookies.clear()
    staff_csrf = sign_in(client, staff.user_id)
    staff_notifications = client.get("/notifications").json()
    assert staff_notifications["unread_count"] == 1
    assert staff_notifications["items"][0]["notification_type"] == "new_enquiry"
    assert staff_notifications["items"][0]["enquiry_id"] == enquiry_id

    client.cookies.clear()
    other_staff_csrf = sign_in(client, other_staff.user_id)
    other_notifications = client.get("/notifications").json()
    assert other_notifications["unread_count"] == 1
    assert client.patch(
        f"/notifications/{staff_notifications['items'][0]['id']}/read",
        headers={"X-CSRF-Token": other_staff_csrf},
        json={},
    ).status_code == 404

    client.cookies.clear()
    manager_csrf = sign_in(client, manager.user_id)
    assert client.get("/notifications").json()["unread_count"] == 0

    client.cookies.clear()
    staff_csrf = sign_in(client, staff.user_id)
    request_response = client.post(
        f"/enquiries/{enquiry_id}/change-requests",
        headers={"X-CSRF-Token": staff_csrf},
        json={"request_type": "delete"},
    )
    assert request_response.status_code == 201
    request_id = request_response.json()["id"]

    client.cookies.clear()
    manager_csrf = sign_in(client, manager.user_id)
    manager_notifications = client.get("/notifications").json()
    assert manager_notifications["unread_count"] == 1
    assert manager_notifications["items"][0]["notification_type"] == "deletion_request"
    assert manager_notifications["items"][0]["enquiry_id"] == enquiry_id

    decision = client.patch(
        f"/change-requests/{request_id}",
        headers={"X-CSRF-Token": manager_csrf},
        json={"decision": "approve"},
    )
    assert decision.status_code == 200

    client.cookies.clear()
    staff_csrf = sign_in(client, staff.user_id)
    decision_notifications = client.get("/notifications").json()
    assert decision_notifications["unread_count"] == 2
    assert decision_notifications["items"][0]["notification_type"] == "deletion_decision"
    assert decision_notifications["items"][0]["title"] == "Deletion request approved"

    read_all = client.patch(
        "/notifications/read-all",
        headers={"X-CSRF-Token": staff_csrf},
        json={},
    )
    assert read_all.status_code == 200
    assert read_all.json()["updated_count"] == 2
    assert client.get("/notifications").json()["unread_count"] == 0


def test_staff_first_claim_wins_and_other_staff_gets_taken_notice(client: TestClient, make_user) -> None:
    manager = make_user()
    manager_csrf = sign_in(client, manager.user_id)
    enquiry = client.post(
        "/enquiries", headers={"X-CSRF-Token": manager_csrf}, json=new_enquiry_payload()
    ).json()
    first_staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    first_csrf = sign_in(client, first_staff.user_id)
    claim = client.post(
        f"/enquiries/{enquiry['id']}/claim", headers={"X-CSRF-Token": first_csrf}, json={}
    )
    assert claim.status_code == 200
    assert claim.json()["status"] == "Assigned"
    assert claim.json()["handled_by_id"] == str(first_staff.id)
    assert claim.json()["handled_by_name"] == first_staff.display_name

    second_staff = make_user(email="second@example.com", role=UserRole.STAFF)
    second_csrf = sign_in(client, second_staff.user_id)
    competing_claim = client.post(
        f"/enquiries/{enquiry['id']}/claim", headers={"X-CSRF-Token": second_csrf}, json={}
    )
    assert competing_claim.status_code == 409
    assert first_staff.display_name in competing_claim.json()["detail"]


def test_claimed_enquiry_notes_and_follow_up_are_saved_by_handler(client: TestClient, make_user) -> None:
    manager = make_user()
    manager_csrf = sign_in(client, manager.user_id)
    enquiry = client.post(
        "/enquiries", headers={"X-CSRF-Token": manager_csrf}, json=new_enquiry_payload()
    ).json()
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    staff_csrf = sign_in(client, staff.user_id)
    headers = {"X-CSRF-Token": staff_csrf}
    claimed = client.post(f"/enquiries/{enquiry['id']}/claim", headers=headers, json={})
    assert claimed.status_code == 200

    follow_up_at = datetime.now(timezone.utc) + timedelta(days=2)
    saved = client.put(
        f"/enquiries/{enquiry['id']}/contact",
        headers=headers,
        json={"notes": "Discussed financing options", "next_follow_up_at": follow_up_at.isoformat()},
    )
    assert saved.status_code == 200
    assert saved.json()["notes"] == "Discussed financing options"
    assert saved.json()["status"] == "Follow-ups"
    assert saved.json()["handled_by_id"] == str(staff.id)
    upcoming = client.get("/follow-ups?bucket=upcoming")
    assert any(row["id"] == enquiry["id"] for row in upcoming.json()["items"])

    other = make_user(email="other@example.com", role=UserRole.STAFF)
    other_csrf = sign_in(client, other.user_id)
    rejected = client.put(
        f"/enquiries/{enquiry['id']}/contact",
        headers={"X-CSRF-Token": other_csrf},
        json={"notes": "Overwriting", "next_follow_up_at": follow_up_at.isoformat()},
    )
    assert rejected.status_code == 403
    rejected_outcome = client.patch(
        f"/enquiries/{enquiry['id']}/status",
        headers={"X-CSRF-Token": other_csrf},
        json={"status": "Closed"},
    )
    assert rejected_outcome.status_code == 403


def test_claimed_staff_can_mark_lost_do_not_contact_without_followup(client: TestClient, make_user) -> None:
    manager = make_user()
    manager_csrf = sign_in(client, manager.user_id)
    enquiry = client.post(
        "/enquiries", headers={"X-CSRF-Token": manager_csrf}, json=new_enquiry_payload()
    ).json()
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    staff_csrf = sign_in(client, staff.user_id)
    headers = {"X-CSRF-Token": staff_csrf}
    claimed = client.post(f"/enquiries/{enquiry['id']}/claim", headers=headers, json={})
    assert claimed.status_code == 200

    lost = client.patch(
        f"/enquiries/{enquiry['id']}/status",
        headers=headers,
        json={"status": "Lost", "do_not_contact": True, "outcome_reason": "Customer declined further contact"},
    )
    assert lost.status_code == 200
    assert lost.json()["status"] == "Lost"
    assert lost.json()["do_not_contact"] is True
    assert lost.json()["outcome_reason"] == "Customer declined further contact"
    assert lost.json()["next_follow_up_at"] is None
    assert client.put(
        f"/enquiries/{enquiry['id']}/follow-up",
        headers=headers,
        json={"next_follow_up_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()},
    ).status_code == 409


def test_handler_can_mark_enquiry_open_and_final_outcome_clears_schedule(client: TestClient, make_user) -> None:
    manager = make_user()
    manager_csrf = sign_in(client, manager.user_id)
    enquiry = client.post(
        "/enquiries", headers={"X-CSRF-Token": manager_csrf}, json=new_enquiry_payload()
    ).json()
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    staff_csrf = sign_in(client, staff.user_id)
    headers = {"X-CSRF-Token": staff_csrf}
    assert client.post(f"/enquiries/{enquiry['id']}/claim", headers=headers, json={}).status_code == 200
    follow_up_at = datetime.now(timezone.utc) + timedelta(days=2)
    saved = client.put(
        f"/enquiries/{enquiry['id']}/contact",
        headers=headers,
        json={"notes": "Requirement not met yet", "next_follow_up_at": follow_up_at.isoformat()},
    )
    assert saved.status_code == 200

    opened = client.patch(
        f"/enquiries/{enquiry['id']}/status",
        headers=headers,
        json={"status": "Open", "outcome_reason": "May contact about future offers"},
    )
    assert opened.status_code == 200
    assert opened.json()["status"] == "Open"
    assert opened.json()["next_follow_up_at"] is None
    assert opened.json()["outcome_reason"] == "May contact about future offers"


def test_claim_endpoint_is_database_rate_limited_per_staff(client: TestClient, make_user) -> None:
    manager = make_user()
    manager_csrf = sign_in(client, manager.user_id)
    enquiry_ids = [
        client.post("/enquiries", headers={"X-CSRF-Token": manager_csrf}, json=new_enquiry_payload(f"Lead {index}")).json()["id"]
        for index in range(11)
    ]
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    staff_csrf = sign_in(client, staff.user_id)
    results = [
        client.post(f"/enquiries/{enquiry_id}/claim", headers={"X-CSRF-Token": staff_csrf}, json={})
        for enquiry_id in enquiry_ids
    ]
    assert [result.status_code for result in results[:10]] == [200] * 10
    assert results[10].status_code == 429


def test_enquiry_status_transitions_and_do_not_contact(client: TestClient, make_user) -> None:
    user = make_user()
    csrf = sign_in(client, user.user_id)
    headers = {"X-CSRF-Token": csrf}
    created = client.post("/enquiries", headers=headers, json=new_enquiry_payload()).json()
    enquiry_id = created["id"]

    attended = client.patch(
        f"/enquiries/{enquiry_id}/status", headers=headers, json={"status": "Attended"}
    )
    assert attended.status_code == 200
    assert attended.json()["status"] == "Attended"

    follow_ups = client.patch(
        f"/enquiries/{enquiry_id}/status", headers=headers, json={"status": "Follow-ups"}
    )
    assert follow_ups.status_code == 200
    lost = client.patch(
        f"/enquiries/{enquiry_id}/status",
        headers=headers,
        json={"status": "Lost", "do_not_contact": True, "outcome_reason": "Asked us not to call"},
    )
    assert lost.status_code == 200
    assert lost.json()["do_not_contact"] is True

    clear_contact_restriction = client.patch(
        f"/enquiries/{enquiry_id}/status",
        headers=headers,
        json={"status": "Lost", "do_not_contact": False},
    )
    assert clear_contact_restriction.status_code == 409

    reopen = client.patch(
        f"/enquiries/{enquiry_id}/status", headers=headers, json={"status": "Attended"}
    )
    assert reopen.status_code == 409


def test_new_enquiry_can_be_marked_open_without_followups(client: TestClient, make_user) -> None:
    user = make_user()
    csrf = sign_in(client, user.user_id)
    created = client.post(
        "/enquiries", headers={"X-CSRF-Token": csrf}, json=new_enquiry_payload()
    ).json()

    response = client.patch(
        f"/enquiries/{created['id']}/status",
        headers={"X-CSRF-Token": csrf},
        json={"status": "Open", "outcome_reason": "May contact about future offers"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Open"
    assert response.json()["outcome_reason"] == "May contact about future offers"


def test_completed_follow_ups_and_actionable_date_buckets(client: TestClient, make_user) -> None:
    user = make_user()
    csrf = sign_in(client, user.user_id)
    headers = {"X-CSRF-Token": csrf}
    zone = ZoneInfo("Asia/Kolkata")
    now = datetime.now(zone)
    today = now.date()
    start_today = datetime.combine(today, datetime.min.time(), tzinfo=zone)

    enquiries = {}
    for name, scheduled in (
        ("Due Today", start_today + timedelta(hours=12)),
        ("Upcoming", start_today + timedelta(days=2, hours=12)),
        ("Overdue", start_today - timedelta(hours=12)),
    ):
        created = client.post("/enquiries", headers=headers, json=new_enquiry_payload(name)).json()
        enquiries[name] = created
        scheduled_response = client.put(
            f"/enquiries/{created['id']}/follow-up",
            headers=headers,
            json={"next_follow_up_at": scheduled.isoformat()},
        )
        assert scheduled_response.status_code == 200
        assert scheduled_response.json()["completed_follow_up_count"] == 0

    completed = client.post(
        f"/enquiries/{enquiries['Due Today']['id']}/follow-ups",
        headers=headers,
        json={},
    )
    assert completed.status_code == 201
    assert completed.json()["created_by_user_id"] == str(user.id)
    history = client.get(f"/enquiries/{enquiries['Due Today']['id']}/follow-ups")
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["id"] == completed.json()["id"]
    listed = client.get("/enquiries").json()["items"]
    due_record = next(row for row in listed if row["id"] == enquiries["Due Today"]["id"])
    assert due_record["completed_follow_up_count"] == 1
    assert due_record["next_follow_up_at"] is None
    assert due_record["status"] == "Closed"

    for bucket, expected_name in (("upcoming", "Upcoming"), ("overdue", "Overdue")):
        response = client.get(f"/follow-ups?bucket={bucket}")
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["items"][0]["customer"]["name"] == expected_name
    assert client.get("/follow-ups?bucket=due-today").json()["total"] == 0


def test_finalizing_enquiry_clears_schedule_and_blocks_future_follow_ups(client: TestClient, make_user) -> None:
    user = make_user()
    csrf = sign_in(client, user.user_id)
    headers = {"X-CSRF-Token": csrf}
    enquiry = client.post("/enquiries", headers=headers, json=new_enquiry_payload()).json()
    scheduled = client.put(
        f"/enquiries/{enquiry['id']}/follow-up",
        headers=headers,
        json={"next_follow_up_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
    )
    assert scheduled.status_code == 200
    closed = client.patch(
        f"/enquiries/{enquiry['id']}/status", headers=headers, json={"status": "Closed"}
    )
    assert closed.status_code == 200
    assert closed.json()["next_follow_up_at"] is None
    assert client.post(f"/enquiries/{enquiry['id']}/follow-ups", headers=headers, json={}).status_code == 409
    assert client.get(f"/enquiries/{enquiry['id']}/follow-ups").json()["total"] == 0
    assert client.put(
        f"/enquiries/{enquiry['id']}/follow-up",
        headers=headers,
        json={"next_follow_up_at": None},
    ).status_code == 409


def test_follow_up_requires_timezone_and_authentication(client: TestClient, make_user) -> None:
    assert client.get("/follow-ups?bucket=due-today").status_code == 401
    user = make_user()
    csrf = sign_in(client, user.user_id)
    headers = {"X-CSRF-Token": csrf}
    enquiry = client.post("/enquiries", headers=headers, json=new_enquiry_payload()).json()
    response = client.put(
        f"/enquiries/{enquiry['id']}/follow-up",
        headers=headers,
        json={"next_follow_up_at": "2026-10-28T12:00:00"},
    )
    assert response.status_code == 422


def test_invalid_enquiry_values_and_missing_customer_are_rejected(client: TestClient, make_user) -> None:
    user = make_user()
    csrf = sign_in(client, user.user_id)
    headers = {"X-CSRF-Token": csrf}

    missing_contact = client.post(
        "/enquiries", headers=headers,
        json={"service_type": "Finance/Loans", "source": "Phone"},
    )
    assert missing_contact.status_code == 422
    unknown_customer = client.post(
        "/enquiries", headers=headers,
        json={"customer_id": "2b195b29-9984-48fa-a93f-a2f3ccf5515c", "service_type": "Finance/Loans", "source": "Phone"},
    )
    assert unknown_customer.status_code == 404
    invalid_status = client.patch(
        "/enquiries/2b195b29-9984-48fa-a93f-a2f3ccf5515c/status",
        headers=headers, json={"status": "Definitely Won"},
    )
    assert invalid_status.status_code == 422


def test_website_lead_is_created_as_new_website_enquiry(client: TestClient, make_user) -> None:
    response = client.post(
        "/public/enquiries",
        json={
            "customer": {"name": "Website Lead", "phone": "+91 99887 76655"},
            "service_type": "Real Estate",
        },
    )
    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    listing = client.get("/enquiries")
    assert listing.status_code == 401
    user = make_user()
    sign_in(client, user.user_id)
    visible = client.get("/enquiries")
    assert visible.status_code == 200
    website_enquiry = visible.json()["items"][0]
    assert website_enquiry["source"] == "Website"
    assert website_enquiry["status"] == "New"
    assert website_enquiry["service_type"] == "Real Estate"


def test_staff_can_explicitly_link_website_customer_to_existing_record(client: TestClient, make_user) -> None:
    user = make_user()
    csrf = sign_in(client, user.user_id)
    headers = {"X-CSRF-Token": csrf}
    original = client.post("/enquiries", headers=headers, json=new_enquiry_payload()).json()
    website = client.post(
        "/public/enquiries",
        json={
            "customer": {"name": "Riya S.", "phone": "+91 98765 43210", "email": "riya@example.com"},
            "service_type": "Real Estate",
        },
    )
    assert website.status_code == 202
    customers = client.get("/customers").json()
    assert len(customers) == 2
    source_id = next(row["id"] for row in customers if row["name"] == "Riya S.")

    linked = client.post(
        f"/customers/{original['customer']['id']}/link",
        headers=headers,
        json={"source_customer_id": source_id},
    )
    assert linked.status_code == 200
    assert linked.json()["enquiries_relinked"] == 1
    reused_merged_customer = client.post(
        "/enquiries",
        headers=headers,
        json={"customer_id": source_id, "service_type": "Finance/Loans", "source": "Phone"},
    )
    assert reused_merged_customer.status_code == 409
    assert len(client.get("/customers").json()) == 1
    enquiries = client.get("/enquiries").json()["items"]
    assert {row["customer"]["id"] for row in enquiries} == {original["customer"]["id"]}
