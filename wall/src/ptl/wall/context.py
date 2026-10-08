"""Who is who: classify an email address into a TargetClass.

Security rules followed here:
  * Classification is pure code over a frozen snapshot. No LLM, no reading of email bodies.
  * Exact domain match only. "bluesparrowtech.com.evil.com" is NOT internal.
  * Anything odd (non-ASCII, several addresses in one string, bad format) is UNKNOWN,
    and UNKNOWN can never be granted, so odd input always fails closed.
"""

from __future__ import annotations

import re
from typing import Iterable

from pydantic import BaseModel, ConfigDict, field_validator

from .models import TargetClass

_EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9\-]+(\.[a-z0-9\-]+)+$")
_ANGLE_RE = re.compile(r"<([^<>]*)>")


def normalize_address(raw: object) -> str | None:
    """Return a clean lowercase address, or None if it is not exactly one valid address."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    angle = _ANGLE_RE.findall(text)
    if len(angle) > 1:
        return None
    if len(angle) == 1:                     # "Bob Smith <bob@x.com>"
        text = angle[0].strip()
    text = text.lower()
    if not text.isascii() or not _EMAIL_RE.match(text):
        return None
    return text


class WallContext(BaseModel):
    """A frozen snapshot of who the user trusts, taken when the user confirms the Wall."""

    model_config = ConfigDict(frozen=True)

    account_email: str
    trusted_contacts: frozenset[str] = frozenset()
    trusted_domains: frozenset[str] = frozenset()

    @field_validator("account_email")
    @classmethod
    def _clean_account(cls, v: str) -> str:
        clean = normalize_address(v)
        if clean is None:
            raise ValueError(f"invalid account email: {v!r}")
        return clean

    @field_validator("trusted_contacts")
    @classmethod
    def _clean_contacts(cls, v: frozenset[str]) -> frozenset[str]:
        return frozenset(a for a in (normalize_address(x) for x in v) if a)

    @field_validator("trusted_domains")
    @classmethod
    def _clean_domains(cls, v: frozenset[str]) -> frozenset[str]:
        return frozenset(d.strip().lower() for d in v if d and d.strip())

    def classify(self, raw: object) -> TargetClass:
        addr = normalize_address(raw)
        if addr is None:
            return TargetClass.UNKNOWN
        if addr == self.account_email:
            return TargetClass.SELF
        domain = addr.rsplit("@", 1)[1]
        if domain in self.trusted_domains:
            return TargetClass.INTERNAL
        if addr in self.trusted_contacts:
            return TargetClass.CONTACT
        return TargetClass.EXTERNAL

    @classmethod
    def for_account(
        cls,
        account_email: str,
        contacts: Iterable[str] = (),
        extra_domains: Iterable[str] = (),
        trust_own_domain: bool = True,
    ) -> "WallContext":
        acct = normalize_address(account_email)
        if acct is None:
            raise ValueError(f"invalid account email: {account_email!r}")
        domains = set(extra_domains)
        if trust_own_domain:
            domains.add(acct.rsplit("@", 1)[1])
        return cls(
            account_email=acct,
            trusted_contacts=frozenset(contacts),
            trusted_domains=frozenset(domains),
        )

    @classmethod
    def from_agentdojo_env(cls, env: object, extra_domains: Iterable[str] = ()) -> "WallContext":
        """Snapshot an AgentDojo Workspace environment (env.inbox.account_email, env.inbox.contact_list).

        Take this snapshot ONCE, at the start, from the clean pre-environment. AgentDojo
        auto-builds contact_list from email participants, so re-reading it mid-run could
        let an address that appeared in an attacker's email become a "contact".
        """
        inbox = getattr(env, "inbox")
        contacts = [str(getattr(c, "email", "")) for c in getattr(inbox, "contact_list", [])]
        return cls.for_account(str(inbox.account_email), contacts, extra_domains)
