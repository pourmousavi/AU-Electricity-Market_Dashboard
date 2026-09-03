"""Economic dispatch pricing kit for Topic 5.

Shared by ed_price, ed_ramp and truthful_offers: one LP, one palette, one set
of zoom-legible styles. The three experiments differ in what they put on the
page, not in how the market is solved.

Notation follows the lectures: lambda is the balance-row multiplier, mu-bar and
mu-underbar the upper and lower capacity multipliers, nu the ramp multipliers,
Delta T = 1/12 h. Every multiplier this module returns is already scaled to
$/MWh; every cost is dollars per five-minute interval.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import streamlit as st
from scipy.optimize import linprog

# Deck standard. No other hues anywhere, Plotly traces included.
NAVY = "#140F50"
PURPLE = "#836BFF"
LAVENDER = "#ECE9FF"
SILVER = "#E9E6EE"
LIMESTONE = "#F8EFE0"
MUTED = "#6E6A8A"

DT = 1.0 / 12.0  # hours in one dispatch interval
PER_HOUR = 1.0 / DT  # multiplier taking $/interval-MW to $/MWh


@dataclass(frozen=True)
class Gen:
    name: str
    offer: float  # $/MWh
    capacity: float  # MW


# The fixed market all three experiments price against.
GENERATORS: tuple[Gen, ...] = (
    Gen("G1", 40.0, 1500.0),
    Gen("G2", 20.0, 1000.0),
    Gen("G3", 50.0, 1500.0),
)

TOTAL_CAPACITY = sum(g.capacity for g in GENERATORS)


@dataclass(frozen=True)
class Dispatch:
    """One solved horizon. Index order is always [interval][generator]."""
    ok: bool
    message: str
    P: tuple[tuple[float, ...], ...]
    lam: tuple[float, ...]
    mu_max: tuple[tuple[float, ...], ...]
    mu_min: tuple[tuple[float, ...], ...]
    # Ramp multipliers live on the step INTO interval t, so index 0 of these is
    # the t1-to-t2 step. Empty when the solve had no ramp rows.
    nu_up: tuple[tuple[float, ...], ...]
    nu_dn: tuple[tuple[float, ...], ...]
    cost: tuple[float, ...]  # dollars per five-minute interval, per interval

    @property
    def total_cost(self) -> float:
        return sum(self.cost)

    def payment(self, demands: Sequence[float]) -> float:
        """Sum of lambda_t x D_t x Delta T, in dollars over the horizon."""
        return sum(l * d * DT for l, d in zip(self.lam, demands))


def _status_message(status: int) -> str:
    """Why HiGHS returned nothing. 2 is infeasible, 3 unbounded."""
    if status == 2:
        return (
            "Infeasible: demand cannot be met inside the generator limits. "
            "Above total capacity there is nothing left to dispatch, and below "
            "the sum of the minimum loads the balance row cannot be satisfied."
        )
    if status == 3:
        return "Unbounded: the objective improves without limit."
    return "No feasible dispatch was found."


def solve(
    demands: Sequence[float],
    minimums: Sequence[float] = (0.0, 0.0, 0.0),
    ramps: Sequence[float] | None = None,
    gens: Sequence[Gen] = GENERATORS,
) -> Dispatch:
    """Minimise offered cost over the horizon.

    Capacity limits go in as explicit inequality ROWS rather than variable
    bounds so that mu-bar and mu-underbar come straight back out of
    ``r.ineqlin.marginals``, which is what the lectures write down. The
    variables themselves are left free.

    ``ramps`` is one RU = RD limit per generator, or None for no ramp coupling
    (which is also what makes the intervals separate).
    """
    n = len(gens)
    T = len(demands)
    N = n * T

    def idx(t: int, k: int) -> int:
        return t * n + k

    c = [0.0] * N
    for t in range(T):
        for k in range(n):
            c[idx(t, k)] = gens[k].offer * DT

    A_ub: list[list[float]] = []
    b_ub: list[float] = []
    for t in range(T):  # P <= Pmax, giving mu-bar
        for k in range(n):
            row = [0.0] * N
            row[idx(t, k)] = 1.0
            A_ub.append(row)
            b_ub.append(gens[k].capacity)
    for t in range(T):  # -P <= -Pmin, giving mu-underbar
        for k in range(n):
            row = [0.0] * N
            row[idx(t, k)] = -1.0
            A_ub.append(row)
            b_ub.append(-minimums[k])

    n_ramp_rows = 0
    if ramps is not None and T > 1:
        for t in range(1, T):
            for k in range(n):
                up = [0.0] * N
                up[idx(t, k)] = 1.0
                up[idx(t - 1, k)] = -1.0
                A_ub.append(up)
                b_ub.append(ramps[k])
                dn = [0.0] * N
                dn[idx(t, k)] = -1.0
                dn[idx(t - 1, k)] = 1.0
                A_ub.append(dn)
                b_ub.append(ramps[k])
        n_ramp_rows = 2 * n * (T - 1)

    A_eq = []
    for t in range(T):
        row = [0.0] * N
        for k in range(n):
            row[idx(t, k)] = 1.0
        A_eq.append(row)

    r = linprog(
        c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=list(demands),
        bounds=[(None, None)] * N, method="highs",
    )
    if not r.success:
        empty: tuple = ()
        return Dispatch(False, _status_message(r.status), empty, empty,
                        empty, empty, empty, empty, empty)

    # HiGHS reports marginals as d(objective)/d(rhs). The objective is dollars
    # per interval, so x PER_HOUR puts every multiplier in $/MWh. Raising a
    # capacity LOWERS cost, so the inequality marginals come back negative and
    # are negated here to give the non-negative mu the lectures write.
    lam = tuple(float(m) * PER_HOUR + 0.0 for m in r.eqlin.marginals)
    ineq = [-float(m) * PER_HOUR + 0.0 for m in r.ineqlin.marginals]

    P = tuple(
        tuple(float(r.x[idx(t, k)]) + 0.0 for k in range(n)) for t in range(T)
    )
    mu_max = tuple(tuple(ineq[t * n + k] for k in range(n)) for t in range(T))
    base = n * T
    mu_min = tuple(
        tuple(ineq[base + t * n + k] for k in range(n)) for t in range(T)
    )

    nu_up: list[tuple[float, ...]] = []
    nu_dn: list[tuple[float, ...]] = []
    if n_ramp_rows:
        base = 2 * n * T
        for step in range(T - 1):
            start = base + step * 2 * n
            nu_up.append(tuple(ineq[start + 2 * k] for k in range(n)))
            nu_dn.append(tuple(ineq[start + 2 * k + 1] for k in range(n)))

    cost = tuple(
        sum(gens[k].offer * P[t][k] * DT for k in range(n)) for t in range(T)
    )

    return Dispatch(True, "", P, lam, mu_max, mu_min,
                    tuple(nu_up), tuple(nu_dn), cost)


def staircase(
    minimums: Sequence[float] = (0.0, 0.0, 0.0),
    gens: Sequence[Gen] = GENERATORS,
) -> list[tuple[float, float, float]]:
    """The lambda staircase as (demand_from, demand_to, price) segments.

    Solved in closed form rather than by re-running the LP a few thousand
    times: with the minimum loads forced on, the rest of demand is filled from
    the cheapest headroom upwards, so lambda is the offer of whichever unit is
    supplying the increment. Riser positions are the cumulative headroom.
    """
    floor = sum(minimums)
    segments: list[tuple[float, float, float]] = []
    edge = floor
    order = sorted(range(len(gens)), key=lambda k: gens[k].offer)
    for k in order:
        headroom = gens[k].capacity - minimums[k]
        if headroom <= 0:
            continue
        segments.append((edge, edge + headroom, gens[k].offer))
        edge += headroom
    return segments


def price_at(demand: float, minimums: Sequence[float] = (0.0, 0.0, 0.0),
             gens: Sequence[Gen] = GENERATORS) -> float | None:
    """Lambda at one demand, or None if that demand is infeasible."""
    for lo, hi, price in staircase(minimums, gens):
        if lo - 1e-9 <= demand <= hi + 1e-9:
            return price
    return None


# --- Page furniture -------------------------------------------------------
#
# These pages are projected over Zoom to a second campus, so the sizes below
# are the floor, not a preference: headline numbers 28px and up, body text
# 16px and up, Plotly tick labels 14px and up.
#
# Every symbol a student reads goes through KaTeX, which means it has to reach
# the markdown parser as TEXT. Streamlit parses `$...$` on text nodes only: a
# block-level tag such as `<div>` opens an HTML block and everything to the
# next blank line becomes one opaque node, so maths inside it renders as the
# literal string `$\lambda$`. So the coloured boxes below are not wrappers at
# all. Each is an empty INLINE marker span that CSS finds with :has(), leaving
# the prose beside it as ordinary markdown for KaTeX to pick up.
CHART_FONT = dict(size=16, color=NAVY)
TICK_FONT = dict(size=14, color=NAVY)

# Plotly has no KaTeX in Streamlit, so chart furniture uses the Unicode
# letters instead. Same symbols the lectures use, just not typeset.
LAMBDA = "\u03bb"
NU = "\u03bd"


def css() -> None:
    """Scoped styles for the Topic 5 experiments."""
    st.markdown(
        f"""<style>
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] td,
[data-testid="stMarkdownContainer"] th {{
  font-size: 1.05rem; color: {NAVY};
}}
/* KaTeX sets its own size, so lift it explicitly or inline symbols end up
   smaller than the prose they sit in when projected. */
.katex {{ font-size: 1.14em; }}
.katex-display {{ margin: .5rem 0; }}

[data-testid="stMetric"] {{
  background: {LAVENDER}; border: 2px solid {SILVER};
  border-left: 8px solid {PURPLE}; border-radius: 12px;
  padding: .85rem 1.05rem;
}}
[data-testid="stMetricLabel"] p {{
  font-size: 1rem; font-weight: 700; color: {MUTED};
}}
[data-testid="stMetricValue"] {{
  font-size: 2.1rem; font-weight: 800; color: {NAVY};
}}

/* The marker spans themselves never show; they exist for :has() to find. */
.ed-mark {{ display: none; }}
[data-testid="stElementContainer"]:has(.ed-mark-note) {{
  background: {LIMESTONE}; border-left: 8px solid {NAVY};
  border-radius: 12px; padding: .9rem 1.2rem; margin: .7rem 0;
}}
[data-testid="stElementContainer"]:has(.ed-mark-row) {{
  background: #FFFFFF; border: 2px solid {SILVER};
  border-radius: 12px; padding: .7rem 1.1rem; margin-bottom: .5rem;
}}
[data-testid="stElementContainer"]:has(.ed-mark-marginal) {{
  background: {LAVENDER}; border-color: {PURPLE};
}}
.ed-flag {{
  display: inline-block; background: {LIMESTONE}; color: {NAVY};
  border: 2px solid {PURPLE}; border-radius: 99px;
  padding: .1rem .6rem; font-size: 1rem; font-weight: 700;
}}
.ed-table table {{ width: 100%; border-collapse: collapse; }}
.ed-table th, .ed-table td {{
  padding: .45rem .6rem; text-align: center; font-size: 1.05rem;
  color: {NAVY}; border-bottom: 1px solid {SILVER};
}}
.ed-table th {{ border-bottom: 2px solid {SILVER}; }}
.ed-table th:first-child {{ text-align: left; }}
</style>""",
        unsafe_allow_html=True,
    )


def _marked(marker: str, md: str) -> None:
    """Emit `md` in a box CSS draws around it.

    The span and the first line of `md` share a line deliberately. A line
    holding nothing but a tag would start an HTML BLOCK and swallow the maths
    after it; a tag with text beside it stays inline, so `md` is parsed as
    ordinary markdown and its `$...$` reaches KaTeX.
    """
    st.markdown(f'<span class="ed-mark {marker}"></span>{md.lstrip()}',
                unsafe_allow_html=True)


def note(md: str) -> None:
    """A limestone banner. `md` may contain LaTeX."""
    _marked("ed-mark-note", md)


def row(md: str, marginal: bool = False) -> None:
    """One boxed row. `marginal` tints it lavender for the price setter."""
    _marked("ed-mark-row" + (" ed-mark-marginal" if marginal else ""), md)


def headline(label: str, value: str) -> None:
    """A big number. The label is markdown, so it may contain LaTeX."""
    st.metric(label, value)


def money(value: float) -> str:
    return f"{value:,.2f}"


def header(title: str, subtitle: str) -> None:
    """The common page opening: course identity, then what this page is."""
    css()
    st.markdown(
        f'<div style="color:{MUTED};font-size:1rem;letter-spacing:.08em;'
        'text-transform:uppercase;font-weight:700">'
        "ENGE X406 Electricity Market and Power System Operations</div>",
        unsafe_allow_html=True,
    )
    st.title(title)
    st.markdown(subtitle)
