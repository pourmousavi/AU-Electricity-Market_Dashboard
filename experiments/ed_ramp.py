"""Three-interval dispatch: what ramp coupling does to prices (Topic 5, block three).

Without a ramp row the horizon separates and each interval is its own little
market. Add the ramp row and the intervals stop being separable: lambda in one
interval starts paying for movements in the others, and prices appear that no
one offered.
"""
from __future__ import annotations

import streamlit as st

from experiments._kit import ed

T = 3
DEMAND_KEYS = ("edr_d1", "edr_d2", "edr_d3")
RAMP_KEYS = ("edr_ru1", "edr_ru2", "edr_ru3")
RAMPS_ON_KEY = "edr_ramps_on"
PROBE_KEY = "edr_probe"

DEFAULT_DEMANDS = (2600, 2540, 2450)
DEFAULT_RAMPS = (45, 20, 40)

DEFAULTS = {
    **dict(zip(DEMAND_KEYS, DEFAULT_DEMANDS)),
    **dict(zip(RAMP_KEYS, DEFAULT_RAMPS)),
    RAMPS_ON_KEY: True,
}

OFFERS = {gen.offer for gen in ed.GENERATORS}


def _price_cell(lam: float) -> str:
    """Lambda, in purple when it matches no offer in the market."""
    invented = not any(abs(lam - offer) < 1e-6 for offer in OFFERS)
    colour = ed.PURPLE if invented else ed.NAVY
    weight = 800 if invented else 600
    return (
        f'<span style="color:{colour};font-weight:{weight};font-size:1.15rem">'
        f"{lam:,.2f}</span>"
    )


def _violations(result: ed.Dispatch, ramps) -> list[tuple[int, int, float]]:
    """Steps the plan takes that no ramp limit would allow: (step, gen, MW)."""
    out = []
    for t in range(1, len(result.P)):
        for k, gen in enumerate(ed.GENERATORS):
            move = result.P[t][k] - result.P[t - 1][k]
            if abs(move) > ramps[k] + 1e-6:
                out.append((t, k, move))
    return out


TH = ("padding:.45rem .6rem;text-align:center;font-size:1.05rem;"
      f"border-bottom:2px solid {ed.SILVER};color:{ed.NAVY}")
TD = ("padding:.45rem .6rem;text-align:center;font-size:1.05rem;"
      f"border-bottom:1px solid {ed.SILVER};color:{ed.NAVY}")
TH_LEFT = TH.replace("text-align:center", "text-align:left")


def _plan_table(result: ed.Dispatch, demands, ramps, flag: bool) -> str:
    """One column per interval: dispatch, price, interval cost."""
    flagged = {(t, k) for t, k, _ in _violations(result, ramps)} if flag else set()

    def row(label: str, cells: list[str]) -> str:
        body = "".join(f'<td style="{TD}">{c}</td>' for c in cells)
        return f'<tr><th style="{TH_LEFT}">{label}</th>{body}</tr>'

    header = f'<tr><th style="{TH_LEFT}">Demand D_t (MW)</th>' + "".join(
        f'<th style="{TH}">{d:,.0f}</th>' for d in demands
    ) + "</tr>"

    rows = ""
    for k, gen in enumerate(ed.GENERATORS):
        cells = []
        for t in range(len(demands)):
            mark = ' <span class="ed-flag">ramp exceeded</span>' if (t, k) in flagged else ""
            cells.append(f"{result.P[t][k]:,.0f}{mark}")
        rows += row(f"P({gen.name}, t) MW", cells)
    rows += row("lambda ($/MWh)",
                [_price_cell(l) for l in result.lam])
    rows += row("Cost ($ per five-minute interval)",
                [ed.money(c) for c in result.cost])

    return ('<div class="ed-wrap"><table style="width:100%;border-collapse:collapse">'
            f"{header}{rows}</table></div>")


def render() -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)

    ed.header(
        "Ramp limits and the price of movement",
        "Three consecutive five-minute intervals. Solve them one at a time and "
        "the answer is the same three separate markets. Couple them with a ramp "
        "limit and the price in one interval starts paying for what the "
        "generators have to do in the others.",
    )

    st.subheader("Market data")
    columns = st.columns(3)
    demands = [
        float(columns[t].number_input(
            f"Demand at t{t + 1} (MW)", min_value=0, max_value=4000, step=10,
            key=DEMAND_KEYS[t],
        ))
        for t in range(T)
    ]

    ramps_on = st.toggle(
        "Ramps on", key=RAMPS_ON_KEY,
        help="Off means no inter-temporal constraint at all. There is no ramp "
             "on interval 1, so the first interval is never limited by where "
             "the units started.",
    )
    ramp_columns = st.columns(3)
    ramps = [
        float(ramp_columns[k].number_input(
            f"{gen.name} RU = RD (MW per interval)", min_value=1, max_value=1500,
            step=5, key=RAMP_KEYS[k], disabled=not ramps_on,
        ))
        for k, gen in enumerate(ed.GENERATORS)
    ]

    alone = ed.solve(demands)
    together = ed.solve(demands, ramps=ramps if ramps_on else None)

    if not alone.ok or not together.ok:
        ed.note(f"<strong>No dispatch.</strong> "
                f"{alone.message or together.message}")
        return

    left, right = st.columns(2)
    with left:
        st.subheader("Intervals solved alone")
        st.markdown(_plan_table(alone, demands, ramps, flag=ramps_on),
                    unsafe_allow_html=True)
    with right:
        st.subheader("Horizon solved together")
        st.markdown(_plan_table(together, demands, ramps, flag=False),
                    unsafe_allow_html=True)

    if not ramps_on:
        ed.note("No inter-temporal constraint, so the horizon separates. "
                "Solving the three intervals one at a time gives exactly the "
                "plan the whole horizon gives.")
    else:
        breaches = _violations(alone, ramps)
        if breaches:
            items = "".join(
                f"<li>{ed.GENERATORS[k].name} moves {move:+,.0f} MW from "
                f"t{t} to t{t + 1}, and its limit is {ramps[k]:,.0f} MW.</li>"
                for t, k, move in breaches
            )
            ed.note(
                "The left-hand plan is cheaper interval by interval, but it "
                f"commits movements the units cannot make:<ul>{items}</ul>"
                "The right-hand plan is the cheapest one they can actually "
                "follow, and it is what the prices are read from."
            )
        else:
            ed.note("The interval-by-interval plan happens to respect every "
                    "ramp limit here, so the two columns agree.")

    if any(not any(abs(l - o) < 1e-6 for o in OFFERS) for l in together.lam):
        st.markdown(
            f'<div class="ed-wrap"><p style="color:{ed.PURPLE};font-weight:700">'
            "The prices shown in purple match no offer in the market: no one "
            "offered this price.</p></div>",
            unsafe_allow_html=True,
        )

    st.subheader("Binding ramp rows")
    binding = [
        (f"{gen.name} {way}, t{step + 1} to t{step + 2}", nu)
        for step in range(len(together.nu_up))
        for k, gen in enumerate(ed.GENERATORS)
        for nu, way in ((together.nu_up[step][k], "ramp-up"),
                        (together.nu_dn[step][k], "ramp-down"))
        if nu > 1e-6
    ]
    if not binding:
        st.markdown('<div class="ed-wrap"><p>No ramp row is binding, so no '
                    "ramp multiplier is non-zero.</p></div>",
                    unsafe_allow_html=True)
    else:
        for name, nu in binding:
            st.markdown(
                f'<div class="ed-row"><span class="who">{name}</span> is '
                f"<strong>binding</strong>, nu = {nu:,.2f} $/MWh. That is the "
                "marginal value of relaxing a constraint: one more MW of "
                f"movement allowed on this step is worth {nu:,.2f} $/MWh.</div>",
                unsafe_allow_html=True,
            )

    st.subheader("Totals over the three intervals")
    left, right = st.columns(2)
    left.markdown(
        ed.headline("Total offered cost", ed.money(together.total_cost),
                    "$ over the three intervals"),
        unsafe_allow_html=True,
    )
    right.markdown(
        ed.headline("Total consumer payment",
                    ed.money(together.payment(demands)),
                    "$ over the three intervals"),
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="ed-wrap"><p>These are two separate quantities and they '
        "are never added together. The cost is what the generators offered to "
        "produce the energy. The payment is the sum of lambda_t x D_t x "
        "Delta T, which is what the consumers hand over at the cleared "
        "price.</p></div>",
        unsafe_allow_html=True,
    )

    st.subheader("The one-megawatt probe")
    interval = st.radio(
        "Add one MW of demand in which interval?", options=list(range(1, T + 1)),
        format_func=lambda t: f"t{t}", horizontal=True, key=PROBE_KEY,
    )
    probe_demands = list(demands)
    probe_demands[interval - 1] += 1.0
    probe = ed.solve(probe_demands, ramps=ramps if ramps_on else None)

    if not probe.ok:
        ed.note(f"<strong>One MW more at t{interval} is not feasible.</strong> "
                f"{probe.message}")
        return

    items = []
    for t in range(T):
        for k, gen in enumerate(ed.GENERATORS):
            move = probe.P[t][k] - together.P[t][k]
            if abs(move) < 1e-6:
                continue
            items.append(
                f"<li>{gen.name} {move:+,.0f} MW at t{t + 1}, at "
                f"{gen.offer:,.0f} $/MWh: {move * gen.offer:+,.2f} $/h</li>"
            )
    chain = (probe.total_cost - together.total_cost) * ed.PER_HOUR
    st.markdown(
        f'<div class="ed-wrap"><p>One more MW at t{interval} sets off this '
        f"chain of movements:</p><ul>{''.join(items)}</ul>"
        f"<p><strong>Total {chain:,.2f} $/h, which is lambda at t{interval} = "
        f"{together.lam[interval - 1]:,.2f} $/MWh.</strong></p></div>",
        unsafe_allow_html=True,
    )
