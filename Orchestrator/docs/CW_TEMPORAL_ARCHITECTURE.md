# Collegewise — Temporal Workflow Architecture

## Overview

Migrate Collegewise's recurring payment processing and notification system
from synchronous cron-driven execution to **Temporal** durable workflow
orchestration. The goal: eliminate double-charges, gain automatic retries with
idempotency, and have full auditability of every payment workflow execution.

**ClickUp Tickets:**
- [Add Recurring charges to Queue](https://app.clickup.com/t/868hdtbvr) — `868hdtbvr`
- [Investigate SMTP Server Timeout | Add email queue](https://app.clickup.com/t/868d1drz4) — `868d1drz4`

---

## Architecture

```
┌──────────────┐     trigger      ┌──────────────────┐
│ Magento Cron │ ───────────────► │  Temporal Server  │
│  (existing)  │                  │  (orchestrator)   │
└──────────────┘                  └────────┬─────────┘
                                           │
                                    schedules workflows
                                           │
                                  ┌────────▼─────────┐
                                  │  Temporal Worker  │
                                  │  (thin orchestrator) │
                                  └────────┬─────────┘
                                           │
                              ┌────────────┼────────────┐
                              │                         │
                     ┌────────▼────────┐     ┌──────────▼──────────┐
                     │ Magento Charge  │     │ Magento Notification │
                     │    Endpoint     │     │      Endpoint        │
                     │ (Authorize.net) │     │  (templates + SMTP)  │
                     └────────┬────────┘     └──────────┬──────────┘
                              │                         │
                       ┌──────▼──────┐           ┌──────▼──────┐
                       │  MySQL      │           │  SMTP       │
                       │  (Magento)  │           │  (Magento)  │
                       └─────────────┘           └─────────────┘
```

The Temporal worker is a **thin orchestrator**. It decides *when* and *whether*
to act. Magento handles all downstream execution: payment processing
(Authorize.net), notification rendering (templates), and email delivery (SMTP).

---

## Core Workflow: `RecurringPaymentCycle`

One durable workflow per payment plan per billing cycle. Manages the full
timeline from reminders through charge through receipt — emails and charges
can never be misaligned because they're sequential steps in one execution.

```
Workflow: RecurringPaymentCycle(paymentPlanId, chargeDate)
│
├─ Activity: DetermineEligibility
│   └─ Query payment_plans table, check status + next_payment_date
│
├─ Reminder Phase (configurable: default 7, 3, 1 days before)
│   ├─ sleep until reminder date (Temporal durable timer)
│   ├─ Re-verify plan still active
│   └─ Activity: SendNotification(type: "payment_reminder")
│       └─ POST to Magento notification API — Magento renders template + sends
│
├─ sleep until charge date
│
├─ Charge Phase (with configurable retry schedule: default +1d, +3d, +5d)
│   ├─ Activity: ExecuteCharge
│   │   └─ POST to Magento's charge endpoint
│   │   └─ Magento handles Authorize.net — system of record
│   │   └─ Idempotency key via X-Idempotency-Key header
│   │
│   ├─ On success:
│   │   ├─ Activity: RecordResult
│   │   └─ Activity: SendNotification(type: "payment_receipt")
│   │
│   └─ On failure:
│       ├─ Activity: RecordResult (failure)
│       ├─ Activity: SendNotification(type: "payment_failed_retry")
│       └─ sleep until next retry date → loop
│
├─ All retries exhausted:
│   └─ Activity: SendNotification(type: "payment_failed_final")
│
└─ Workflow completes — full history visible in Temporal UI

Signals:
  cancelCycle          → abort the workflow at any point
  paymentMethodUpdated → note that customer updated card mid-cycle
```

### Default Schedule

| Event | Timing |
|---|---|
| Reminder notifications | 7, 3, 1 days before charge |
| Charge attempt | On charge date |
| Retry 1 | +1 day after charge date |
| Retry 2 | +3 days after charge date |
| Retry 3 | +5 days after charge date |
| Final failure notification | After all retries exhausted |

All intervals are configurable per workflow invocation.

---

## Responsibility Boundary

| Layer | Responsibility |
|---|---|
| **Temporal Worker** | Orchestration: eligibility, scheduling, retries, deciding *what* to notify |
| **Magento** | Everything else: payment processing (Authorize.net), notifications (templates + SMTP), system of record |
| **Temporal Server** | Durability: workflow state, replay, event history |

### Magento Endpoints Required

The worker calls two Magento REST API endpoints:

| Endpoint | Purpose |
|---|---|
| `POST /rest/V1/collegewise/payment-plans/{id}/charge` | Process a charge. Magento calls Authorize.net, returns transaction result. Accepts `X-Idempotency-Key` header to reject duplicates. |
| `POST /rest/V1/collegewise/notifications` | Send a typed notification. Magento maps the notification type to a template and handles rendering + SMTP delivery. |

### Notification Types

| Type | When sent | Template data |
|---|---|---|
| `payment_reminder` | 7, 3, 1 days before charge | `customer_name`, `amount`, `currency`, `charge_date`, `days_before` |
| `payment_receipt` | After successful charge | `customer_name`, `amount`, `currency`, `transaction_id`, `charge_date` |
| `payment_failed_retry` | After failed charge (more retries left) | `customer_name`, `amount`, `currency`, `charge_date`, `error`, `next_retry_days`, `attempt_number` |
| `payment_failed_final` | After all retries exhausted | `customer_name`, `amount`, `currency`, `charge_date`, `error`, `total_attempts` |

Marketing can update email copy and templates in Magento admin without
redeploying the worker.

---

## Magento Requirements

Everything below needs to be built in the Magento repo (`collegewise1/cw-magento`)
before the Temporal integration goes live. The worker is ready; Magento is the
blocker.

### 1. Custom Module: `Collegewise_PaymentWorkflow`

A new Magento 2 module to house the API endpoints, idempotency logic, and
notification dispatch.

```
app/code/Collegewise/PaymentWorkflow/
├── registration.php
├── etc/
│   ├── module.xml
│   ├── di.xml
│   ├── webapi.xml                    ← REST route definitions
│   └── email_templates.xml           ← template registration
├── Api/
│   ├── ChargeManagementInterface.php
│   └── NotificationManagementInterface.php
├── Model/
│   ├── ChargeManagement.php          ← charge endpoint logic
│   ├── NotificationManagement.php    ← notification endpoint logic
│   └── IdempotencyLog.php            ← idempotency key storage
├── Setup/
│   └── db_schema.xml                 ← new tables
└── view/
    └── frontend/
        └── email/                    ← 4 notification templates
```

### 2. REST API: Charge Endpoint

**Route:** `POST /rest/V1/collegewise/payment-plans/:id/charge`

**`webapi.xml`:**
```xml
<route url="/V1/collegewise/payment-plans/:id/charge" method="POST">
    <service class="Collegewise\PaymentWorkflow\Api\ChargeManagementInterface"
             method="execute"/>
    <resources>
        <resource ref="Collegewise_PaymentWorkflow::charge"/>
    </resources>
</route>
```

**Request:**
```json
{
    "chargeDate": "2026-04-01",
    "idempotencyKey": "abc123..."
}
```
Plus header: `X-Idempotency-Key: abc123...`

**Response (success):**
```json
{
    "success": true,
    "transaction_id": "txn_12345",
    "auth_code": "AUTH01",
    "amount": 299.00
}
```

**Response (failure — card declined):**
```json
{
    "success": false,
    "error_code": "card_declined",
    "error_message": "Insufficient funds",
    "amount": 299.00
}
```

**Implementation notes:**
- Look up the payment plan by `id`, load the stored Authorize.net payment profile
- Call Authorize.net `createTransactionRequest` (Customer Profile Transaction)
- **Before processing**: check `idempotency_log` table for the key. If found,
  return the stored result instead of charging again
- **After processing**: insert the key + result into `idempotency_log`
- Return the full result for the worker to record

### 3. REST API: Notification Endpoint

**Route:** `POST /rest/V1/collegewise/notifications`

**`webapi.xml`:**
```xml
<route url="/V1/collegewise/notifications" method="POST">
    <service class="Collegewise\PaymentWorkflow\Api\NotificationManagementInterface"
             method="send"/>
    <resources>
        <resource ref="Collegewise_PaymentWorkflow::notification"/>
    </resources>
</route>
```

**Request:**
```json
{
    "type": "payment_reminder",
    "payment_plan_id": 42,
    "order_id": 1001,
    "customer_id": 55,
    "customer_email": "jane@example.com",
    "data": {
        "customer_name": "Jane Doe",
        "amount": "299.00",
        "currency": "USD",
        "charge_date": "2026-04-01",
        "days_before": 7
    }
}
```

**Response:**
```json
{
    "success": true,
    "notification_id": "ntf_67890"
}
```

**Implementation notes:**
- Map `type` to a Magento transactional email template ID
- Load the customer, populate template variables from `data`
- Send via Magento's `TransportBuilder` (uses the store's configured SMTP)
- Log the notification in a `notification_log` table for audit

### 4. Database Schema Changes (`db_schema.xml`)

**New table: `collegewise_idempotency_log`**

| Column | Type | Notes |
|---|---|---|
| `id` | int (PK, auto) | |
| `idempotency_key` | varchar(128), unique | SHA-256 hash from worker |
| `payment_plan_id` | int | FK to `payment_plans` |
| `charge_date` | date | |
| `result_json` | text | Full charge response stored as JSON |
| `created_at` | timestamp | |

When the charge endpoint receives a request, it first queries this table.
If a row exists for the key, it returns `result_json` without calling
Authorize.net again. This is the server-side double-charge guard.

**New table: `collegewise_notification_log`** (optional but recommended)

| Column | Type | Notes |
|---|---|---|
| `id` | int (PK, auto) | |
| `notification_id` | varchar(64), unique | Returned to worker |
| `type` | varchar(32) | e.g. `payment_reminder` |
| `payment_plan_id` | int | |
| `customer_id` | int | |
| `customer_email` | varchar(255) | |
| `data_json` | text | Template data snapshot |
| `sent_at` | timestamp | |
| `status` | varchar(16) | `sent`, `failed` |
| `error` | text, nullable | SMTP error if failed |

**Existing table: `payment_plans`** — verify schema matches what the worker queries:

| Column | Type | Worker expects |
|---|---|---|
| `id` | int (PK) | `WHERE id = ?` |
| `order_id` | int | Read |
| `customer_id` | int | Read |
| `customer_email` | varchar | Read |
| `customer_name` | varchar | Read |
| `amount` | decimal | Read |
| `currency` | varchar (default `USD`) | Read |
| `frequency` | enum(`monthly`, `quarterly`, `annual`) | Read + used to advance date |
| `next_payment_date` | date | `WHERE next_payment_date <= ?`, updated on success |
| `status` | enum(`active`, `paused`, `cancelled`, `completed`) | `WHERE status = 'active'` |

**Existing table: `payment_dates`** — verify schema matches what the worker inserts:

| Column | Type | Worker writes |
|---|---|---|
| `payment_plan_id` | int | Insert |
| `charge_date` | date | Insert (composite unique with plan ID) |
| `transaction_id` | varchar, nullable | Insert/update |
| `success` | tinyint | Insert/update |
| `amount` | decimal | Insert |
| `error_message` | text, nullable | Insert/update |
| `created_at` | timestamp | `NOW()` |

### 5. Email Templates (4 required)

Register in `email_templates.xml` and create HTML templates under
`view/frontend/email/`:

| Template ID | File | Subject line (example) |
|---|---|---|
| `collegewise_payment_reminder` | `payment_reminder.html` | "Your payment of {{var amount}} is due on {{var charge_date}}" |
| `collegewise_payment_receipt` | `payment_receipt.html` | "Payment received — {{var amount}}" |
| `collegewise_payment_failed_retry` | `payment_failed_retry.html` | "Payment failed — we'll retry in {{var next_retry_days}} days" |
| `collegewise_payment_failed_final` | `payment_failed_final.html` | "Action required: payment failed after {{var total_attempts}} attempts" |

All templates should be editable from **Marketing > Email Templates** in
Magento admin so copy changes don't require a code deploy.

### 6. Magento Integration Token

Create a Magento 2 Integration (System > Integrations) for the Temporal worker:

- **Name:** `Temporal Worker`
- **Resource Access:** Custom — grant only:
  - `Collegewise_PaymentWorkflow::charge`
  - `Collegewise_PaymentWorkflow::notification`
- The generated token goes into `CW_MAGENTO_API_TOKEN` env var for the worker

### 7. Cron Trigger (Phase 2)

The existing Magento cron that processes recurring payments needs to be modified
to start Temporal workflows instead of charging directly:

**Before (current):**
```
cron runs → load eligible plans → call Authorize.net → send email → update DB
```

**After:**
```
cron runs → load eligible plans → for each plan, start RecurringPaymentCycle
            workflow via Temporal HTTP API or SDK → done (Temporal handles the rest)
```

The simplest approach is an HTTP call from PHP to start each workflow:
```
POST http://temporal-server:7233/api/v1/namespaces/collegewise/workflows
```

Or use the Temporal PHP SDK (`temporal/sdk`) if deeper integration is preferred.

### Magento Checklist

- [ ] Create `Collegewise_PaymentWorkflow` module skeleton
- [ ] Implement charge endpoint with Authorize.net CIM call
- [ ] Add `collegewise_idempotency_log` table and duplicate-key guard
- [ ] Implement notification endpoint with template dispatch
- [ ] Add `collegewise_notification_log` table
- [ ] Create 4 email templates (reminder, receipt, retry, final)
- [ ] Register templates in `email_templates.xml`
- [ ] Verify `payment_plans` and `payment_dates` table schemas match worker expectations
- [ ] Create Integration token with scoped ACL
- [ ] Test charge endpoint returns correct `ChargeResult` shape
- [ ] Test notification endpoint sends email and returns `NotificationResult` shape
- [ ] Test idempotency: second call with same key returns stored result, no duplicate charge
- [ ] (Phase 2) Modify cron to trigger Temporal workflows instead of charging directly

---

## Retry & Idempotency Strategy

| Concern | Approach |
|---|---|
| Double-charge prevention | Idempotency key = `sha256(charge:{plan_id}:{charge_date})` sent to Magento via `X-Idempotency-Key` header; Magento rejects duplicate charges |
| Charge retry (transient) | Temporal activity retry: 3 attempts, 30s/60s/120s backoff (gateway timeouts, 5xx errors) |
| Charge retry (business) | Workflow-level retry schedule: +1d, +3d, +5d (card declined, insufficient funds) with notification between each |
| Magento timeout | Activity timeout = 45s, Temporal replays from last successful activity |
| Notification failure | Separate activity with own timeout (20s) and retries; never blocks charge recording |
| Email/charge alignment | Both live in one workflow — reminders, charges, and receipts are sequential steps, never out of sync |
| Mid-cycle cancellation | `cancelCycle` signal aborts the workflow cleanly at the next checkpoint |
| Workflow visibility | Every step (each reminder, each charge attempt, each notification) recorded in Temporal event history |

---

## Service Topology

```
docker-compose.yml
│
├── magento-app          (existing — unchanged)
├── magento-cron         (existing — triggers workflows via Temporal SDK or HTTP)
├── temporal-server      (temporalio/auto-setup, single-node)
├── temporal-ui          (temporalio/ui)
├── temporal-worker      (custom: thin orchestrator calling Magento APIs)
├── temporal-mysql       (dedicated MySQL for Temporal persistence)
└── [optional] grafana + loki + promtail (observability)
```

### Why Temporal over basic queues

- **Durability**: workflows survive crashes — Temporal replays from last checkpoint
- **Idempotency**: built into the programming model, not bolted on
- **Visibility**: Temporal UI shows every workflow run, every activity, every retry
- **No double-charge risk**: a resumed workflow picks up exactly where it left off
- **Multi-day state**: durable timers handle the reminder → charge → retry timeline
- **Auditability**: full event history for compliance / debugging

---

## Phased Rollout

### Phase 1: Infrastructure + Standalone Notifications (low risk)

1. Stand up Temporal server + UI + worker in Docker Compose
2. Build the two Magento API endpoints (charge + notifications)
3. Deploy `sendNotificationWorkflow` — decouple ad-hoc notifications from Magento request cycle
4. Magento triggers notification workflows instead of sending inline
5. Resolves SMTP timeout issue (ticket `868d1drz4`)
6. **Validates the full stack before touching payments**

### Phase 2: Unified Payment Cycle (critical path)

1. Deploy `recurringPaymentCycle` workflow — reminders + charge + receipts in one workflow
2. Magento's charge endpoint receives idempotency key, Temporal orchestrates the schedule
3. Run in shadow mode: Temporal workflow executes alongside existing cron (dry run)
4. Compare results — ensure parity
5. Cut over: cron triggers Temporal payment cycles instead of charging directly
6. Resolves recurring charges ticket (`868hdtbvr`)

### Phase 3: Observability + Hardening

1. Add Grafana + Loki for centralized container logs
2. Set up Temporal workflow alerts (failed workflows → Slack/admin notification)
3. Dashboard integration: surface Temporal workflow status in Agent007 dashboard
4. Deprecate legacy cron charge logic and inline email sends
5. Configure Temporal retention policy for event history cleanup

---

## Tech Stack

| Component | Technology | Notes |
|---|---|---|
| Temporal Server | `temporalio/auto-setup:latest` | Single-node, Docker |
| Temporal UI | `temporalio/ui:latest` | Port 8080 |
| Temporal Worker | **TypeScript (Node.js)** | `@temporalio/worker` + `@temporalio/workflow` |
| Temporal Persistence | MySQL 8 (separate container) | Dedicated schema, not shared with Magento |
| Magento App | PHP / Magento 2 | System of record — owns charges, notifications, templates |
| Payment Gateway | Authorize.net | Called by Magento, not by the worker |
| Notifications | Magento notification API | Templates + SMTP owned by Magento; worker sends typed events |
| Infrastructure | Docker Compose on EC2 | EBS-backed volumes for persistence |
| Observability | Temporal UI + container logs | Optional: Grafana + Loki + Promtail |

### Why TypeScript for the Worker

- Temporal has first-class TypeScript SDK
- Closer to the existing Node.js tooling in the org
- Easier to maintain than a PHP Temporal worker
- Strong typing for payment/financial logic
- Calls Magento REST API for both charges and notifications — worker is a thin orchestrator

---

## File Structure

```
infra/collegewise-temporal/
├── docker-compose.yml
├── .env.example
├── README.md
├── temporal-worker/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vitest.config.ts
│   ├── Dockerfile
│   ├── src/
│   │   ├── worker.ts                    # Worker bootstrap
│   │   ├── client.ts                    # CLI client for triggering workflows
│   │   ├── workflows/
│   │   │   ├── index.ts                 # Workflow exports
│   │   │   ├── payment-cycle.ts         # RecurringPaymentCycle workflow
│   │   │   └── send-email.ts            # Standalone SendNotification workflow
│   │   ├── activities/
│   │   │   ├── index.ts                 # Activity exports
│   │   │   ├── payment.ts              # Magento charge endpoint call
│   │   │   ├── database.ts             # MySQL eligibility + result recording
│   │   │   └── notification.ts         # Magento notification endpoint call
│   │   └── shared/
│   │       ├── types.ts                 # PaymentPlan, ChargeResult, NotificationType, etc.
│   │       └── idempotency.ts           # Deterministic charge key generation
│   └── tests/
│       ├── idempotency.test.ts          # Idempotency key unit tests
│       ├── payment.test.ts              # Magento charge activity tests
│       ├── notification.test.ts         # Magento notification activity tests
│       ├── payment-cycle.test.ts        # Full payment cycle workflow tests
│       └── workflows.test.ts            # Standalone notification workflow tests
```

---

## Environment Variables

```env
# Temporal
TEMPORAL_ADDRESS=temporal-server:7233
TEMPORAL_NAMESPACE=collegewise
TEMPORAL_TASK_QUEUE=collegewise-payments

# MySQL (Magento — eligibility checks + result recording)
CW_MYSQL_HOST=...
CW_MYSQL_PORT=3306
CW_MYSQL_USER=...
CW_MYSQL_PASSWORD=...
CW_MYSQL_DATABASE=collegewise

# Magento REST API (charges + notifications — Magento owns everything downstream)
CW_MAGENTO_API_URL=https://collegewise.com
CW_MAGENTO_API_TOKEN=...
```

No SMTP credentials needed in the worker — Magento handles email delivery.

---

## Testing

Tests use **Vitest** for unit tests and **@temporalio/testing** (`TestWorkflowEnvironment`)
for workflow integration tests with mocked activities.

```bash
cd infra/collegewise-temporal/temporal-worker
npm install
npm test            # run all tests
npm run test:watch  # watch mode
```

### Test Coverage

| Test file | What it covers |
|---|---|
| `idempotency.test.ts` | Key determinism, uniqueness, format |
| `payment.test.ts` | Dry run, Magento endpoint call, error handling |
| `notification.test.ts` | Magento notification API call, payload structure, error handling |
| `payment-cycle.test.ts` | Full cycle: ineligible plan, success with reminders, retry on failure, all retries exhausted, notification failure doesn't block charge, mid-cycle cancellation |
| `workflows.test.ts` | Standalone notification workflow |
