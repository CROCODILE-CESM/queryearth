"""Emission: findings as log records, warnings, one exception or a sink (section 11).

The active Policy lives in a contextvars.ContextVar, so a policy set in one
thread or asyncio task never changes another (copy_context().run carries it).
"""

from __future__ import annotations

import contextlib
import contextvars
import dataclasses
import logging
import sys
import warnings
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Literal

from queryearth.objects import Finding, Severity, severity_of

__all__ = [
    "AdvisoryError",
    "AdvisoryWarning",
    "InfoAdvisory",
    "Policy",
    "SevereAdvisory",
    "Sink",
    "WarningAdvisory",
    "emit",
    "message",
    "policy",
]

logger = logging.getLogger("queryearth")
MODES = ("log", "warn", "raise", "ignore")
Sink = Callable[[Finding, str], None]  # receives each kept finding and its text


class AdvisoryWarning(UserWarning):
    """A finding emitted as a warning; the instance carries it as .finding."""

    finding: Finding | None = None


class InfoAdvisory(AdvisoryWarning):
    """An INFO finding emitted as a warning."""


class WarningAdvisory(AdvisoryWarning):
    """A WARNING finding emitted as a warning."""


class SevereAdvisory(AdvisoryWarning):
    """A SEVERE finding emitted as a warning."""


_CATEGORY = dict(zip(Severity, (InfoAdvisory, WarningAdvisory, SevereAdvisory)))


class AdvisoryError(Exception):
    """Raised by emit() once for every blocking finding; .findings holds them."""

    def __init__(self, findings: Iterable[Finding]) -> None:
        self.findings = tuple(findings)
        super().__init__("\n".join(message(f) for f in self.findings))


@dataclass(frozen=True)
class Policy:
    """How emit() reports findings (section 11.1); emit() documents each field.

    skip_packages names packages, besides queryearth, whose frames a warning
    or log record should not point at.
    """

    mode: Literal["log", "warn", "raise", "ignore"] | Sink = "warn"
    min_severity: Severity = Severity.WARNING
    raise_at: Severity | None = None
    ignore: frozenset[str] = frozenset()
    include_drafts: bool = True
    show_recommendations: bool = True  # log them at INFO in every mode but ignore
    skip_packages: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not callable(self.mode) and self.mode not in MODES:
            raise ValueError(f"mode is one of {MODES} or a sink, not {self.mode!r}")
        object.__setattr__(self, "min_severity", severity_of(self.min_severity))
        if self.raise_at is not None:
            object.__setattr__(self, "raise_at", severity_of(self.raise_at))
        ignore = (self.ignore,) if isinstance(self.ignore, str) else self.ignore
        object.__setattr__(self, "ignore", frozenset(ignore))
        object.__setattr__(self, "skip_packages", tuple(self.skip_packages))


_ACTIVE = contextvars.ContextVar("queryearth_policy", default=Policy())


@contextlib.contextmanager
def policy(**changes: Any) -> Iterator[Policy]:
    """Install a copy of the active Policy with changes for a with block."""
    token = _ACTIVE.set(dataclasses.replace(_ACTIVE.get(), **changes))
    try:
        yield _ACTIVE.get()
    finally:
        _ACTIVE.reset(token)


def message(finding: Finding) -> str:
    """The text of a finding: "[CODE] title (label; area 40%; periods; draft)"."""
    notes = [finding.query_label] if finding.query_label else []
    if finding.area_fraction is not None:
        notes.append(f"area {finding.area_fraction:.0%}")
    if finding.time_overlap:
        notes.append(", ".join(f"{a}..{b}" for a, b in finding.time_overlap))
    if finding.status == "draft":
        notes.append("draft")
    return f"[{finding.code}] {finding.title}" + (
        f" ({'; '.join(notes)})" if notes else ""
    )


def _stacklevel(skip: tuple[str, ...]) -> int:
    """The stacklevel, from emit(), of the first frame outside queryearth and skip."""
    packages = ("queryearth", *skip)
    frame, level = sys._getframe(1), 1  # emit() itself is level 1
    while frame is not None:
        name = frame.f_globals.get("__name__", "")
        if not any(name == p or name.startswith(p + ".") for p in packages):
            break
        frame, level = frame.f_back, level + 1
    return level


def emit(
    findings: Iterable[Finding], mode: Any = None, **changes: Any
) -> list[Finding]:
    """Report findings under the active policy; returns those logged, warned or sunk.

    mode and changes override the policy for this call. Dropped: conditional
    findings, caveats and coverage below min_severity, area_fraction below
    min_overlap, codes or prefixes in ignore, drafts unless include_drafts,
    recommendations unless show_recommendations, and repeats of (code,
    query_label, product). Recommendations are logged at INFO or sunk, never
    warned or raised; in "raise" mode, or at or above raise_at, caveats and
    coverage findings are raised together after the rest are reported.
    """
    active = dataclasses.replace(
        _ACTIVE.get(), **changes, **({} if mode is None else {"mode": mode})
    )
    if active.mode == "ignore":
        return []
    kept, seen = [], set()
    for f in findings:
        advice = f.kind == "recommendation"
        key = (f.code, f.query_label, f.product)
        if (
            f.conditional_on
            or key in seen
            or (advice and not active.show_recommendations)
            or (not advice and f.severity < active.min_severity)
            or (f.area_fraction is not None and f.area_fraction < f.min_overlap)
            or any(f.code.startswith(p) for p in active.ignore)
            or (f.status == "draft" and not active.include_drafts)
        ):
            continue
        seen.add(key)
        kept.append(f)
    level = _stacklevel(active.skip_packages)
    shown, blocking = [], []
    for f in kept:
        text, advice = message(f), f.kind == "recommendation"
        if not advice and (
            active.mode == "raise"
            or (active.raise_at is not None and f.severity >= active.raise_at)
        ):
            blocking.append(f)
            continue
        if callable(active.mode):
            active.mode(f, text)
        elif advice or active.mode == "log":
            severity = logging.INFO if advice else int(f.severity)
            logger.log(severity, text, extra={"finding": f}, stacklevel=level)
        else:
            warning = _CATEGORY[f.severity](text)
            warning.finding = f
            warnings.warn(warning, stacklevel=level)
        shown.append(f)
    if blocking:
        raise AdvisoryError(blocking)
    return shown
