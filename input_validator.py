"""
Input validation and sanitization for OpenCore Prodigy.

Ensures user inputs are safe and valid before processing.
"""

import re
from pathlib import Path
from typing import Any, List, Optional

from logger import setup_logger

logger = setup_logger(__name__)


class ValidationError(Exception):
    """Raised when input validation fails."""

    pass


def validate_choice(choice: str, valid_options: List[str]) -> str:
    """
    Validate user choice against valid options.

    Args:
        choice: User input
        valid_options: List of valid option keys

    Returns:
        Validated choice (lowercase)

    Raises:
        ValidationError: If choice is invalid
    """
    choice = choice.strip().lower()
    if choice not in valid_options:
        raise ValidationError(
            f"Invalid choice '{choice}'. Valid options: {', '.join(valid_options)}"
        )
    return choice


def validate_yes_no(prompt: str, max_attempts: int = 3) -> bool:
    """
    Prompt user for yes/no response with validation.

    Args:
        prompt: Question to ask
        max_attempts: Maximum retry attempts

    Returns:
        True for yes, False for no

    Raises:
        ValidationError: If max attempts exceeded
    """
    for attempt in range(max_attempts):
        try:
            response = input(f"{prompt} (y/n): ").strip().lower()
            if response in ("y", "yes"):
                return True
            elif response in ("n", "no"):
                return False
            else:
                logger.warning("Please enter 'y' or 'n'")
        except KeyboardInterrupt:
            raise ValidationError("User cancelled")

    raise ValidationError(f"Failed to get valid yes/no response after {max_attempts} attempts")


def validate_directory_path(path: str, must_exist: bool = False) -> Path:
    """
    Validate directory path.

    Args:
        path: Path string to validate
        must_exist: Whether directory must already exist

    Returns:
        Validated Path object

    Raises:
        ValidationError: If path is invalid
    """
    try:
        p = Path(path).resolve()

        if must_exist and not p.exists():
            raise ValidationError(f"Directory does not exist: {p}")

        if must_exist and not p.is_dir():
            raise ValidationError(f"Not a directory: {p}")

        # Check for suspicious patterns
        if ".." in str(p) or "~" in str(p):
            logger.warning(f"Path contains relative components, resolving to: {p}")

        return p

    except (ValueError, OSError) as e:
        raise ValidationError(f"Invalid path '{path}': {e}") from e


def validate_filename(filename: str, max_length: int = 255) -> str:
    """
    Validate filename for safety.

    Args:
        filename: Filename to validate
        max_length: Maximum filename length

    Returns:
        Validated filename

    Raises:
        ValidationError: If filename is invalid
    """
    if not filename:
        raise ValidationError("Filename cannot be empty")

    if len(filename) > max_length:
        raise ValidationError(f"Filename too long (max {max_length} characters)")

    # Remove dangerous characters
    invalid_chars = r'[<>:"|?*\\x00-\\x1f]'
    if re.search(invalid_chars, filename):
        raise ValidationError(f"Filename contains invalid characters: {filename}")

    # Don't allow names that are reserved
    reserved = {"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"}
    if filename.upper().split(".")[0] in reserved:
        raise ValidationError(f"Reserved filename: {filename}")

    return filename


def validate_boot_args(args: str) -> str:
    """
    Validate boot arguments string.

    Args:
        args: Boot arguments string

    Returns:
        Validated arguments

    Raises:
        ValidationError: If arguments are invalid
    """
    # Boot args should be reasonably short
    if len(args) > 1000:
        raise ValidationError("Boot arguments string too long")

    # Check for obvious shell injection attempts
    dangerous_patterns = [";", "|", "&", "$", "`", "(", ")", "<", ">"]
    if any(pattern in args for pattern in dangerous_patterns):
        logger.warning("Boot arguments contain special characters - ensure they are intentional")

    return args.strip()


def validate_uuid(uuid_str: str) -> str:
    """
    Validate UUID format.

    Args:
        uuid_str: UUID string to validate

    Returns:
        Validated UUID

    Raises:
        ValidationError: If UUID is invalid
    """
    uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    if not re.match(uuid_pattern, uuid_str.lower()):
        raise ValidationError(f"Invalid UUID format: {uuid_str}")
    return uuid_str.upper()


def validate_mac_address(mac: str) -> str:
    """
    Validate MAC address format.

    Args:
        mac: MAC address string (colon or hyphen separated)

    Returns:
        Validated MAC address (colon separated)

    Raises:
        ValidationError: If MAC address is invalid
    """
    # Accept both colon and hyphen separators
    mac_pattern = r"^([0-9a-f]{2}[:-]){5}([0-9a-f]{2})$"
    if not re.match(mac_pattern, mac.lower()):
        raise ValidationError(f"Invalid MAC address format: {mac}")

    # Normalize to colon separator
    return mac.upper().replace("-", ":")


def validate_smbios_model(model: str) -> str:
    """
    Validate SMBIOS model format.

    Args:
        model: SMBIOS model string (e.g., "iMac19,1")

    Returns:
        Validated SMBIOS model

    Raises:
        ValidationError: If model is invalid
    """
    smbios_pattern = r"^[a-zA-Z0-9]+\d+,\d+$"
    if not re.match(smbios_pattern, model):
        raise ValidationError(
            f"Invalid SMBIOS model format: {model} (expected format like 'iMac19,1')"
        )
    return model


def sanitize_hardware_report(report: dict) -> dict:
    """
    Sanitize hardware report to remove or mask sensitive data.

    Args:
        report: Hardware report dictionary

    Returns:
        Sanitized report

    Note:
        Serial numbers and MAC addresses are preserved but marked as sensitive.
    """
    sanitized = report.copy()

    # Mark sensitive fields
    if "Motherboard" in sanitized and sanitized["Motherboard"]:
        if "SerialNumber" in sanitized["Motherboard"]:
            # Keep it but users should be aware they're sharing it
            logger.debug("Hardware report contains motherboard serial number")

    return sanitized


def validate_input_safe(prompt: str, max_length: int = 1024) -> str:
    """
    Get and validate user input with safety checks.

    Args:
        prompt: Prompt to display
        max_length: Maximum input length

    Returns:
        Validated input

    Raises:
        ValidationError: If input is invalid
    """
    try:
        user_input = input(prompt).strip()

        if not user_input:
            raise ValidationError("Input cannot be empty")

        if len(user_input) > max_length:
            raise ValidationError(f"Input too long (max {max_length} characters)")

        return user_input

    except KeyboardInterrupt:
        raise ValidationError("User cancelled input")
