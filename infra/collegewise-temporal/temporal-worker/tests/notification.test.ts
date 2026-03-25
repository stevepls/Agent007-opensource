import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

describe("sendNotification", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = {
      ...originalEnv,
      CW_MAGENTO_API_URL: "https://test.collegewise.com",
      CW_MAGENTO_API_TOKEN: "test-token",
    };
  });

  afterEach(() => {
    process.env = originalEnv;
    vi.restoreAllMocks();
  });

  it("calls Magento notification API with correct payload", async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({
        success: true,
        notification_id: "notif-001",
      }),
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockResponse as Response);

    const { sendNotification } = await import("../src/activities/notification");
    const result = await sendNotification({
      type: "payment_reminder",
      paymentPlanId: 42,
      orderId: 1001,
      customerId: 555,
      customerEmail: "jane@example.com",
      data: {
        customer_name: "Jane Doe",
        amount: 99.95,
        charge_date: "2026-04-01",
        days_before: 3,
      },
    });

    expect(result.success).toBe(true);
    expect(result.notificationId).toBe("notif-001");

    expect(globalThis.fetch).toHaveBeenCalledOnce();
    const [url, opts] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toBe(
      "https://test.collegewise.com/rest/V1/collegewise/notifications"
    );

    const body = JSON.parse((opts as RequestInit).body as string);
    expect(body.type).toBe("payment_reminder");
    expect(body.payment_plan_id).toBe(42);
    expect(body.customer_email).toBe("jane@example.com");
    expect(body.data.amount).toBe(99.95);
  });

  it("throws on non-OK response (Temporal will retry)", async () => {
    const mockResponse = {
      ok: false,
      status: 503,
      text: async () => "Service Unavailable",
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockResponse as Response);

    const { sendNotification } = await import("../src/activities/notification");
    await expect(
      sendNotification({
        type: "payment_receipt",
        paymentPlanId: 42,
        orderId: 1001,
        customerId: 555,
        customerEmail: "jane@example.com",
        data: { amount: 99.95 },
      })
    ).rejects.toThrow(/Magento notification API returned 503/);
  });
});
