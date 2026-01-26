"""
Cost Tracker

Tracks API token usage and enforces budget limits.
Implements circuit breaker for failure protection.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum

from .policies import get_policy


class BudgetExceededError(Exception):
    """Raised when token/call budget is exceeded."""
    pass


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open due to repeated failures."""
    pass


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class TokenUsage:
    """Track token usage for a single request."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def cost_estimate_usd(self) -> float:
        """Estimate cost in USD (rough approximation)."""
        # Approximate costs per 1K tokens
        costs = {
            "claude-3-5-sonnet": (0.003, 0.015),  # (input, output)
            "claude-3-opus": (0.015, 0.075),
            "gpt-4": (0.03, 0.06),
            "gpt-4-turbo": (0.01, 0.03),
            "gpt-3.5-turbo": (0.0005, 0.0015),
        }
        
        # Default to Claude Sonnet pricing
        input_cost, output_cost = costs.get("claude-3-5-sonnet", (0.003, 0.015))
        
        for model_name, (ic, oc) in costs.items():
            if model_name in self.model.lower():
                input_cost, output_cost = ic, oc
                break
        
        return (self.input_tokens / 1000 * input_cost) + (self.output_tokens / 1000 * output_cost)


@dataclass
class CostTracker:
    """
    Tracks token usage and enforces budget limits.
    
    Features:
    - Token counting per task
    - Budget limits with warnings and hard stops
    - API call counting
    - Circuit breaker for repeated failures
    - Rate limiting
    """
    
    # Budget tracking
    total_tokens: int = 0
    total_api_calls: int = 0
    total_tool_calls: int = 0
    usage_history: List[TokenUsage] = field(default_factory=list)
    
    # Circuit breaker state
    consecutive_failures: int = 0
    circuit_state: CircuitState = CircuitState.CLOSED
    circuit_opened_at: Optional[datetime] = None
    
    # Rate limiting
    request_timestamps: List[datetime] = field(default_factory=list)
    
    # Session info
    session_start: datetime = field(default_factory=datetime.utcnow)
    warnings_issued: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        self._load_limits()
    
    def _load_limits(self):
        """Load limits from policy configuration."""
        cost_policy = get_policy("cost") or {}
        
        self.max_tokens = cost_policy.get("max_tokens_per_task", 100_000)
        self.max_api_calls = cost_policy.get("max_api_calls_per_task", 50)
        self.max_tool_calls = cost_policy.get("max_tool_calls_per_task", 100)
        self.warn_at_percentage = cost_policy.get("warn_at_percentage", 80)
        self.circuit_breaker_threshold = cost_policy.get("circuit_breaker_threshold", 5)
        self.circuit_breaker_reset_time = cost_policy.get("circuit_breaker_reset_time", 300)
        self.max_requests_per_minute = cost_policy.get("max_requests_per_minute", 30)
    
    def record_usage(self, usage: TokenUsage) -> TokenUsage:
        """
        Record token usage for a request.
        
        Raises:
            BudgetExceededError: If budget limit is reached
        """
        # Check budget before recording
        projected_total = self.total_tokens + usage.total_tokens
        
        if projected_total > self.max_tokens:
            raise BudgetExceededError(
                f"Token budget exceeded: {projected_total} > {self.max_tokens}. "
                f"Task used {self.total_tokens} tokens so far."
            )
        
        # Record usage
        self.total_tokens += usage.total_tokens
        self.total_api_calls += 1
        self.usage_history.append(usage)
        
        # Check warning threshold
        usage_percentage = (self.total_tokens / self.max_tokens) * 100
        if usage_percentage >= self.warn_at_percentage:
            warning = f"Token usage at {usage_percentage:.1f}% of budget ({self.total_tokens}/{self.max_tokens})"
            if warning not in self.warnings_issued:
                self.warnings_issued.append(warning)
        
        # Reset circuit breaker on success
        self.consecutive_failures = 0
        if self.circuit_state == CircuitState.HALF_OPEN:
            self.circuit_state = CircuitState.CLOSED
        
        return usage
    
    def record_tool_call(self):
        """Record a tool call."""
        self.total_tool_calls += 1
        
        if self.total_tool_calls > self.max_tool_calls:
            raise BudgetExceededError(
                f"Tool call limit exceeded: {self.total_tool_calls} > {self.max_tool_calls}"
            )
    
    def record_failure(self, error: str = None):
        """
        Record a failure for circuit breaker.
        
        Raises:
            CircuitBreakerOpenError: If circuit breaker trips
        """
        self.consecutive_failures += 1
        
        if self.consecutive_failures >= self.circuit_breaker_threshold:
            self.circuit_state = CircuitState.OPEN
            self.circuit_opened_at = datetime.utcnow()
            raise CircuitBreakerOpenError(
                f"Circuit breaker tripped after {self.consecutive_failures} consecutive failures. "
                f"Last error: {error or 'Unknown'}. "
                f"Will reset after {self.circuit_breaker_reset_time} seconds."
            )
    
    def check_circuit_breaker(self):
        """
        Check if circuit breaker allows requests.
        
        Raises:
            CircuitBreakerOpenError: If circuit is open
        """
        if self.circuit_state == CircuitState.CLOSED:
            return
        
        if self.circuit_state == CircuitState.OPEN:
            # Check if reset time has passed
            if self.circuit_opened_at:
                elapsed = (datetime.utcnow() - self.circuit_opened_at).total_seconds()
                if elapsed >= self.circuit_breaker_reset_time:
                    self.circuit_state = CircuitState.HALF_OPEN
                    return
            
            raise CircuitBreakerOpenError(
                f"Circuit breaker is OPEN. "
                f"Waiting for reset ({self.circuit_breaker_reset_time}s)."
            )
    
    def check_rate_limit(self):
        """
        Check if rate limit allows a new request.
        
        Returns:
            float: Seconds to wait (0 if no wait needed)
        """
        now = datetime.utcnow()
        minute_ago = now - timedelta(minutes=1)
        
        # Clean old timestamps
        self.request_timestamps = [ts for ts in self.request_timestamps if ts > minute_ago]
        
        if len(self.request_timestamps) >= self.max_requests_per_minute:
            # Calculate wait time
            oldest = min(self.request_timestamps)
            wait_time = (oldest + timedelta(minutes=1) - now).total_seconds()
            return max(0, wait_time)
        
        # Record this request
        self.request_timestamps.append(now)
        return 0
    
    def can_proceed(self) -> tuple[bool, Optional[str]]:
        """
        Check if a new request can proceed.
        
        Returns:
            (can_proceed, reason) - reason is None if can proceed
        """
        try:
            self.check_circuit_breaker()
        except CircuitBreakerOpenError as e:
            return False, str(e)
        
        if self.total_api_calls >= self.max_api_calls:
            return False, f"API call limit reached: {self.total_api_calls}/{self.max_api_calls}"
        
        wait_time = self.check_rate_limit()
        if wait_time > 0:
            return False, f"Rate limited. Wait {wait_time:.1f}s"
        
        return True, None
    
    def get_summary(self) -> Dict[str, Any]:
        """Get usage summary for the current session."""
        total_cost = sum(u.cost_estimate_usd for u in self.usage_history)
        
        return {
            "session_duration_seconds": (datetime.utcnow() - self.session_start).total_seconds(),
            "total_tokens": self.total_tokens,
            "max_tokens": self.max_tokens,
            "tokens_remaining": self.max_tokens - self.total_tokens,
            "usage_percentage": (self.total_tokens / self.max_tokens) * 100 if self.max_tokens > 0 else 0,
            "total_api_calls": self.total_api_calls,
            "max_api_calls": self.max_api_calls,
            "total_tool_calls": self.total_tool_calls,
            "max_tool_calls": self.max_tool_calls,
            "estimated_cost_usd": round(total_cost, 4),
            "circuit_state": self.circuit_state.value,
            "consecutive_failures": self.consecutive_failures,
            "warnings": self.warnings_issued,
        }
    
    def reset(self):
        """Reset tracker for a new task."""
        self.total_tokens = 0
        self.total_api_calls = 0
        self.total_tool_calls = 0
        self.usage_history = []
        self.consecutive_failures = 0
        self.circuit_state = CircuitState.CLOSED
        self.circuit_opened_at = None
        self.warnings_issued = []
        self.session_start = datetime.utcnow()


# Global tracker instance
_tracker: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    """Get or create the global cost tracker."""
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker


def track_tokens(input_tokens: int, output_tokens: int, model: str = "") -> TokenUsage:
    """Convenience function to track token usage."""
    usage = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        model=model,
    )
    return get_cost_tracker().record_usage(usage)
