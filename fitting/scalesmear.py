"""
scalesmear.py
-------------
Utilities for applying affine (shift + scale) morphing to 1D histograms,
primarily used to model jet mass scale (JMS) and jet mass resolution (JMR)
systematic variations in CMS analyses.

Classes
-------
AffineMorphTemplate
    Morphs a histogram by shifting and/or scaling its mass axis.
MorphHistW2
    Wraps AffineMorphTemplate to propagate sumw2 (bin variance) alongside
    bin contents through the same morphing.

Functions
---------
poisson_interval  : Garwood frequentist coverage interval for weighted histograms.
export1d          : Convert a (sumw, edges[, sumw2]) tuple to a boost-histogram.
mdev              : Compute the mean and standard deviation of a histogram.
"""

from __future__ import annotations

import warnings

import boost_histogram as bh
import numpy as np
import scipy.stats
from scipy.interpolate import interp1d

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# One-sigma central coverage for a normal distribution (~68.27%)
_COVERAGE_1SD: float = scipy.stats.norm.cdf(1) - scipy.stats.norm.cdf(-1)

# Histogram tuple type alias for readability: (sumw, edges) or (sumw, edges, sumw2)
HistTuple = tuple[np.ndarray, np.ndarray]
HistTupleW2 = tuple[np.ndarray, np.ndarray, np.ndarray]


def poisson_interval(
    sumw: np.ndarray,
    sumw2: np.ndarray,
    coverage: float = _COVERAGE_1SD,
) -> np.ndarray:
    """Frequentist (Garwood) coverage interval for Poisson-distributed observations.

    For weighted data the observed count is approximated as ``sumw**2 / sumw2``,
    which rescales the unweighted Poisson interval by the mean weight per bin.
    Empty bins borrow the scale factor from the nearest non-empty neighbour.
    If *all* bins are empty a ``RuntimeWarning`` is issued and the interval
    collapses to ``sumw``.

    Parameters
    ----------
    sumw:
        Array of summed weights (one entry per bin).
    sumw2:
        Array of summed squared weights (one entry per bin).
    coverage:
        Central coverage fraction. Defaults to the 1-sigma normal interval
        (~68.27%).

    Returns
    -------
    np.ndarray, shape (2, nbins)
        Row 0 is the lower bound; row 1 is the upper bound.

    References
    ----------
    * Garwood (1936) via https://www.ine.pt/revstat/pdf/rs120203.pdf  # codespell:ignore ine
    * http://ms.mcmaster.ca/peter/s743/poissonalpha.html
    * Weighted-data treatment: https://arxiv.org/pdf/1309.1287.pdf
    * Originally adapted from Coffea.
    """
    scale = np.empty_like(sumw)
    filled = sumw != 0
    scale[filled] = sumw2[filled] / sumw[filled]

    empty = ~filled
    if empty.any():
        available = np.nonzero(sumw)
        if len(available[0]) == 0:
            warnings.warn(
                "All sumw are zero! Cannot compute meaningful error bars.",
                RuntimeWarning,
                stacklevel=2,
            )
            return np.vstack([sumw, sumw])

        missing = np.where(empty)
        # For each empty bin find the nearest non-empty bin (Euclidean distance).
        nearest_idx = np.sum(
            [np.subtract.outer(d, d0) ** 2 for d, d0 in zip(available, missing)]
        ).argmin(axis=0)
        nearest = tuple(dim[nearest_idx] for dim in available)
        scale[missing] = scale[nearest]

    counts = sumw / scale
    lo = scale * scipy.stats.chi2.ppf((1 - coverage) / 2, 2 * counts) / 2.0
    hi = scale * scipy.stats.chi2.ppf((1 + coverage) / 2, 2 * (counts + 1)) / 2.0

    interval = np.array([lo, hi])
    interval = np.nan_to_num(interval, nan=0.0)
    return interval


# ---------------------------------------------------------------------------
# Morphing classes
# ---------------------------------------------------------------------------


class AffineMorphTemplate:
    """Apply an affine transformation to the mass axis of a 1D histogram.

    The transformation maps each bin edge ``x`` to ``(x - shift) / scale``,
    which is equivalent to shifting the *distribution* by ``+shift`` and
    widening it by ``scale``. The total normalisation is preserved.

    Parameters
    ----------
    hist:
        A ``(sumw, edges)`` tuple where *sumw* has length ``len(edges) - 1``.
    """

    def __init__(self, hist: HistTuple) -> None:
        self.sumw, self.edges = hist
        self.centers: np.ndarray = self.edges[:-1] + np.diff(self.edges) / 2.0

        self.norm: float = float(self.sumw.sum())
        self.mean: float = float((self.sumw * self.centers).sum() / self.norm)

        # Build a CDF interpolant over bin edges for fast morphing.
        self._cdf = interp1d(
            x=self.edges,
            y=np.r_[0.0, np.cumsum(self.sumw / self.norm)],
            kind="linear",
            assume_sorted=True,
            bounds_error=False,
            fill_value=(0.0, 1.0),
        )

    def get(self, shift: float = 0.0, scale: float = 1.0) -> HistTuple:
        """Return a morphed copy of the histogram.

        The physical interpretation is:
        * ``shift > 0``: distribution moves to higher mass.
        * ``scale > 1``: distribution becomes wider (poorer resolution).

        When ``scale != 1`` the shift is adjusted so that the *mean* of the
        distribution is preserved under pure scaling (i.e. the scale pivots
        around the mean).

        Parameters
        ----------
        shift:
            Additive offset applied to the mass axis (same units as the axis).
        scale:
            Multiplicative factor applied to the mass axis.

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            ``(morphed_sumw, original_edges)`` — edges are unchanged.
        """
        if not np.isclose(scale, 1.0):
            # Pivot the scale around the distribution mean so that a pure
            # rescaling does not shift the peak position.
            shift += self.mean * (1.0 - scale)

        morphed_edges = (self.edges - shift) / scale
        morphed_sumw = np.diff(self._cdf(morphed_edges)) * self.norm
        return morphed_sumw, self.edges

    def rescale(self, factor: float) -> None:
        """Multiply the total normalisation by *factor* in-place."""
        self.norm *= factor


class MorphHistW2:
    """Affine morphing that propagates bin variances (sumw2) alongside bin contents.

    Both the bin-content histogram and the variance histogram are morphed
    independently using :class:`AffineMorphTemplate`, so the output retains
    proper statistical uncertainties after morphing.

    Parameters
    ----------
    hist:
        Either an uproot/UHI histogram object (must expose ``.values()``,
        ``.axes[0].edges()``, and ``.variances()``) or a plain
        ``(sumw, edges, sumw2)`` tuple.
    """

    def __init__(self, hist: HistTupleW2) -> None:
        self._original = hist

        # Accept both UHI histogram objects and raw (sumw, edges, sumw2) tuples.
        try:
            sumw = hist.values()
            edges = hist.axes[0].edges()
            sumw2 = hist.variances()
        except AttributeError:
            sumw, edges, sumw2 = hist

        self._nominal = AffineMorphTemplate((sumw, edges))
        self._variances = AffineMorphTemplate((sumw2, edges))

    def get(self, shift: float = 0.0, scale: float = 1.0) -> HistTupleW2:
        """Return morphed ``(sumw, edges, sumw2)`` for the given shift and scale.

        Parameters
        ----------
        shift:
            Additive offset on the mass axis (same units as axis).
        scale:
            Multiplicative factor on the mass axis.

        Returns
        -------
        tuple[np.ndarray, np.ndarray, np.ndarray]
            ``(morphed_sumw, edges, morphed_sumw2)``.
        """
        morphed_sumw, edges = self._nominal.get(shift, scale)
        morphed_sumw2, _ = self._variances.get(shift, scale)
        return morphed_sumw, edges, morphed_sumw2


# ---------------------------------------------------------------------------
# ROOT / boost-histogram I/O helpers
# ---------------------------------------------------------------------------


def export1d(hist: HistTuple | HistTupleW2) -> bh.Histogram:
    """Convert a histogram tuple to a weighted boost-histogram.

    Parameters
    ----------
    hist:
        Either ``(sumw, edges)`` or ``(sumw, edges, sumw2)``.  When only two
        elements are provided, ``sumw2`` defaults to ``sumw`` (i.e. unweighted
        Poisson statistics are assumed).

    Returns
    -------
    bh.Histogram
        A variable-bin weighted histogram compatible with uproot's ``recreate``.
    """
    if len(hist) == 3:
        sumw, edges, sumw2 = hist
    else:
        sumw, edges = hist
        sumw2 = sumw.copy()

    h = bh.Histogram(bh.axis.Variable(edges), storage=bh.storage.Weight())
    h.view().value = sumw
    h.view().variance = sumw2
    return h


def mdev(hist: HistTuple) -> np.ndarray:
    """Return the mean and standard deviation of a 1D histogram.

    Parameters
    ----------
    hist:
        ``(sumw, edges)`` tuple.

    Returns
    -------
    np.ndarray, shape (2,)
        ``[mean, std_dev]``.
    """
    sumw, edges = hist
    total = sumw.sum()
    centers = edges[:-1] + 0.5 * np.diff(edges)
    mean = (sumw * centers).sum() / total
    variance = (sumw * (centers - mean) ** 2).sum() / total
    return np.array([mean, np.sqrt(variance)])
