"""
Unified Logging System
All logging goes through Python's logging module for both console and file output.
"""
import logging

# Get the root logger to ensure we use the same configuration as main.py
def get_logger(name="Default"):
    """Get a logger instance with the specified name."""
    return logging.getLogger(name)

# Unified logging functions that use the Python logging system
def console_info(message, module="Default"):
    """Log an info message with emoji formatting."""
    logger = get_logger(module)
    logger.info(f"ℹ️  [{module}] {message}")

def console_debug(message, module="Default"):
    """Log a debug message with emoji formatting."""
    logger = get_logger(module)
    logger.debug(f"🐛 [{module}] {message}")

def console_warning(message, module="Default"):
    """Log a warning message with emoji formatting."""
    logger = get_logger(module)
    logger.warning(f"⚠️  [{module}] {message}")

def console_error(message, module="Default"):
    """Log an error message with emoji formatting."""
    logger = get_logger(module)
    logger.error(f"❌ [{module}] {message}")

def console_telemetry_event(event_name, properties, module="Default"):
    """Log a telemetry event with emoji formatting."""
    logger = get_logger(module)
    logger.info(f"📊 [{module}] {event_name}: {properties}")
