import mysql from "mysql2/promise";
import type { PaymentPlan } from "../shared/types";

let pool: mysql.Pool | null = null;

function getPool(): mysql.Pool {
  if (!pool) {
    pool = mysql.createPool({
      host: process.env.CW_MYSQL_HOST,
      port: Number(process.env.CW_MYSQL_PORT || 3306),
      user: process.env.CW_MYSQL_USER,
      password: process.env.CW_MYSQL_PASSWORD,
      database: process.env.CW_MYSQL_DATABASE,
      waitForConnections: true,
      connectionLimit: 5,
    });
  }
  return pool;
}

/**
 * Fetch a payment plan and determine if it's eligible for charging today.
 */
export async function determineEligibility(
  paymentPlanId: number,
  chargeDate: string
): Promise<PaymentPlan | null> {
  const db = getPool();

  const [rows] = await db.execute<mysql.RowDataPacket[]>(
    `SELECT * FROM payment_plans WHERE id = ? AND status = 'active' AND next_payment_date <= ?`,
    [paymentPlanId, chargeDate]
  );

  if (rows.length === 0) return null;

  const row = rows[0];
  return {
    id: row.id,
    orderId: row.order_id,
    customerId: row.customer_id,
    customerEmail: row.customer_email,
    customerName: row.customer_name,
    amount: parseFloat(row.amount),
    currency: row.currency || "USD",
    frequency: row.frequency,
    nextPaymentDate: row.next_payment_date,
    status: row.status,
  };
}

/**
 * Record a successful or failed charge attempt.
 */
export async function recordChargeResult(
  paymentPlanId: number,
  chargeDate: string,
  transactionId: string | null,
  success: boolean,
  amount: number,
  errorMessage: string | null
): Promise<void> {
  const db = getPool();

  await db.execute(
    `INSERT INTO payment_dates (payment_plan_id, charge_date, transaction_id, success, amount, error_message, created_at)
     VALUES (?, ?, ?, ?, ?, ?, NOW())
     ON DUPLICATE KEY UPDATE transaction_id = VALUES(transaction_id), success = VALUES(success), error_message = VALUES(error_message)`,
    [paymentPlanId, chargeDate, transactionId, success, amount, errorMessage]
  );

  if (success) {
    // Advance next_payment_date based on frequency
    await db.execute(
      `UPDATE payment_plans
       SET next_payment_date = CASE frequency
         WHEN 'monthly' THEN DATE_ADD(next_payment_date, INTERVAL 1 MONTH)
         WHEN 'quarterly' THEN DATE_ADD(next_payment_date, INTERVAL 3 MONTH)
         WHEN 'annual' THEN DATE_ADD(next_payment_date, INTERVAL 1 YEAR)
         ELSE DATE_ADD(next_payment_date, INTERVAL 1 MONTH)
       END
       WHERE id = ?`,
      [paymentPlanId]
    );
  }
}
