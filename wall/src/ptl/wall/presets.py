"""Ready-made policies for experiments.

STRICT_WORKSPACE matches the running example in our pitch:
  "Handle my email and calendar. Only email people in my contacts.
   Never share files outside work. Never delete anything."
"""

from __future__ import annotations

from .models import Capability as C
from .models import TargetClass as T
from .policy import Grant, WallPolicy

STRICT_WORKSPACE = WallPolicy(
    description=(
        "Handle my email and calendar. Only email people in my contacts. "
        "Never share files outside work. Never delete anything."
    ),
    grants=(
        Grant(capability=C.READ, targets=frozenset({T.SELF})),
        Grant(capability=C.CREATE, targets=frozenset({T.SELF, T.INTERNAL, T.CONTACT})),
        Grant(capability=C.MODIFY, targets=frozenset({T.SELF, T.INTERNAL, T.CONTACT})),
        Grant(capability=C.SEND, targets=frozenset({T.SELF, T.INTERNAL, T.CONTACT})),
        Grant(capability=C.SHARE, targets=frozenset({T.INTERNAL})),
    ),
    attachments_allowed_to=frozenset({T.SELF, T.INTERNAL}),
    max_recipients=10,
    max_share_permission="r",
)

# Baseline for the "no protection" setup: allows every capability to every valid target.
ALLOW_ALL = WallPolicy(
    description="No limits (baseline only).",
    grants=tuple(
        Grant(capability=c, targets=frozenset({T.SELF, T.INTERNAL, T.CONTACT, T.EXTERNAL}))
        for c in C
    ),
    attachments_allowed_to=frozenset({T.SELF, T.INTERNAL, T.CONTACT, T.EXTERNAL}),
    max_share_permission="rw",
)
