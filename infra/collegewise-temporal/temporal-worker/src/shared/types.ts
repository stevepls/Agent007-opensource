export interface PaymentPlan {
  id: number;
  orderId: number;
  customerId: number;
  customerEmail: string;
  customerName: string;
  amount: number;
  currency: string;
  frequency: "monthly" | "quarterly" | "annual";
  nextPaymentDate: string;
  status: "active" | "paused" | "cancelled" | "completed";
}

export interface ChargeResult {
  success: boolean;
  transactionId?: string;
  authCode?: string;
  errorCode?: string;
  errorMessage?: string;
  amount: number;
  idempotencyKey: string;
}

export interface ChargeRecurringInput {
  paymentPlanId: number;
  chargeDate: string;
  dryRun?: boolean;
}

export type NotificationType =
  | "payment_reminder"
  | "payment_receipt"
  | "payment_failed_retry"
  | "payment_failed_final";

export interface SendNotificationInput {
  type: NotificationType;
  paymentPlanId: number;
  orderId: number;
  customerId: number;
  customerEmail: string;
  data: Record<string, string | number | boolean | null>;
}

export interface NotificationResult {
  success: boolean;
  notificationId?: string;
  error?: string;
}
