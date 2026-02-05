from src.core.mixins.auditable import AuditableMixin, TimestampMixin
from src.core.mixins.crm_note import CRMNoteMixin
from src.core.mixins.taggable import TaggableMixin
from src.core.base_service import BaseService, CRUDService, TaggableServiceMixin
from src.core.constants import (
    DEFAULT_CURRENCY,
    DEFAULT_COLOR,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ENTITY_TYPE_CONTACTS,
    ENTITY_TYPE_COMPANIES,
    ENTITY_TYPE_LEADS,
    ENTITY_TYPE_OPPORTUNITIES,
    ENTITY_TYPE_ACTIVITIES,
    ENTITY_TYPE_CAMPAIGNS,
    HTTPStatus,
    ErrorMessages,
    EntityNames,
    PaginationDefaults,
)
from src.core.schemas import (
    TagBrief,
    PaginatedResponse,
    PaginationParams,
    SuccessResponse,
    ErrorResponse,
    DeleteResponse,
)

# Note: router_utils is imported separately in routers to avoid circular imports
# Use: from src.core.router_utils import DBSession, CurrentUser, etc.

__all__ = [
    # Mixins
    "AuditableMixin",
    "TimestampMixin",
    "CRMNoteMixin",
    "TaggableMixin",
    # Base Services
    "BaseService",
    "CRUDService",
    "TaggableServiceMixin",
    # Constants
    "DEFAULT_CURRENCY",
    "DEFAULT_COLOR",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "ENTITY_TYPE_CONTACTS",
    "ENTITY_TYPE_COMPANIES",
    "ENTITY_TYPE_LEADS",
    "ENTITY_TYPE_OPPORTUNITIES",
    "ENTITY_TYPE_ACTIVITIES",
    "ENTITY_TYPE_CAMPAIGNS",
    "HTTPStatus",
    "ErrorMessages",
    "EntityNames",
    "PaginationDefaults",
    # Schemas
    "TagBrief",
    "PaginatedResponse",
    "PaginationParams",
    "SuccessResponse",
    "ErrorResponse",
    "DeleteResponse",
]
