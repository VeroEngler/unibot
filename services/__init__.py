"""Server administration services for the UNAHUR Discord bot."""

from .channels import create_subject_channels, delete_subject_channels
from .metrics import update_metrics_board
from .notices import delete_notes_notices, send_notes_notices
from .roles import create_subject_roles, delete_subject_roles

__all__ = [
    "create_subject_channels",
    "delete_subject_channels",
    "create_subject_roles",
    "delete_subject_roles",
    "send_notes_notices",
    "delete_notes_notices",
    "delete_subject_channels",
    "update_metrics_board",
]