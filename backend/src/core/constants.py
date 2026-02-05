"""Core constants used across the CRM application."""

from fastapi import status


# Default settings
DEFAULT_CURRENCY = "USD"
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Default UI colors (used in whitelabel/theming)
DEFAULT_PRIMARY_COLOR = "#6366f1"
DEFAULT_SECONDARY_COLOR = "#8b5cf6"
DEFAULT_ACCENT_COLOR = "#22c55e"

# Backwards compatibility alias
DEFAULT_COLOR = DEFAULT_PRIMARY_COLOR

# Default locale settings
DEFAULT_LANGUAGE = "en"
DEFAULT_DATE_FORMAT = "MM/DD/YYYY"

# Entity types for polymorphic relationships
ENTITY_TYPE_CONTACTS = "contacts"
ENTITY_TYPE_COMPANIES = "companies"
ENTITY_TYPE_LEADS = "leads"
ENTITY_TYPE_OPPORTUNITIES = "opportunities"
ENTITY_TYPE_ACTIVITIES = "activities"
ENTITY_TYPE_CAMPAIGNS = "campaigns"


# HTTP Status Codes - commonly used codes as constants
class HTTPStatus:
    """HTTP status codes for API responses."""

    OK = status.HTTP_200_OK
    CREATED = status.HTTP_201_CREATED
    NO_CONTENT = status.HTTP_204_NO_CONTENT
    BAD_REQUEST = status.HTTP_400_BAD_REQUEST
    UNAUTHORIZED = status.HTTP_401_UNAUTHORIZED
    FORBIDDEN = status.HTTP_403_FORBIDDEN
    NOT_FOUND = status.HTTP_404_NOT_FOUND
    CONFLICT = status.HTTP_409_CONFLICT
    UNPROCESSABLE_ENTITY = status.HTTP_422_UNPROCESSABLE_ENTITY
    INTERNAL_SERVER_ERROR = status.HTTP_500_INTERNAL_SERVER_ERROR


# Error Message Templates
class ErrorMessages:
    """Standard error message templates."""

    # Not Found errors
    NOT_FOUND = "{entity} not found"
    NOT_FOUND_WITH_ID = "{entity} with ID {id} not found"

    # Already exists errors
    ALREADY_EXISTS = "{entity} already exists"
    DUPLICATE_ENTRY = "{entity} with {field} '{value}' already exists"

    # Conversion errors
    ALREADY_CONVERTED = "{entity} already converted"
    ALREADY_CONVERTED_TO = "{entity} already converted to {target}"

    # Permission errors
    PERMISSION_DENIED = "Permission denied"
    NOT_AUTHORIZED = "Not authorized to access this resource"

    # Validation errors
    INVALID_INPUT = "Invalid input provided"
    REQUIRED_FIELD = "{field} is required"
    INVALID_FORMAT = "Invalid format for {field}"

    @classmethod
    def not_found(cls, entity: str) -> str:
        """Generate a not found error message."""
        return cls.NOT_FOUND.format(entity=entity)

    @classmethod
    def not_found_with_id(cls, entity: str, entity_id: int) -> str:
        """Generate a not found error message with ID."""
        return cls.NOT_FOUND_WITH_ID.format(entity=entity, id=entity_id)

    @classmethod
    def already_converted(cls, entity: str) -> str:
        """Generate an already converted error message."""
        return cls.ALREADY_CONVERTED.format(entity=entity)

    @classmethod
    def already_converted_to(cls, entity: str, target: str) -> str:
        """Generate an already converted to target error message."""
        return cls.ALREADY_CONVERTED_TO.format(entity=entity, target=target)


# Entity names for consistent messaging
class EntityNames:
    """Standard entity names for error messages."""

    CONTACT = "Contact"
    COMPANY = "Company"
    LEAD = "Lead"
    OPPORTUNITY = "Opportunity"
    ACTIVITY = "Activity"
    CAMPAIGN = "Campaign"
    CAMPAIGN_MEMBER = "Campaign member"
    PIPELINE_STAGE = "Pipeline stage"
    LEAD_SOURCE = "Lead source"
    TAG = "Tag"
    USER = "User"
    NOTE = "Note"
    TENANT = "Tenant"
    TENANT_SETTINGS = "Tenant settings"
    TENANT_USER = "Tenant user"


# Pagination defaults
class PaginationDefaults:
    """Default pagination values."""

    DEFAULT_PAGE = 1
    DEFAULT_PAGE_SIZE = 20
    MIN_PAGE = 1
    MIN_PAGE_SIZE = 1
    MAX_PAGE_SIZE = 100
