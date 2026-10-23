# AGENT.md — Backend Development Instructions
## Real Estate & Finance CRM Dashboard

## 1. Project Objective

Build a secure, maintainable backend for a business management dashboard used by a real estate brokerage and finance/loan consultancy.

The business operates two service lines:

- **Real Estate:** Property enquiries, property listings, buyers, sellers, and property-related services.
- **Finance & Loans:** Home loans, property financing, and other financial services offered by the business.

Both service lines must be managed through one unified CRM system.

The backend must support the existing frontend, website-generated leads, staff workflows, follow-ups, customer records, property management, and administrative approvals.

This is a small-team application. Prioritize reliability, simplicity, data integrity, and maintainability over unnecessary enterprise-level complexity.

## 2. Mandatory Development Rules

These rules take precedence over convenience or assumptions.

### 2.1 Work in Phases

**NEVER implement the entire backend in one go.**

Development must proceed through clearly defined phases. Each phase must have a specific scope, implementation tasks, and verification criteria.

The required workflow is:

1. Inspect the existing repository and understand its current state.
2. Identify the next incomplete phase.
3. Explain the phase's scope and planned changes to the user.
4. Ask the user for approval before implementing that phase.
5. Implement only the approved phase.
6. Run appropriate tests and checks.
7. Summarize completed work, modified files, tests, known issues, and decisions needed.
8. Ask for approval before moving to the next phase.

Do not begin the next phase automatically after finishing the current one.

If the user requests a specific change to the current phase, handle that request within the agreed scope when possible.

### 2.2 Ask Before Making Important Decisions

Ask the user before proceeding when a decision materially affects:

- Database structure or relationships.
- Authentication or authorization.
- Destructive operations or data retention.
- Public website API contracts.
- External services, integrations, or paid dependencies.
- Property-specific fields that have not yet been finalized.
- Major architectural changes.

Do not repeatedly ask questions about requirements already established in this document.

For smaller implementation details, use sensible defaults, document the decision, and continue within the approved phase.

### 2.3 Inspect Before Modifying

Before writing backend code:

- Inspect the repository structure and existing source files.
- Read the existing `package.json`, README, configuration files, and relevant frontend API usage where available.
- Identify the current frontend framework, routes, forms, expected data structures, and existing integrations.
- Check whether any backend code already exists.
- Identify existing dependencies, naming conventions, and configuration patterns.

Do not assume that the repository is empty.

Do not replace working code, delete files, regenerate the project, or introduce a new architecture without a clear reason and user approval where the change is significant.

### 2.4 Keep Changes Small and Reviewable

- Implement only what belongs to the current approved phase.
- Prefer small, logically grouped changes.
- Avoid creating every model, endpoint, service, and module before their requirements are needed.
- Do not generate large amounts of placeholder code for future phases.
- Do not introduce unused dependencies or speculative abstractions.
- Keep code readable and easy for the user to understand and maintain.
- Reuse existing conventions when appropriate.

If a dependency is required, explain why it is needed before introducing it when the choice materially affects the project.

### 2.5 Never Claim Untested Success

After implementation:

- Run the available relevant tests.
- Check imports and application startup where possible.
- Validate changed endpoints and business rules.
- Report failed or unavailable checks honestly.
- Do not claim that an endpoint, integration, or feature works unless it has been verified.

---

## 3. Proposed Backend Technology

Use the following as the initial direction, subject to inspection of the existing project and user approval.

- **Language:** Python
- **Backend framework:** FastAPI
- **Database:** PostgreSQL
- **ORM:** SQLAlchemy 2.x
- **Database migrations:** Alembic
- **Request validation:** Pydantic
- **Testing:** Pytest and FastAPI's testing utilities
- **API documentation:** FastAPI-generated OpenAPI documentation
- **Authentication:** Secure, standards-based authentication suitable for a staff dashboard
- **Configuration:** Environment variables managed through a validated settings module

Do not install all these dependencies immediately. Introduce them incrementally when the relevant phase is approved.

If an existing implementation already establishes a suitable technology choice, inspect it and discuss any proposed changes before replacing it.

Do not introduce Redis, Celery, microservices, a message broker, blockchain, or other infrastructure without a demonstrated requirement.

---

## 4. Business Roles and Permissions

The initial team consists of:

- One administrator.
- One manager.
- Two staff members.

Keep role configuration extensible so that additional staff can be added later.

### 4.1 Administrator

The administrator is responsible for administrative access and account-level operations.

The exact distinction between administrator and manager permissions has not yet been finalized. Do not silently assume they are identical.

Ask the user to finalize their differences before implementing privileged account-management functionality.

### 4.2 Manager

The manager must be able to:

- View all enquiries and customer records.
- View all staff members and their `Handled By` information.
- Review proposed edits and deletion requests.
- Approve or reject staff change requests.
- Edit records directly.
- Review follow-up dates, overdue work, and enquiry outcomes.
- Manage property listings.
- Maintain oversight of the business workflow.

### 4.3 Staff

Staff must be able to:

- View all enquiries and customer records.
- Create enquiries manually.
- Handle enquiries without claiming or assigning them.
- Update enquiry statuses according to business rules.
- Record completed follow-up dates.
- Schedule future follow-ups.
- Propose edits to existing enquiries.
- Request deletion of enquiries.
- Add, edit, and remove property listings subject to the agreed approval workflow for records.

Staff must not bypass manager approval when editing or requesting deletion of existing enquiries.

### 4.4 No Enquiry Assignment System

**Do not implement an enquiry claiming or assignment workflow.**

All staff can see all enquiries.

Each enquiry has a lightweight `handled_by` field identifying the staff member currently handling it.

This field is for visibility and accountability only. It must not restrict enquiry visibility or behave like an assignment.

Staff may change who is handling an enquiry if permitted by the finalized business rules. Do not implement automatic ownership transfers.

The manager can oversee all enquiries and their handlers.

---

## 5. Core Data Model Principles

Implement models incrementally as each phase requires them.

Potential core entities include:

- User
- Customer
- Enquiry
- FollowUp
- ChangeRequest
- Property
- AuditEvent, if required by the approved audit design

Do not create every model at the beginning simply because it appears in this list.

### 5.1 Customers and Enquiries

A customer and an enquiry are not the same entity.

- A customer represents a person or business contact.
- An enquiry represents a specific request for a service.
- One customer can have multiple enquiries.
- Each enquiry has its own service type, status, handler, follow-up history, and outcome.
- A customer's enquiries must be tracked independently.

Example:

A customer enquires about a property and later asks about a home loan. These must be two distinct enquiries linked to the same customer.

Closing one enquiry must not automatically close the customer's other enquiries.

Avoid creating duplicate customer records when a new enquiry comes from an existing customer. Use an appropriate identification or matching workflow; do not assume that a matching name alone proves two records represent the same person.

### 5.2 Unified Enquiry Records

Website-generated enquiries and manually created enquiries must use the same underlying enquiry model.

Record an appropriate source, such as:

- Website
- Phone call
- Referral
- Walk-in
- Other, when needed

The service type must identify the kind of service requested, initially including:

- Real Estate
- Finance/Loans

Keep the service type extensible.

The property-specific fields and full service catalog will be finalized later. Do not hardcode a detailed property schema before the user approves it.

### 5.3 Historical Integrity

Do not permanently erase related customer, property, or enquiry history through cascading deletion unless explicitly approved.

A property removed from the public website must not automatically erase historical enquiries or property information needed by the business.

Use appropriate relationships, validation, and retention behavior.

The enquiry deletion approval workflow must be designed deliberately. Do not implement hard deletion as an unprotected shortcut.

---

## 6. Enquiry Lifecycle

The initial lifecycle consists of:

1. `New`
2. `Attended`
3. `Follow-ups`
4. A final outcome:
   - `Closed`
   - `Open`
   - `Lost`

The API should validate allowed status transitions rather than accepting arbitrary status strings.

### 6.1 New

An enquiry has been received but has not yet been marked as attended.

Website leads must appear in the dashboard immediately without manager approval.

Manual enquiries created by staff or the manager must also enter the same workflow without a separate approval requirement for creation.

### 6.2 Attended

Staff have contacted the customer and started handling the enquiry.

Staff manually change the status from `New` to `Attended`.

Do not implement an automatic `Start Handling` action that changes the status or handler.

### 6.3 Follow-ups

The follow-up stage supports tracking customer contact attempts without requiring detailed call logs.

Record:

- Completed follow-up dates.
- Follow-up count, derived from or kept consistent with completed follow-up records.
- Next scheduled follow-up date.
- Relevant timestamps.

The business considers two follow-ups a useful minimum before classifying an unresolved enquiry as Open or Lost. This is a guideline for staff, **not a mandatory system restriction**.

Do not block status changes solely because fewer than two follow-ups have been recorded.

### 6.4 Closed

Use `Closed` when the customer's requirement has been fulfilled, such as securing the desired property or obtaining the intended loan.

Staff can close an enquiry as soon as the requirement is fulfilled. Two follow-ups are not required.

### 6.5 Open

Use `Open` when the customer's current requirement has not been fulfilled but they may be contacted about future offers.

Staff can decide the outcome based on the actual customer situation. Do not force unnecessary follow-ups.

### 6.6 Lost

Use `Lost` when the enquiry should no longer be pursued.

If the customer explicitly refuses further calls or requests not to be contacted, staff must be able to mark the enquiry Lost immediately.

Respect the do-not-contact request and ensure it is not overridden by routine follow-up scheduling or promotional workflows.

Record an appropriate reason or contact restriction when needed to preserve this instruction.

### 6.7 Customer Outcome Views

The dashboard will provide separate views for:

- Closed Customers
- Open Customers
- Lost Customers

These views must not create duplicate customer or enquiry records.

Keep the underlying customer and enquiry entities intact, and build views from their stored outcomes.

Because one customer can have multiple enquiries with different outcomes, do not classify all of a customer's enquiries based on a single enquiry's outcome.

The exact display and filtering rules for these views can be finalized during implementation.

---

## 7. Follow-up Scheduling and Reminders

Follow-ups are a key operational feature.

### 7.1 Completed Follow-ups

Store completed follow-up dates so staff can track their own activity.

No mandatory call transcripts, extensive notes, or detailed call logs are required.

Do not invent a complex activity-management system.

### 7.2 Next Follow-up

Staff can schedule the next follow-up date for an enquiry.

The backend must support querying follow-ups that are:

- Due today
- Upcoming
- Overdue

The dashboard will have a dedicated Follow-ups section and also display follow-up information inside individual enquiries.

### 7.3 Reminder Behavior

The initial implementation can calculate due and overdue status from the stored next-follow-up date.

Do not introduce a background worker or external notification service unless the user later requests notifications that require it.

Use consistent date and timezone handling. Confirm the intended business timezone if it becomes necessary for correct date boundaries.

### 7.4 Finalized Enquiries

Do not continue showing completed enquiries as actionable follow-ups.

When an enquiry becomes Lost, Closed, or Open, apply the finalized scheduling rules so inappropriate reminders are not generated.

In particular, do not schedule calls after a do-not-contact request.

---

## 8. Edit and Deletion Approval Workflow

Existing enquiry edits and deletions require a manager approval workflow.

### 8.1 Staff Edit Requests

Staff cannot directly overwrite an existing enquiry's protected data.

Instead:

1. Staff submit a proposed change.
2. The backend validates the proposed values.
3. The request is stored as pending.
4. The original enquiry remains unchanged.
5. The manager reviews the proposed change.
6. The manager approves or rejects it.
7. The backend records the decision and applies the approved change.

A pending change must not affect the active enquiry until approval.

If the enquiry changes after a request is submitted, protect against stale approvals. Use a version number, timestamp check, or another suitable concurrency-control mechanism.

Do not silently overwrite newer data with an old proposed change.

### 8.2 Manager Decisions

The manager can:

- View pending edit requests.
- Review the original and proposed values.
- Approve a request.
- Reject a request.
- See who submitted it and when.
- See the decision and decision timestamp.

Only authorized users may perform these operations.

### 8.3 Staff Deletion Requests

Staff must submit a deletion request instead of directly deleting an enquiry.

The request should include a reason.

While deletion is pending:

- The enquiry remains active.
- Existing data remains available.
- The request is visible to the manager.

The manager can approve or reject the request.

If rejected, the enquiry remains active.

If approved, the manager must confirm the deletion before the operation proceeds.

Preserve an appropriate audit record of the request and decision. Determine the final retention strategy before implementing irreversible physical deletion.

### 8.4 Manager Direct Edits

The manager can edit existing enquiries directly without submitting an approval request.

The backend must still validate the data and enforce authorization.

Record relevant privileged changes in an audit trail where appropriate.

### 8.5 Approval Workflow Scope

The initial approval workflow applies to edits and deletions of existing enquiries.

Do not automatically apply the same workflow to customer creation, follow-up logging, routine status changes, or property management unless the user approves those additional requirements.

---

## 9. Property Management

Property management is required, but detailed property fields are intentionally postponed until the client requirements are clearer.

The business requires the ability to:

- Add property listings.
- Edit property listings.
- Remove listings from the public website.
- Upload and manage property photos.
- Reflect listing changes on the public website.

Both staff and the manager can manage property listings.

### Important constraints

- Do not finalize all property fields in the initial backend phase.
- Do not assume every listing has the same attributes.
- Do not automatically apply the enquiry approval workflow to properties.
- Removing a listing from the website must not automatically erase historical enquiries linked to it.
- Decide whether listing removal means unpublishing, archiving, or permanent deletion only after clarifying the requirement.
- Ask before selecting a paid image-storage provider or other external service.

Property management should be implemented in its own approved phase after the foundational CRM workflows.

---

## 10. Public Website Integration

The public website will submit customer enquiries to the backend.

Website leads must:

- Be accepted through an appropriate public API endpoint.
- Be validated on the server.
- Enter the unified enquiry system immediately.
- Be marked with source `Website`.
- Include the submitted service type.
- Appear in the dashboard without manager approval.

### Security Requirements

Public endpoints must not expose internal customer data or staff-only functionality.

- Validate all incoming data.
- Apply sensible rate limiting where appropriate.
- Avoid exposing database errors or stack traces.
- Prevent unauthorized access to staff endpoints.
- Restrict sensitive data returned by API responses.
- Keep secrets and credentials out of source control.

The public website must never receive administrative privileges simply because it can create enquiries.

The exact contact form fields and validation rules should be finalized against the existing frontend rather than invented in advance.

---

## 11. Authentication and Authorization

The dashboard requires authenticated staff access.

Before implementing authentication, inspect the existing frontend and ask the user to approve the authentication approach.

Required principles:

- Store passwords using a suitable secure password-hashing algorithm if password authentication is selected.
- Never store plaintext passwords.
- Protect privileged endpoints with server-side authorization.
- Never rely exclusively on frontend role checks.
- Prevent staff from approving their own requests if the final approval policy requires separation of duties.
- Validate all identifiers and ownership-related relationships.
- Keep credentials, signing keys, and database passwords in environment configuration.

Do not assume that hiding a button in the frontend is sufficient protection.

Do not implement public staff registration unless explicitly requested.

---

## 12. API Design Principles

Use predictable, versionable, documented APIs.

Where appropriate:

- Use REST conventions.
- Separate request and response schemas.
- Validate input with Pydantic.
- Return consistent HTTP status codes.
- Provide useful validation errors without leaking internals.
- Implement pagination for potentially large enquiry lists.
- Support filtering by status, service type, source, handler, and follow-up date when relevant.
- Avoid returning unrestricted database model objects directly.
- Keep public website endpoints separate from authenticated dashboard operations.

API names and response formats must remain aligned with the existing frontend.

Do not generate endpoints for every imaginable future feature. Implement endpoints as required by the current approved phase.

---

## 13. Data Integrity and Reliability

The backend must preserve reliable business records.

Required principles:

- Use database constraints where appropriate.
- Use transactions for operations that must succeed or fail together.
- Prevent duplicate approval processing.
- Ensure concurrent updates cannot silently overwrite one another.
- Keep customer-to-enquiry relationships consistent.
- Ensure follow-up counts and dates remain accurate.
- Prevent unauthorized status transitions.
- Prevent unauthorized edit and deletion approvals.
- Keep important timestamps consistent.
- Preserve relevant historical records.

If a public lead is submitted more than once due to a network retry, consider an idempotency mechanism when its behavior and requirements are clear. Do not deduplicate legitimate separate enquiries merely because they share a phone number.

---

## 14. Testing Requirements

Write tests incrementally alongside the features introduced in each phase.

Prioritize tests for:

- Valid and invalid enquiry creation.
- Website leads appearing without approval.
- Staff and manager permissions.
- Customer-to-enquiry relationships.
- Independent outcomes for multiple enquiries belonging to one customer.
- Follow-up scheduling and due-date calculations.
- Early outcome decisions without mandatory follow-ups.
- Do-not-contact behavior.
- Edit requests leaving original data unchanged while pending.
- Approval and rejection behavior.
- Deletion requests remaining pending until manager approval.
- Invalid or unauthorized status transitions.
- Concurrent modifications and duplicate approval attempts.
- Property history preservation when a listing is removed from publication.

Do not postpone all testing until the entire backend is complete.

Tests should reflect approved requirements, not speculative future features.

---

## 15. Development Phases

Use this sequence as the proposed plan. Review it after inspecting the repository.

### Phase 0 — Repository Audit and Backend Plan

Tasks:

- Inspect the existing repository.
- Identify frontend API expectations.
- Determine whether backend code already exists.
- Recommend the initial folder structure.
- Identify important unanswered technical decisions.
- Propose a phased implementation plan.

Deliverable: a concise audit and implementation proposal.

**Do not build the backend during this phase. Ask the user to approve the plan.**

### Phase 1 — Backend Foundation

After approval:

- Set up the minimal FastAPI application.
- Configure environment settings.
- Establish the approved database connection.
- Add health-check and basic application configuration.
- Establish the testing setup.
- Confirm the application starts successfully.

Do not implement the entire CRM in this phase.

At completion, run the appropriate checks and request approval before Phase 2.

### Phase 2 — Authentication and Roles

After approval:

- Implement the agreed authentication approach.
- Add the approved roles and authorization rules.
- Establish protected dashboard endpoints.
- Test access restrictions.

Do not implement all business features at the same time.

### Phase 3 — Customers and Enquiries

After approval:

- Implement customer and enquiry models.
- Support multiple enquiries per customer.
- Add unified manual enquiry creation.
- Implement website enquiry intake.
- Add service type and source fields.
- Implement the agreed status lifecycle.
- Add enquiry filtering and pagination as needed.
- Add the `Handled By` field without an assignment workflow.

Test the main enquiry lifecycle before proceeding.

### Phase 4 — Follow-ups and Reminders

After approval:

- Add completed follow-up dates.
- Add next-follow-up scheduling.
- Implement due-today, upcoming, and overdue queries.
- Integrate follow-up data with enquiry records.
- Prevent inappropriate reminders for finalized or do-not-contact enquiries.

### Phase 5 — Manager Approval Workflows

After approval:

- Implement staff edit requests.
- Implement manager review and decisions.
- Implement staff deletion requests.
- Implement manager-approved deletion.
- Add concurrency safeguards.
- Preserve an appropriate approval history.

### Phase 6 — Property Management

After approval:

- Finalize property fields with the user.
- Implement listing creation and editing.
- Implement publication and removal behavior.
- Add photo management according to the approved storage strategy.
- Preserve historical relationships.

### Phase 7 — Dashboard Integration and Reporting

After approval:

- Align APIs with the existing frontend.
- Implement the Closed, Open, and Lost views.
- Ensure customer and enquiry records are not duplicated.
- Add appropriate dashboard summaries.
- Validate end-to-end business workflows.

### Phase 8 — Hardening and Deployment Preparation

After approval:

- Review security and authorization.
- Verify migrations and configuration.
- Expand tests where necessary.
- Review logging and error handling.
- Prepare deployment documentation.
- Document backup and recovery considerations.
- Verify the application can be configured outside the development environment.

Do not deploy, migrate production data, or perform destructive operations without explicit authorization.

---

## 16. Required End-of-Phase Report

At the end of every approved phase, provide a concise report containing:

1. **Completed:** What was implemented.
2. **Files changed:** New, modified, or deleted files.
3. **Dependencies:** What was added and why.
4. **Verification:** Tests and checks performed, with actual results.
5. **Business rules:** Any relevant decisions or assumptions.
6. **Outstanding issues:** Anything incomplete or blocked.
7. **Next phase:** What is proposed next.

Then ask the user for approval before starting the next phase.

If a phase is incomplete, state that clearly and finish or resolve the agreed scope before requesting progression.

---

## 17. Scope Control and Future Requirements

Some business requirements are intentionally undecided.

Examples include:

- Detailed property fields.
- Exact finance-service categories.
- The full administrator-versus-manager permission distinction.
- Customer matching and merging rules.
- Final data-retention and deletion policies.
- Exact authentication and deployment choices.
- Future reporting and integrations.

Do not invent final answers for these requirements.

When an undecided requirement becomes necessary, explain why it matters and ask one focused question.

Do not delay unrelated approved work because a future feature remains undecided.

---

## 18. Instructions for the Coding Agent

You are an implementation agent, not an autonomous product decision-maker.

Your priorities, in order, are:

1. Follow the user's explicit instructions.
2. Preserve the established business rules in this document.
3. Inspect and respect the existing repository.
4. Implement only the currently approved phase.
5. Maintain security and data integrity.
6. Test the changes.
7. Explain the result and ask before progressing.

**At the start of work, determine the current phase and whether it has already been approved.**

If the repository has not been audited, start with Phase 0.

If the current phase has not been approved, present its proposed scope and wait.

Never treat the existence of this file as blanket permission to implement every phase.

The goal is a practical, secure, maintainable backend that supports the client's real workflow and evolves as requirements become clearer—not a large, overengineered system built on assumptions.
