import logging
import os
from datetime import datetime


def get_logger(name: str,
               log_file: str = "logs/pipeline.log",
               level=logging.INFO,
               include_timestamp_in_filename: bool = False):
    """
    Create and configure a logger with both console and file output.

    This function creates a logger that outputs to both the console and a file,
    avoiding duplicate handlers if the logger already exists.

    Args:
        name (str): Name of the logger (typically __name__ from calling module)
        log_file (str): Path to the log file (default: "logs/pipeline.log")
        level: Logging level (default: logging.INFO)
        include_timestamp_in_filename (bool): If True, adds timestamp to log filename

    Returns:
        logging.Logger: Configured logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("This message will appear in console and log file")
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid adding handlers twice - prevents duplicate log messages
    if logger.hasHandlers():
        return logger

    # Add timestamp to filename if requested (useful for multiple runs)
    if include_timestamp_in_filename:
        base_name, ext = os.path.splitext(log_file)
        timestamp = datetime.now().strftime("%Y%m%d")
        log_file = f"{base_name}_{timestamp}{ext}"

    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(log_file)
    if log_dir:  # Only create if there's actually a directory path
        os.makedirs(log_dir, exist_ok=True)

    # Enhanced formatter with more detailed information
    formatter = logging.Formatter(
        '%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d'
    )

    # Console handler - shows logs in terminal
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)  # Respect the logging level

    # File handler - saves logs to file with UTF-8 encoding for special characters
    file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='w')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # Add both handlers to the logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # Log the logger creation (helpful for debugging)
    logger.info(f"Logger '{name}' initialized. Logging to: {log_file}")

    return logger


def set_global_logging_level(level=logging.INFO):
    """
    Set the global logging level for all loggers.

    Args:
        level: Logging level (e.g., logging.DEBUG, logging.INFO, logging.WARNING)
    """
    logging.getLogger().setLevel(level)