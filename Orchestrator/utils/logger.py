"""
Centralized Debug Logger

Provides file and console logging for the Orchestrator.
All components should use this logger for consistent output.
"""

import os
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from enum import Enum


# =============================================================================
# Configuration
# =============================================================================

LOG_DIR = Path(os.getenv("LOG_DIR", "/home/steve/Agent007/Orchestrator/logs"))
LOG_FILE = LOG_DIR / "orchestrator.log"
DEBUG_LOG_FILE = LOG_DIR / "debug.log"
MAX_LOG_LINES = 1000  # Keep last N lines in memory for UI


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class LogEntry:
    """A single log entry."""
    timestamp: str
    level: str
    source: str
    message: str
    data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())


# =============================================================================
# Logger Class
# =============================================================================

class OrchestratorLogger:
    """Centralized logger for the Orchestrator."""
    
    _instance: Optional["OrchestratorLogger"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.entries: List[LogEntry] = []
        self.max_entries = MAX_LOG_LINES
        
        # Create log directory
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        
        # Set up Python logging
        self.logger = logging.getLogger("orchestrator")
        self.logger.setLevel(logging.DEBUG)
        
        # File handler (all logs)
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
        ))
        self.logger.addHandler(file_handler)
        
        # Debug file handler (JSON format)
        self.debug_file = open(DEBUG_LOG_FILE, "a")
        
        # Console handler (INFO and above)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(
            '%(levelname)s: %(message)s'
        ))
        self.logger.addHandler(console_handler)
        
        self.info("Logger initialized", source="logger")
    
    def _add_entry(self, level: LogLevel, message: str, source: str = "unknown", data: Dict = None):
        """Add a log entry."""
        entry = LogEntry(
            timestamp=datetime.utcnow().isoformat(),
            level=level.value,
            source=source,
            message=message,
            data=data,
        )
        
        # Add to memory buffer
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]
        
        # Write to debug file (JSON)
        self.debug_file.write(entry.to_json() + "\n")
        self.debug_file.flush()
        
        return entry
    
    def debug(self, message: str, source: str = "unknown", data: Dict = None):
        """Log debug message."""
        self.logger.debug(f"[{source}] {message}")
        return self._add_entry(LogLevel.DEBUG, message, source, data)
    
    def info(self, message: str, source: str = "unknown", data: Dict = None):
        """Log info message."""
        self.logger.info(f"[{source}] {message}")
        return self._add_entry(LogLevel.INFO, message, source, data)
    
    def warning(self, message: str, source: str = "unknown", data: Dict = None):
        """Log warning message."""
        self.logger.warning(f"[{source}] {message}")
        return self._add_entry(LogLevel.WARNING, message, source, data)
    
    def error(self, message: str, source: str = "unknown", data: Dict = None):
        """Log error message."""
        self.logger.error(f"[{source}] {message}")
        return self._add_entry(LogLevel.ERROR, message, source, data)
    
    def critical(self, message: str, source: str = "unknown", data: Dict = None):
        """Log critical message."""
        self.logger.critical(f"[{source}] {message}")
        return self._add_entry(LogLevel.CRITICAL, message, source, data)
    
    def get_recent(self, n: int = 100, level: str = None, source: str = None) -> List[LogEntry]:
        """Get recent log entries with optional filtering."""
        entries = self.entries
        
        if level:
            entries = [e for e in entries if e.level == level.upper()]
        
        if source:
            entries = [e for e in entries if source.lower() in e.source.lower()]
        
        return entries[-n:]
    
    def get_errors(self, n: int = 50) -> List[LogEntry]:
        """Get recent errors and warnings."""
        return [e for e in self.entries if e.level in ("ERROR", "WARNING", "CRITICAL")][-n:]
    
    def clear(self):
        """Clear in-memory log buffer."""
        self.entries = []
    
    def export(self, format: str = "json") -> str:
        """Export logs."""
        if format == "json":
            return json.dumps([e.to_dict() for e in self.entries], indent=2)
        else:
            return "\n".join(
                f"{e.timestamp} | {e.level:8} | {e.source} | {e.message}"
                for e in self.entries
            )


# =============================================================================
# Global Access
# =============================================================================

_logger: Optional[OrchestratorLogger] = None


def get_logger() -> OrchestratorLogger:
    """Get the global logger instance."""
    global _logger
    if _logger is None:
        _logger = OrchestratorLogger()
    return _logger


def log_debug(message: str, source: str = "unknown", data: Dict = None):
    """Quick debug log."""
    return get_logger().debug(message, source, data)


def log_info(message: str, source: str = "unknown", data: Dict = None):
    """Quick info log."""
    return get_logger().info(message, source, data)


def log_warning(message: str, source: str = "unknown", data: Dict = None):
    """Quick warning log."""
    return get_logger().warning(message, source, data)


def log_error(message: str, source: str = "unknown", data: Dict = None):
    """Quick error log."""
    return get_logger().error(message, source, data)
