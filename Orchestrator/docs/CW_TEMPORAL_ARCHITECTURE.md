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
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
          ┌─────────▼──────────┐ ┌─────────▼──────────┐ ┌────────▼─────────┐
          │ Cron Trigger API   │ │ Notification API   │ │ MySQL (read-only)│
          │ (existing)         │ │ (existing)         │ │ eligibility check│
          │ RecurringCharge    │ │ NotificationService│ │                  │
          │ → USAePay REST/SOAP│ │ → TransportBuilder │ │                  │
          └────────────────────┘ └────────────────────┘ └──────────────────┘
```

The Temporal worker is a **thin orchestrator**. It decides *when* and *whether*
to act. All charge execution, duplicate prevention, and email rendering stays
in the existing `ForgeLabs\RecurringCharge` module. The payment gateway is
**USAePay** (REST for CC tokens, SOAP for ACH/ePay-imported plans).

### Code Reuse from `ForgeLabs\RecurringCharge`

The Temporal worker does **not** reimplement charge or notification logic.
It calls the existing Magento REST APIs:

| What Temporal does | What Magento does (existing) |
|---|---|
| Decides it's time to charge | `RecurringCharge::execute()` — eligibility, USAePay call, atomic DB update, confirmation email |
| Decides it's time to retry | `RetryRecurringCharge::execute()` — reload payment date, validate, charge, handle response |
| Sends a notification | `NotificationService::send()` — template lookup, TransportBuilder, BCC finance team |
| Checks eligibility | Direct SQL read of `collegewise_payment_plan` + `collegewise_payment_dates` |

### Existing Magento APIs (already deployed)

| Endpoint | Class | Worker uses |
|---|---|---|
| `POST /V1/recurring-charge/cron/trigger/recurring-charge` | `CronManagerInterface::triggerRecurringCharge` | Trigger charge |
| `POST /V1/recurring-charge/cron/trigger/retry-charge` | `CronManagerInterface::triggerRetryCharge` | Trigger retry |
| `POST /V1/recurring-charge/send-notification` | `NotificationInterface::send` | Send emails |
| `GET /V1/recurring-charge/cron/preview/recurring-charge` | `CronManagerInterface::previewRecurringCharge` | Shadow mode comparison |
| `GET /V1/recurring-charge/payment-plan/:id` | `PaymentPlanManagerInterface::getPaymentPlan` | Plan details |

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
| **Temporal Worker** | Orchestration: eligibility reads, scheduling, retry timing, notification sequencing |
| **ForgeLabs\RecurringCharge** | Everything else: USAePay charges, duplicate prevention, atomic DB updates, email rendering, plan management |
| **Temporal Server** | Durability: workflow state, replay, event history |

### Existing Notification Types (in NotificationService)

| Type | When sent | Notes |
|---|---|---|
| `initial_failure` | Immediately after charge failure | Uses configurable template ID, BCC finance team |
| `reminder_5day` | 5 days after failure | Template ID `5`, includes card update link |
| `reminder_16day` | 16 days after failure | Template ID `3`, includes card update link |
| `update_card` | On demand | Sends card update email with tokenized link |

### Existing Email Templates

| Template | File | Module |
|---|---|---|
| Payment confirmation | `payment_confirmation.html` | `ForgeLabs_RecurringCharge` |
| Duplicate payment alert | `duplicate_payment_notification.html` | `ForgeLabs_RecurringCharge` |
| Upcoming charge | `upcomming_charge.html` | `Mangoit_ChargeNotification` |
| Expired card (admin) | `expiredcc.html` | `Mangoit_ExpiredCreditCardEmails` |

Marketing can update email copy in **Marketing > Email Templates** in Magento admin.

---

## Existing Magento Module: `ForgeLabs\RecurringCharge`

The Temporal integration reuses the existing module — **no new Magento module is needed**.
The charge, retry, notification, and duplicate-prevention logic already exists.

### What Already Exists (no changes needed)

| Component | Location | Notes |
|---|---|---|
| Charge execution | `Cron/RecurringCharge.php` | USAePay REST (CC) + SOAP (ACH/ePay) |
| Retry logic | `Cron/RetryRecurringCharge.php` | Configurable intervals, max attempts, plan suspension |
| Notification API | `Model/NotificationService.php` | `initial_failure`, `reminder_5day`, `reminder_16day`, `update_card` |
| Cron trigger API | `Model/CronManager.php` | `POST /V1/recurring-charge/cron/trigger/*` |
| Cron preview API | `Model/CronManager.php` | `GET /V1/recurring-charge/cron/preview/*` |
| Duplicate prevention | `Helper/RecurringChargeHelper.php` | `isDuplicateTransaction()`, `checkEpayForDuplicateCharge()`, advisory locks |
| Atomic DB updates | `Cron/RecurringCharge.php` | `FOR UPDATE` row locking, transaction isolation |
| Email templates | `view/frontend/email/` | `payment_confirmation.html`, `duplicate_payment_notification.html` |
| Activity log | `Api/ActivityLogInterface.php` | Full audit trail of all charge/plan actions |
| Diagnostics API | `Api/DiagnosticsInterface.php` | Unpaid by date, balance mismatch, missed charges |

### Database Tables (already deployed)

**`collegewise_payment_plan`** (via `Mangoit/PaymentMethod` + `ForgeLabs/RecurringCharge` extensions):

| Column | Type | Used by worker |
|---|---|---|
| `id` | int (PK) | Eligibility lookup |
| `order_id` | int | Read |
| `customer_id` | int | Read |
| `customer_email` | varchar | Read |
| `customer_name` | varchar | Read |
| `amount_of_additional_payment` | decimal | Charge amount |
| `number_of_additional_payment` | int | Installments remaining |
| `next_payment_date` | date | Eligibility filter |
| `plan_status` | varchar | Must not be suspended/expired/canceled |
| `recurring_mage_managed` | boolean | Must be 1 |
| `payment_method_type` | varchar | `cc` or `ach` |
| `customer_cc_token` | varchar | Used by charge logic (not worker) |
| `amount_captured` | decimal | Read for validation |
| `amount_outstanding` | decimal | Read for validation |

**`collegewise_payment_dates`** (via `Mangoit/ChargeNotification` + `ForgeLabs/RecurringCharge` extensions):

| Column | Type | Used by worker |
|---|---|---|
| `entity_id` | int (PK) | Row identifier |
| `payment_plan_id` | int | FK to payment plan |
| `charge_date` | date | Eligibility filter |
| `amount_due` | decimal | Amount to charge |
| `amount_charged` | decimal | Running total |
| `payment_status` | varchar | `UNPAID`, `PARTIALLY_PAID`, `PAID` |
| `retry_count` | int | Retry tracking |
| `failed_at` | date | Last failure date |
| `failure_reason` | text | Error details |
| `last_retry` | timestamp | Last retry date |
| `five_days_email_sent` | smallint | Notification tracking |
| `sixteen_days_email_sent` | smallint | Notification tracking |
| `upcoming_charge_email_sent` | smallint | Notification tracking |
| `failed_payment_email_sent` | smallint | Notification tracking |

### What's New (minimal Magento-side work)

| Item | Effort | Notes |
|---|---|---|
| Integration token for Temporal worker | 5 min | System > Integrations > new token scoped to `Mangoit_Collegewise::index` |
| (Optional) Per-plan charge API | Medium | Extract single-plan charge from `RecurringCharge::execute()` into a new API route. Current workaround: trigger cron which processes all eligible plans. |
| (Optional) `collegewise_idempotency_log` table | Low | Additional server-side idempotency layer. Current duplicate prevention via `isDuplicateTransaction()` is already effective. |

### Magento Checklist

- [ ] Create Integration token for Temporal worker (scoped ACL)
- [ ] Test cron trigger API returns expected response shape
- [ ] Test notification API for each type (`initial_failure`, `reminder_5day`, `reminder_16day`, `update_card`)
- [ ] (Phase 2) Add per-plan charge endpoint to allow Temporal to charge a single plan
- [ ] (Phase 2) Disable charge/retry crons once Temporal is orchestrating
- [ ] (Optional) Add `collegewise_idempotency_log` table for Temporal's idempotency keys

### Data Migration

**No data migration is needed.** The existing tables (`collegewise_payment_plan`,
`collegewise_payment_dates`, `collegewise_recurring_charge_log`) are used as-is.
The Temporal worker reads them for eligibility and calls existing APIs for
all mutations. The worker's `database.ts` queries have been aligned with the
actual schema.

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

### Phase 1: Infrastructure + Shadow Mode (low risk)

1. Stand up Temporal server + UI + worker in Docker Compose
2. Create Magento Integration token for the worker
3. Deploy `recurringPaymentCycle` workflow in **dry-run mode**
4. Temporal runs alongside existing crons — compares results, charges nothing
5. Use existing `preview` APIs to validate Temporal's eligibility decisions match cron's
6. **Validates the full stack without touching production charges**

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
| Payment Gateway | USAePay (REST + SOAP) | Called by Magento `RecurringCharge`, not by the worker |
| Notifications | Existing `NotificationService` API | Templates + SMTP owned by Magento; worker calls existing endpoint |
| Infrastructure | Docker Compose on EC2 | EBS-backed volumes for persistence |
| Observability | Temporal UI + container logs | Optional: Grafana + Loki + Promtail |

### Why TypeScript for the Worker

- Temporal has first-class TypeScript SDK
- Closer to the existing Node.js tooling in the org
- Easier to maintain than a PHP Temporal worker
- Strong typing for payment/financial logic
- Calls existing Magento REST APIs — worker is a thin orchestrator

---

## Backwards Compatibility

The existing cron jobs continue to work unchanged during the transition.
Temporal adds orchestration *around* the same charge/notification logic.

### Existing Crons (from `crontab.xml`)

| Cron | Schedule | Temporal replaces? |
|---|---|---|
| `collegewise_recurring_charge` | 5:00 AM daily | Phase 2: Temporal triggers instead |
| `collegewise_retry_recurring_charge` | 5:00 AM daily | Phase 2: Temporal handles retry schedule |
| `collegewise_failed_payments_notifications` | Every 10 min | Phase 2: Temporal sends failure notifications |
| `collegewise_upcoming_charge_notifications` | 8:00 AM daily | Phase 2: Temporal sends reminders |
| `collegewise_expired_cc_notifications` | 8:00 AM daily | **Keeps running** (outside scope) |
| `collegewise_expiring_cc_notifications` | 8:00 AM daily | **Keeps running** (outside scope) |

### Cutover Plan

**Phase 1 (shadow):** Both crons and Temporal run. Temporal is in dry-run mode.
No production impact.

**Phase 2 (cutover):** Comment out charge/retry/notification crons in `crontab.xml`.
Temporal workflows take over orchestration but still call the same underlying
`RecurringCharge::execute()` and `NotificationService::send()` logic.

**Rollback:** Uncomment crons in `crontab.xml`. Temporal workflows can be
terminated via Temporal UI. No data migration to revert.

---

## Data Migration

**No data migration is needed.**

- The worker reads `collegewise_payment_plan` and `collegewise_payment_dates` as-is
- All mutations go through existing Magento APIs which update the same tables
- Temporal persistence uses its own dedicated MySQL database (separate container)
- The `collegewise_recurring_charge_log` table continues to be written by the PHP code
- Temporal adds its own event history (stored in Temporal's MySQL) for workflow auditability

---

## File Structure

The Temporal infrastructure lives in the **cw-magento repo** at `infra/temporal/`,
alongside the existing Magento application code it integrates with.

```
collegewise1/cw-magento/
├── app/code/ForgeLabs/RecurringCharge/   # Existing — charge, retry, notification logic
│   ├── Cron/RecurringCharge.php          # Daily charge cron (USAePay)
│   ├── Cron/RetryRecurringCharge.php     # Retry cron with configurable intervals
│   ├── Cron/PaymentFailedNotification.php # Failed payment notification cron
│   ├── Model/NotificationService.php      # REST notification API
│   ├── Model/CronManager.php              # REST cron trigger/preview API
│   ├── Helper/RecurringChargeHelper.php   # Duplicate prevention, advisory locks
│   └── etc/webapi.xml                     # Existing REST routes
│
└── infra/temporal/                        # NEW — Temporal orchestration layer
    ├── docker-compose.yml
    ├── .env.example
    ├── README.md
    └── temporal-worker/
        ├── package.json
        ├── tsconfig.json
        ├── vitest.config.ts
        ├── Dockerfile
        ├── src/
        │   ├── worker.ts                  # Worker bootstrap
        │   ├── client.ts                  # CLI client for triggering workflows
        │   ├── workflows/
        │   │   ├── index.ts               # Workflow exports
        │   │   ├── payment-cycle.ts       # RecurringPaymentCycle workflow
        │   │   └── send-email.ts          # Standalone notification workflow
        │   ├── activities/
        │   │   ├── index.ts               # Activity exports
        │   │   ├── payment.ts             # Calls existing cron trigger API
        │   │   ├── database.ts            # Reads collegewise_payment_plan / _dates
        │   │   └── notification.ts        # Calls existing NotificationService API
        │   └── shared/
        │       ├── types.ts               # Aligned with actual DB schema
        │       └── idempotency.ts         # Deterministic charge key generation
        └── tests/
            ├── idempotency.test.ts
            ├── payment.test.ts
            ├── notification.test.ts
            ├── payment-cycle.test.ts
            └── workflows.test.ts
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
