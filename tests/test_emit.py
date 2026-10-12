"""Emission: fixtures 26 and 28 of docs/reference/fixtures.md, the emit() parts of
fixtures 6 and 19, and the policy, message text and warning classes of section 11.
"""

import contextlib
import contextvars
import logging
import threading
import warnings

import pytest

import queryearth as qe
from queryearth import space as sp


def finding(code="CRU001", kind="caveat", severity="warning", **fields):
    return qe.Finding(
        code=code,
        kind=kind,
        title=f"{code} title",
        message="m",
        severity=severity,
        **fields,
    )


CRU001 = finding(query_label="lake 1234", area_fraction=1.0, product="cru_ts")
CROC102 = finding("CROC102", "recommendation", "info")
GEN001 = finding("GEN001", severity="info")


@contextlib.contextmanager
def logged():
    """Records of the queryearth logger at INFO and above, and warnings raised."""
    records = []
    handler = logging.Handler(logging.INFO)
    handler.emit = records.append
    logger = logging.getLogger("queryearth")
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            yield records, caught
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)


# ---- fixture 26: emitting recommendations ------------------------------------------
def test_fixture_26_recommendations_are_logged_at_info():
    with logged() as (records, caught):
        shown = qe.emit([CROC102, GEN001])
    assert shown == [CROC102] and caught == []
    (record,) = records
    assert record.levelno == logging.INFO and record.finding is CROC102
    assert record.getMessage() == "[CROC102] CROC102 title (draft)"
    with logged() as (records, caught):
        assert qe.emit([CROC102, GEN001], show_recommendations=False) == []
    assert records == [] and caught == []
    with logged() as (records, caught):
        assert qe.emit([CROC102], mode="raise") == [CROC102]
    assert len(records) == 1 and caught == []


# ---- fixture 28: an emission sink ---------------------------------------------------
def test_fixture_28_a_sink_receives_every_kept_finding():
    sunk = []

    def sink(f, text):
        sunk.append((f.code, text))

    with logged() as (records, caught):
        assert qe.emit([CRU001, CROC102], mode=sink) == [CRU001, CROC102]
    assert sunk == [
        ("CRU001", "[CRU001] CRU001 title (lake 1234; area 100%; draft)"),
        ("CROC102", "[CROC102] CROC102 title (draft)"),
    ]
    assert records == [] and caught == []
    sunk.clear()
    with pytest.raises(qe.AdvisoryError) as err:
        qe.emit([CRU001, CROC102], mode=sink, raise_at=qe.Severity.WARNING)
    assert [code for code, _ in sunk] == ["CROC102"]
    assert err.value.findings == (CRU001,)


# ---- the emit() parts of fixtures 6 and 19 -----------------------------------------
def test_fixture_6_min_overlap_decides_whether_a_touching_box_is_emitted():
    for minimum, expected in ((0.0, 1), (0.01, 0)):
        index = qe.Index("geo")
        index.add(
            qe.Rule(
                code="SQR001",
                kind="caveat",
                title="t",
                message="m",
                min_overlap=minimum,
                scope=qe.Scope(space=sp.box(0, 0, 10, 10)),
            )
        )
        (touching,) = index.query(space=sp.box(10, 0, 20, 10))
        assert touching.area_fraction == 0.0
        with logged() as (_, caught):
            assert len(qe.emit([touching])) == expected
        assert len(caught) == expected


def test_fixture_19_conditional_findings_are_never_emitted():
    index = qe.Index("x", axes=[qe.Axis("resolution", "km")])
    index.add_product(qe.Product("cru_ts", version="4.07"))
    index.add(
        qe.Rule(
            code="CRU001",
            kind="caveat",
            title="t",
            message="m",
            severity="severe",
            scope=qe.Scope(
                space=sp.box(10, -10, 30, 10),
                time=qe.interval("2000-01-01", ".."),
                facets={"product": ["cru_ts"], "version": {"versions": ["4.07"]}},
            ),
        )
    )
    found = index.query(axes={"resolution": 8.0}, include_conditional=True)
    assert found and all(f.conditional_on for f in found)
    with logged() as (records, caught):
        assert qe.emit(found, mode="raise") == []
    assert records == [] and caught == []


# ---- modes, policy and text -----------------------------------------------------------
def test_warn_mode_uses_one_category_per_severity_and_carries_the_finding():
    severe = finding(
        "ERA5-023", severity="severe", time_overlap=[("2007-10-01", "2013-12-31")]
    )
    with logged() as (records, caught):
        shown = qe.emit([CRU001, severe, GEN001], min_severity="info")
    assert shown == [CRU001, severe, GEN001] and records == []
    categories = [w.category for w in caught]
    assert categories == [qe.WarningAdvisory, qe.SevereAdvisory, qe.InfoAdvisory]
    assert all(issubclass(c, qe.AdvisoryWarning) for c in categories)
    assert caught[1].message.finding is severe
    assert str(caught[1].message) == (
        "[ERA5-023] ERA5-023 title (2007-10-01..2013-12-31; draft)"
    )
    assert caught[0].filename == __file__  # the warning names the caller's line


def test_filters_ignore_drafts_and_repeats():
    reviewed = finding("CRU004", status="reviewed")
    twice = [CRU001, CRU001, finding(product="era5", query_label="lake 1234")]
    with logged() as (records, caught):
        assert qe.emit(twice) == [twice[0], twice[2]]  # one per (code, label, product)
        assert qe.emit([CRU001, reviewed, CROC102], ignore={"CRU0"}) == [CROC102]
        assert qe.emit([CRU001, reviewed], include_drafts=False) == [reviewed]
        assert qe.emit([CRU001, CROC102], mode="ignore") == []
    assert len(caught) == 3 and len(records) == 1


def test_codes_can_be_silenced_with_warning_filters():
    with logged() as (_, caught):
        warnings.filterwarnings("ignore", message=r"\[CRU001\]")
        qe.emit([CRU001, finding("CRU004")])
    assert [str(w.message)[:8] for w in caught] == ["[CRU004]"]


def test_log_mode_with_raise_at_reports_first_then_raises_together():
    qe001 = finding("QE001", "coverage", "severe", product="nwm_retro")
    qe002 = finding("QE002", "coverage", "severe", product="nwm_retro")
    with logged() as (records, caught):
        with pytest.raises(qe.AdvisoryError) as err:
            qe.emit([CRU001, qe001, qe002, CROC102], mode="log", raise_at="severe")
    assert err.value.findings == (qe001, qe002)
    assert str(err.value).splitlines()[0].startswith("[QE001]")
    assert [(r.levelno, r.finding.code) for r in records] == [
        (logging.WARNING, "CRU001"),
        (logging.INFO, "CROC102"),
    ]
    assert caught == []


def test_policy_is_a_context_variable():
    seen = []

    def worker():
        with qe.policy() as active:
            seen.append(active.mode)

    with qe.policy(mode="log", ignore={"GEN"}) as active:
        assert active.mode == "log" and active.ignore == frozenset({"GEN"})
        context = contextvars.copy_context()  # carries the policy into a thread
        thread = threading.Thread(target=context.run, args=(worker,))
        thread.start()
        thread.join()
        with logged() as (records, caught):
            qe.emit([CRU001, GEN001], min_severity="info")
        assert [r.finding.code for r in records] == ["CRU001"] and caught == []
        with pytest.raises(qe.AdvisoryError):
            with qe.policy(mode="raise"):
                qe.emit([CRU001])
    assert seen == ["log"]
    with qe.policy() as default:
        assert default == qe.Policy()
    with pytest.raises(ValueError):
        qe.Policy(mode="shout")
