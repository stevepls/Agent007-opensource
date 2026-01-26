<?php
/**
 * SyncAudit Logger for WordPress/WooCommerce
 * 
 * Sends sync events to the SyncAudit API for tracking and visualization.
 * Drop this file into your theme's functions.php or as a mu-plugin.
 * 
 * Configuration:
 * - Set SYNC_AUDIT_API_URL and SYNC_AUDIT_API_KEY in wp-config.php
 * - Or use the admin settings page
 * 
 * @package SyncAudit
 * @version 1.0.0
 */

if (!defined('ABSPATH')) {
    exit;
}

class SyncAudit_Logger {
    
    private $api_url;
    private $api_key;
    private $project;
    private $source_system;
    private $target_system;
    private $enabled;
    
    private static $instance = null;
    
    public static function get_instance() {
        if (self::$instance === null) {
            self::$instance = new self();
        }
        return self::$instance;
    }
    
    private function __construct() {
        $this->api_url = defined('SYNC_AUDIT_API_URL') 
            ? SYNC_AUDIT_API_URL 
            : get_option('sync_audit_api_url', 'http://localhost:8000');
        
        $this->api_key = defined('SYNC_AUDIT_API_KEY') 
            ? SYNC_AUDIT_API_KEY 
            : get_option('sync_audit_api_key', '');
        
        $this->project = defined('SYNC_AUDIT_PROJECT') 
            ? SYNC_AUDIT_PROJECT 
            : get_option('sync_audit_project', 'wordpress');
        
        $this->source_system = 'woocommerce';
        $this->target_system = 'acuity';
        
        $this->enabled = defined('SYNC_AUDIT_ENABLED') 
            ? SYNC_AUDIT_ENABLED 
            : get_option('sync_audit_enabled', true);
    }
    
    public function log_event($data) {
        if (!$this->enabled) {
            return ['skipped' => true, 'reason' => 'SyncAudit disabled'];
        }
        
        $event = wp_parse_args($data, [
            'project' => $this->project,
            'source_system' => $this->source_system,
            'target_system' => $this->target_system,
            'source_id' => '',
            'target_id' => null,
            'event_type' => 'sync_attempt',
            'status' => 'pending',
            'source_data' => null,
            'target_data' => null,
            'mismatches' => null,
            'error_message' => null,
            'triggered_by' => 'wordpress',
            'notes' => null
        ]);
        
        $response = wp_remote_post(
            rtrim($this->api_url, '/') . '/api/events',
            [
                'headers' => [
                    'Content-Type' => 'application/json',
                    'X-API-Key' => $this->api_key
                ],
                'body' => json_encode($event),
                'timeout' => 10
            ]
        );
        
        if (is_wp_error($response)) {
            error_log('[SyncAudit] Failed to log event: ' . $response->get_error_message());
            return $response;
        }
        
        $code = wp_remote_retrieve_response_code($response);
        $body = json_decode(wp_remote_retrieve_body($response), true);
        
        if ($code >= 200 && $code < 300) {
            error_log('[SyncAudit] Event logged: ID ' . ($body['id'] ?? 'unknown'));
            return $body;
        } else {
            error_log('[SyncAudit] API error: ' . json_encode($body));
            return new WP_Error('sync_audit_error', 'API returned ' . $code, $body);
        }
    }
    
    public function log_sync_attempt($source_id, $source_data, $target_system = null) {
        return $this->log_event([
            'source_id' => $source_id,
            'target_system' => $target_system ?? $this->target_system,
            'event_type' => 'sync_attempt',
            'status' => 'pending',
            'source_data' => $source_data,
            'triggered_by' => 'wordpress'
        ]);
    }
    
    public function log_sync_success($source_id, $target_id, $source_data, $target_data = null) {
        return $this->log_event([
            'source_id' => $source_id,
            'target_id' => $target_id,
            'event_type' => 'sync_success',
            'status' => 'synced',
            'source_data' => $source_data,
            'target_data' => $target_data,
            'triggered_by' => 'wordpress'
        ]);
    }
    
    public function log_sync_failure($source_id, $source_data, $error_message) {
        return $this->log_event([
            'source_id' => $source_id,
            'event_type' => 'sync_failed',
            'status' => 'failed',
            'source_data' => $source_data,
            'error_message' => $error_message,
            'triggered_by' => 'wordpress'
        ]);
    }
    
    public function log_mismatch($source_id, $source_data, $target_data, $mismatches) {
        return $this->log_event([
            'source_id' => $source_id,
            'event_type' => 'mismatch',
            'status' => 'mismatch',
            'source_data' => $source_data,
            'target_data' => $target_data,
            'mismatches' => $mismatches,
            'triggered_by' => 'wordpress'
        ]);
    }
    
    public function compare_and_log($source_id, $source_data, $target_data, $field_mappings) {
        $mismatches = [];
        
        foreach ($field_mappings as $source_field => $target_field) {
            $source_value = $source_data[$source_field] ?? null;
            $target_value = $target_data[$target_field] ?? null;
            
            $source_normalized = $this->normalize_value($source_value);
            $target_normalized = $this->normalize_value($target_value);
            
            if ($source_normalized !== $target_normalized) {
                $mismatches[] = [
                    'field' => $source_field,
                    'source_value' => $source_value,
                    'target_value' => $target_value,
                    'severity' => $this->determine_severity($source_field)
                ];
            }
        }
        
        if (!empty($mismatches)) {
            $this->log_mismatch($source_id, $source_data, $target_data, $mismatches);
        }
        
        return [
            'match' => empty($mismatches),
            'mismatch_count' => count($mismatches),
            'mismatches' => $mismatches
        ];
    }
    
    private function normalize_value($value) {
        if ($value === null || $value === '') {
            return null;
        }
        
        if (is_string($value)) {
            $value = trim(strtolower($value));
        }
        
        if (is_string($value) && preg_match('/\d{4}-\d{2}-\d{2}/', $value)) {
            try {
                $dt = new DateTime($value);
                return $dt->format('Y-m-d H:i');
            } catch (Exception $e) {
                // Not a valid date
            }
        }
        
        return $value;
    }
    
    private function determine_severity($field) {
        $critical_fields = ['appointment_date', 'appointment_time', 'calendar_id', 'instructor'];
        $high_fields = ['customer_email', 'customer_phone', 'package_id'];
        
        $field_lower = strtolower($field);
        
        if (in_array($field_lower, $critical_fields)) {
            return 'critical';
        }
        if (in_array($field_lower, $high_fields)) {
            return 'high';
        }
        return 'medium';
    }
}

function sync_audit() {
    return SyncAudit_Logger::get_instance();
}

function sync_audit_log_attempt($source_id, $source_data, $target_system = null) {
    return sync_audit()->log_sync_attempt($source_id, $source_data, $target_system);
}

function sync_audit_log_success($source_id, $target_id, $source_data, $target_data = null) {
    return sync_audit()->log_sync_success($source_id, $target_id, $source_data, $target_data);
}

function sync_audit_log_failure($source_id, $source_data, $error_message) {
    return sync_audit()->log_sync_failure($source_id, $source_data, $error_message);
}

function sync_audit_compare($source_id, $source_data, $target_data, $field_mappings) {
    return sync_audit()->compare_and_log($source_id, $source_data, $target_data, $field_mappings);
}
