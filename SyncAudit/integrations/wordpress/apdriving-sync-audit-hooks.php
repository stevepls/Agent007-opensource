<?php
/**
 * APDriving-specific SyncAudit Integration
 * 
 * Hooks into the existing AcuitySyncService to log all sync events
 * to the SyncAudit API for visibility and debugging.
 * 
 * Installation:
 * 1. Copy sync-audit-logger.php to wp-content/mu-plugins/
 * 2. Copy this file to wp-content/mu-plugins/
 * 3. Add to wp-config.php:
 *    define('SYNC_AUDIT_API_URL', 'http://localhost:8000');
 *    define('SYNC_AUDIT_API_KEY', 'your-api-key');
 *    define('SYNC_AUDIT_PROJECT', 'apdriving');
 * 
 * @package SyncAudit
 * @version 1.0.0
 */

if (!defined('ABSPATH')) {
    exit;
}

// Require the base logger
require_once __DIR__ . '/sync-audit-logger.php';

/**
 * APDriving Sync Audit Integration
 */
class APDriving_SyncAudit {
    
    private static $instance = null;
    
    public static function get_instance() {
        if (self::$instance === null) {
            self::$instance = new self();
        }
        return self::$instance;
    }
    
    private function __construct() {
        // Hook into sync events
        add_action('pls_booking_before_acuity_sync', [$this, 'log_sync_attempt'], 10, 2);
        add_action('pls_booking_after_acuity_sync', [$this, 'log_sync_result'], 10, 3);
        add_action('pls_booking_sync_failed', [$this, 'log_sync_failure'], 10, 3);
        
        // Hook into cancellation events
        add_action('pls_booking_appointment_cancelled', [$this, 'log_cancellation'], 10, 3);
        
        // Hook into WooCommerce order status changes
        add_action('woocommerce_order_status_completed', [$this, 'log_order_completed'], 5, 1);
        add_action('woocommerce_order_status_processing', [$this, 'log_order_processing'], 5, 1);
        
        // Add custom hooks for verification
        add_action('pls_booking_verify_sync', [$this, 'verify_and_log_sync'], 10, 1);
    }
    
    /**
     * Log sync attempt before calling Acuity API
     */
    public function log_sync_attempt($order_id, $appointment_data) {
        $order = wc_get_order($order_id);
        if (!$order) return;
        
        $source_data = $this->extract_order_data($order);
        $source_data['prepared_appointment_data'] = $appointment_data;
        
        sync_audit_log_attempt(
            (string) $order_id,
            $source_data,
            'acuity'
        );
    }
    
    /**
     * Log successful sync after Acuity returns
     */
    public function log_sync_result($order_id, $acuity_appointment_id, $acuity_response) {
        $order = wc_get_order($order_id);
        if (!$order) return;
        
        $source_data = $this->extract_order_data($order);
        $target_data = $this->extract_acuity_data($acuity_response);
        
        // Compare and detect mismatches
        $field_mappings = $this->get_field_mappings();
        $comparison = sync_audit()->compare_and_log(
            (string) $order_id,
            $source_data,
            $target_data,
            $field_mappings
        );
        
        // If no mismatches, log success
        if ($comparison['match']) {
            sync_audit_log_success(
                (string) $order_id,
                (string) $acuity_appointment_id,
                $source_data,
                $target_data
            );
        }
    }
    
    /**
     * Log sync failure
     */
    public function log_sync_failure($order_id, $error_message, $appointment_data = null) {
        $order = wc_get_order($order_id);
        $source_data = $order ? $this->extract_order_data($order) : [];
        
        if ($appointment_data) {
            $source_data['prepared_appointment_data'] = $appointment_data;
        }
        
        sync_audit_log_failure(
            (string) $order_id,
            $source_data,
            $error_message
        );
    }
    
    /**
     * Log cancellation events
     */
    public function log_cancellation($appointment_id, $order_id, $cancelled_by) {
        sync_audit()->log_event([
            'source_id' => (string) $order_id,
            'target_id' => (string) $appointment_id,
            'event_type' => 'cancellation',
            'status' => 'synced',
            'source_data' => [
                'order_id' => $order_id,
                'cancelled_by' => $cancelled_by,
                'cancelled_at' => current_time('mysql')
            ],
            'notes' => "Appointment cancelled by: $cancelled_by"
        ]);
    }
    
    /**
     * Log when order reaches completed status
     */
    public function log_order_completed($order_id) {
        $this->log_order_status_change($order_id, 'completed');
    }
    
    /**
     * Log when order reaches processing status
     */
    public function log_order_processing($order_id) {
        $this->log_order_status_change($order_id, 'processing');
    }
    
    /**
     * Log order status change (triggers sync)
     */
    private function log_order_status_change($order_id, $status) {
        $order = wc_get_order($order_id);
        if (!$order) return;
        
        // Only log for booking orders
        if (get_post_meta($order_id, '_is_booking_order', true) !== 'yes') {
            return;
        }
        
        sync_audit()->log_event([
            'source_id' => (string) $order_id,
            'event_type' => 'sync_attempt',
            'status' => 'pending',
            'source_data' => $this->extract_order_data($order),
            'notes' => "Order status changed to: $status"
        ]);
    }
    
    /**
     * Verify sync status and log result
     */
    public function verify_and_log_sync($order_id) {
        global $wpdb;
        
        $order = wc_get_order($order_id);
        if (!$order) return;
        
        $source_data = $this->extract_order_data($order);
        
        // Get confirmed appointment
        $appointment = $wpdb->get_row($wpdb->prepare(
            "SELECT * FROM {$wpdb->prefix}pls_confirmed_appointments 
             WHERE order_id = %d 
             ORDER BY id DESC LIMIT 1",
            $order_id
        ));
        
        // Get Acuity data if we have an appointment ID
        $acuity_appointment_id = get_post_meta($order_id, '_acuity_appointment_id', true);
        $target_data = null;
        
        if ($acuity_appointment_id && !str_starts_with($acuity_appointment_id, 'local_')) {
            $target_data = $this->fetch_acuity_appointment($acuity_appointment_id);
        }
        
        // Add local confirmed appointment data
        if ($appointment) {
            $source_data['confirmed_appointment'] = [
                'id' => $appointment->id,
                'acuity_appointment_id' => $appointment->acuity_appointment_id,
                'appointment_date' => $appointment->appointment_date,
                'appointment_time' => $appointment->appointment_time,
                'instructor' => $appointment->instructor,
                'calendar_id' => $appointment->calendar_id,
                'status' => $appointment->status,
                'acuity_sync_status' => $appointment->acuity_sync_status
            ];
        }
        
        // Compare and log
        if ($target_data) {
            $field_mappings = $this->get_field_mappings();
            sync_audit()->compare_and_log(
                (string) $order_id,
                $source_data,
                $target_data,
                $field_mappings
            );
        } else {
            // Log verification without target data
            sync_audit()->log_event([
                'source_id' => (string) $order_id,
                'target_id' => $acuity_appointment_id,
                'event_type' => 'verification',
                'status' => $acuity_appointment_id ? 'synced' : 'pending',
                'source_data' => $source_data,
                'notes' => $target_data ? null : 'Could not fetch Acuity data for verification'
            ]);
        }
    }
    
    /**
     * Extract relevant data from WooCommerce order
     */
    private function extract_order_data($order) {
        $order_id = $order->get_id();
        
        return [
            'order_id' => $order_id,
            'order_number' => $order->get_order_number(),
            'status' => $order->get_status(),
            'customer_email' => $order->get_billing_email(),
            'customer_phone' => $order->get_billing_phone(),
            'customer_name' => $order->get_billing_first_name() . ' ' . $order->get_billing_last_name(),
            
            // Booking meta
            'booking_date' => get_post_meta($order_id, '_booking_date', true),
            'booking_time' => get_post_meta($order_id, '_booking_time', true),
            'booking_location' => get_post_meta($order_id, '_booking_location', true),
            'booking_instructor' => get_post_meta($order_id, '_booking_instructor', true),
            'booking_calendar_id' => get_post_meta($order_id, '_booking_calendar_id', true),
            'booking_package' => get_post_meta($order_id, '_booking_package', true),
            'booking_package_id' => get_post_meta($order_id, '_booking_package_id', true),
            
            // Sync meta
            'acuity_appointment_id' => get_post_meta($order_id, '_acuity_appointment_id', true),
            'acuity_sync_status' => get_post_meta($order_id, '_acuity_sync_status', true),
            'acuity_sync_error' => get_post_meta($order_id, '_acuity_sync_error', true),
            
            // Session tracking
            'booking_session_id' => get_post_meta($order_id, '_booking_session_id', true),
            'temporary_booking_id' => get_post_meta($order_id, '_temporary_booking_id', true),
            
            // Timestamps
            'created' => $order->get_date_created() ? $order->get_date_created()->format('Y-m-d H:i:s') : null
        ];
    }
    
    /**
     * Extract relevant data from Acuity API response
     */
    private function extract_acuity_data($acuity_response) {
        if (!is_array($acuity_response)) {
            return null;
        }
        
        return [
            'appointment_id' => $acuity_response['id'] ?? null,
            'datetime' => $acuity_response['datetime'] ?? null,
            'appointment_date' => isset($acuity_response['datetime']) 
                ? date('Y-m-d', strtotime($acuity_response['datetime'])) 
                : null,
            'appointment_time' => isset($acuity_response['datetime']) 
                ? date('H:i', strtotime($acuity_response['datetime'])) 
                : null,
            'calendar_id' => $acuity_response['calendarID'] ?? null,
            'calendar_name' => $acuity_response['calendar'] ?? null,
            'appointment_type_id' => $acuity_response['appointmentTypeID'] ?? null,
            'customer_email' => $acuity_response['email'] ?? null,
            'customer_phone' => $acuity_response['phone'] ?? null,
            'customer_name' => trim(($acuity_response['firstName'] ?? '') . ' ' . ($acuity_response['lastName'] ?? '')),
            'canceled' => $acuity_response['canceled'] ?? false,
            'notes' => $acuity_response['notes'] ?? null
        ];
    }
    
    /**
     * Fetch appointment data from Acuity API
     */
    private function fetch_acuity_appointment($appointment_id) {
        // Use the existing AcuitySyncService if available
        if (class_exists('PLS_Booking_AcuitySyncService')) {
            $sync_service = new PLS_Booking_AcuitySyncService();
            $appointments = $sync_service->get_appointments(['id' => $appointment_id]);
            
            if (!is_wp_error($appointments) && !empty($appointments)) {
                return $this->extract_acuity_data($appointments[0]);
            }
        }
        
        return null;
    }
    
    /**
     * Get field mappings for comparison
     * Maps source (WooCommerce) fields to target (Acuity) fields
     */
    private function get_field_mappings() {
        return [
            'booking_date' => 'appointment_date',
            'booking_time' => 'appointment_time',
            'booking_calendar_id' => 'calendar_id',
            'customer_email' => 'customer_email',
            'customer_phone' => 'customer_phone',
        ];
    }
}

// Initialize on plugins loaded
add_action('plugins_loaded', function() {
    APDriving_SyncAudit::get_instance();
});

/**
 * WP-CLI command for manual verification
 */
if (defined('WP_CLI') && WP_CLI) {
    WP_CLI::add_command('syncaudit verify', function($args) {
        if (empty($args[0])) {
            WP_CLI::error('Please provide an order ID');
            return;
        }
        
        $order_id = intval($args[0]);
        do_action('pls_booking_verify_sync', $order_id);
        WP_CLI::success("Verification logged for order #$order_id");
    });
    
    WP_CLI::add_command('syncaudit verify-all', function($args, $assoc_args) {
        $days = $assoc_args['days'] ?? 7;
        
        $orders = wc_get_orders([
            'limit' => -1,
            'meta_key' => '_is_booking_order',
            'meta_value' => 'yes',
            'date_created' => '>' . date('Y-m-d', strtotime("-$days days"))
        ]);
        
        WP_CLI::log("Verifying " . count($orders) . " orders from last $days days...");
        
        foreach ($orders as $order) {
            do_action('pls_booking_verify_sync', $order->get_id());
            WP_CLI::log("Verified order #" . $order->get_id());
        }
        
        WP_CLI::success("Verification complete!");
    });
}
