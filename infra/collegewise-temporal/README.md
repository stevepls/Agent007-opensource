# Collegewise — Temporal Workflow Infrastructure

Durable workflow orchestration for Collegewise recurring payments and notifications.
The Temporal worker is a thin orchestrator — Magento handles all payment processing
(Authorize.net), notification rendering (templates), and email delivery (SMTP).

## Quick Start

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env with your Magento MySQL credentials and Magento API token

# 2. Start everything
docker compose up -d

# 3. Check Temporal UI
open http://localhost:8080
```

## Services

| Service | Port | Description |
|---|---|---|
| `temporal-server` | 7233 | Temporal gRPC endpoint |
| `temporal-ui` | 8080 | Web UI for workflow visibility |
| `temporal-mysql` | 3307 | Temporal persistence (separate from Magento) |
| `temporal-worker` | — | Workflow + activity executor (calls Magento APIs) |

## Workflows

### `recurringPaymentCycle` (primary)

One workflow per payment plan per billing cycle. Manages the full timeline:

1. **Reminder notifications** at configurable intervals (default: 7, 3, 1 days before)
2. **Charge** via Magento's REST API on charge date (Magento calls Authorize.net)
3. **Receipt notification** on success
4. **Retry schedule** on failure (default: +1d, +3d, +5d) with retry notice notifications
5. **Final failure notification** + flag for manual review after all retries exhausted

Emails and charges live in one workflow so they can never be misaligned.

- Workflow ID: `charge-cycle-{planId}-{chargeDate}` (deterministic, idempotent)
- Signals: `cancelCycle`, `paymentMethodUpdated`
- Idempotency key: `sha256(charge:{planId}:{chargeDate})` via `X-Idempotency-Key` header

### `sendNotificationWorkflow` (standalone)

For ad-hoc notifications outside the payment cycle (e.g., one-off account alerts).
Calls Magento's notification API with a typed payload — Magento renders the
template and delivers via SMTP.

## Triggering Workflows

### From CLI

```bash
cd temporal-worker
npm install

# Start a full payment cycle (reminders → charge → receipt)
npx ts-node src/client.ts cycle 42 2026-04-01
npx ts-node src/client.ts cycle 42 2026-04-01 --dry-run

# Send a standalone notification via Magento
npx ts-node src/client.ts notify payment_reminder customer@example.com '{"customer_name":"Jane","amount":"99.00","charge_date":"2026-04-01"}'

# Cancel a running cycle
npx ts-node src/client.ts cancel charge-cycle-42-2026-04-01

# Notify a cycle that the customer updated their payment method
npx ts-node src/client.ts payment-updated charge-cycle-42-2026-04-01
```

### From Magento (Phase 2 — HTTP trigger)

The Magento cron starts one `RecurringPaymentCycle` workflow per plan per
billing period. The workflow handles everything from reminders through
charge through receipt — Magento never sends emails or retries charges itself.

## Testing

```bash
cd temporal-worker
npm install
npm test            # run all tests
npm run test:watch  # watch mode
```

### Test Suite

| Test file | Coverage |
|---|---|
| `idempotency.test.ts` | Key determinism, uniqueness, format |
| `payment.test.ts` | Dry run, Magento charge endpoint call, error handling |
| `notification.test.ts` | Magento notification API call, payload structure, errors |
| `payment-cycle.test.ts` | Full cycle integration: eligibility, reminders, charge, retries, cancellation |
| `workflows.test.ts` | Standalone notification workflow |

## Architecture

See [Orchestrator/docs/CW_TEMPORAL_ARCHITECTURE.md](../../Orchestrator/docs/CW_TEMPORAL_ARCHITECTURE.md)
for the full architecture spec, phased rollout plan, and design decisions.
