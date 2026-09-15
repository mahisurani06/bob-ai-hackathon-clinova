"""
interface.py — Public integration boundary for the Site Risk Scoring module.

This is the ONLY file that the Streamlit dashboard (or any other consumer)
needs to import from Member 3's module.  It hides the data-loading pipeline
behind a single clean function, exactly mirroring the pattern established by
``src/protocol/interface.py``.

Intended usage
--------------
    from src.risk.interface import compute_site_risks

    scores = compute_site_risks()
    for s in scores:
        print(s.site_id, s.risk_score, s.risk_level, s.trend)

Or with an explicit data directory (useful in tests):

    from pathlib import Path
    from src.risk.interface import compute_site_risks

    scores = compute_site_risks(data_dir=Path("src/data"))

What this module does NOT do
-----------------------------
- It does not implement any scoring logic.  That lives in scorer.py.
- It does not define any data models.  Those live in models.py.
- It does not call any AI or external service.
- It does not write results to disk.
"""

from __future__ import annotations

from pathlib import Path

from src.deviation.detector   import detect_deviations
from src.protocol.interface   import load_project_data

from .models  import SiteRiskScore
from .scorer  import score_sites


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_site_risks(data_dir: Path | None = None) -> list[SiteRiskScore]:
    """Load data, detect deviations, and return a risk score for every site.

    This is the single entry point for the dashboard.  It orchestrates the
    full pipeline:

    1. Load and validate the clinical-trial dataset via Member 1's interface.
    2. Detect protocol deviations via Member 2's detector.
    3. Compute per-site risk scores via Member 3's scorer.

    The returned list is sorted by ``risk_score`` descending so the highest-
    risk sites appear first.

    Args:
        data_dir: Optional override for the root data directory.
                  Defaults to ``src/data/`` (resolved inside
                  :func:`~src.protocol.interface.load_project_data`).

    Returns:
        A list of :class:`~src.risk.models.SiteRiskScore` objects, one per
        site, sorted highest risk first.

    Raises:
        DataValidationError: If the loaded dataset fails validation.
        FileNotFoundError:   If a required data file is missing.

    Example::

        from src.risk.interface import compute_site_risks

        scores = compute_site_risks()
        print(scores[0])   # highest-risk site
    """
    data = load_project_data(data_dir)

    deviations = detect_deviations(
        observations   = data["observations"],
        protocol_rules = data["protocol_rules"],
    )

    return score_sites(
        deviations   = deviations,
        sites        = data["sites"],
        observations = data["observations"],
    )
