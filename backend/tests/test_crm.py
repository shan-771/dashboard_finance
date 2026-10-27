from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from app.models import UserRole


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


def test_staff_can_set_and_clear_non_restrictive_handler(client: TestClient, make_user) -> None:
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    handler = make_user(email="handler@example.com", role=UserRole.STAFF)
    csrf = sign_in(client, staff.user_id)
    headers = {"X-CSRF-Token": csrf}
    enquiry = client.post("/enquiries", headers=headers, json=new_enquiry_payload()).json()

    assigned = client.patch(
        f"/enquiries/{enquiry['id']}/handler",
        headers=headers,
        json={"handled_by_id": str(handler.id)},
    )
    assert assigned.status_code == 200
    assert assigned.json()["handled_by_id"] == str(handler.id)
    assert assigned.json()["handled_by_name"] == handler.display_name

    cleared = client.patch(
        f"/enquiries/{enquiry['id']}/handler", headers=headers, json={"handled_by_id": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["handled_by_id"] is None


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
