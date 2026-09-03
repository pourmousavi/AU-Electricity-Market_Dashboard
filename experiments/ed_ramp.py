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

# Unicode subscripts, for the HTML table where LaTeX cannot reach.
SUB = {1: "\u2081", 2: "\u2082", 3: "\u2083"}


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


def _plan_table(result: ed.Dispatch, demands, ramps, flag: bool) -> str:
    """One column per interval: dispatch, price, interval cost.

    A real HTML table, so its headers use the Unicode letters rather than
    LaTeX: an HTML block is opaque to the markdown parser, and maths inside it
    would render as its own source. The symbols are defined in LaTeX in the
    legend printed above the two tables.
    """
    flagged = {(t, k) for t, k, _ in _violations(result, ramps)} if flag else set()

    def row(label: str, cells: list[str]) -> str:
        return f"<tr><th>{label}</th>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"

    head = f"<tr><th>Demand D\u209c (MW)</th>" + "".join(
        f"<th>{d:,.0f}</th>" for d in demands
    ) + "</tr>"

    rows = ""
    for k, gen in enumerate(ed.GENERATORS):
        cells = []
        for t in range(len(demands)):
            mark = ' <span class="ed-flag">ramp exceeded</span>' if (t, k) in flagged else ""
            cells.append(f"{result.P[t][k]:,.0f}{mark}")
        rows += row(f"{gen.name}: P{SUB[k + 1]},\u209c (MW)", cells)
    rows += row(f"{ed.LAMBDA}\u209c ($/MWh)", [_price_cell(l) for l in result.lam])
    rows += row("Cost ($ per interval)", [ed.money(c) for c in result.cost])

    return f'<div class="ed-table"><table>{head}{rows}</table></div>'


def render() -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)

    ed.header(
        "Ramp limits and the price of movement",
        "Three consecutive five-minute intervals. Solve them one at a time and "
        "the answer is the same three separate markets. Couple them with a ramp "
        r"limit and $\lambda_t$ in one interval starts paying for what the "
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

    ramps_on = st.toggle("Ramps on", key=RAMPS_ON_KEY)
    st.caption(
        r"The ramp rows are $|P_{k,t} - P_{k,t-1}| \le R_k$ for $t = 2, 3$. "
        r"There is no ramp on the first interval, so $t_1$ is never limited "
        r"by where the units started."
    )
    ramp_columns = st.columns(3)
    ramps = [
        float(ramp_columns[k].number_input(
            f"{gen.name}: RU = RD (MW per interval)", min_value=1,
            max_value=1500, step=5, key=RAMP_KEYS[k], disabled=not ramps_on,
        ))
        for k, gen in enumerate(ed.GENERATORS)
    ]

    alone = ed.solve(demands)
    together = ed.solve(demands, ramps=ramps if ramps_on else None)

    if not alone.ok or not together.ok:
        ed.note(f"**No dispatch.** {alone.message or together.message}")
        return

    st.markdown(
        r"In the tables below, $P_{k,t}$ is the dispatch of generator $k$ in "
        r"interval $t$, $\lambda_t$ is that interval's price in \$/MWh, and "
        r"the cost row is dollars per five-minute interval, that is "
        r"$\sum_k c_k P_{k,t} \Delta T$."
    )

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
            items = "\n".join(
                rf"- {ed.GENERATORS[k].name} moves ${move:+,.0f}$ MW from "
                rf"$t_{t}$ to $t_{t + 1}$, and $R_{k + 1} = {ramps[k]:,.0f}$ MW."
                for t, k, move in breaches
            )
            ed.note(
                "The left-hand plan is cheaper interval by interval, but it "
                "commits movements the units cannot make:\n\n"
                f"{items}\n\n"
                "The right-hand plan is the cheapest one they can actually "
                "follow, and it is what the prices are read from."
            )
        else:
            ed.note("The interval-by-interval plan happens to respect every "
                    "ramp limit here, so the two columns agree.")

    if any(not any(abs(l - o) < 1e-6 for o in OFFERS) for l in together.lam):
        st.markdown(
            rf'<span style="color:{ed.PURPLE};font-weight:700">'
            r"The prices shown in purple match no offer in the market: "
            r"no one offered this price.</span>",
            unsafe_allow_html=True,
        )

    st.subheader("Binding ramp rows")
    binding = [
        (gen.name, way, step + 1, step + 2, k, nu)
        for step in range(len(together.nu_up))
        for k, gen in enumerate(ed.GENERATORS)
        for nu, way in ((together.nu_up[step][k], "ramp-up"),
                        (together.nu_dn[step][k], "ramp-down"))
        if nu > 1e-6
    ]
    if not binding:
        st.markdown(r"No ramp row is binding, so every $\nu$ is zero.")
    else:
        for name, way, a, b, k, nu in binding:
            ed.row(
                rf"**{name} {way}, $t_{a}$ to $t_{b}$** is **binding**, with "
                rf"$\nu = {nu:,.2f}$ \$/MWh. That is the marginal value of "
                rf"relaxing a constraint: one more MW of movement allowed on "
                rf"this step is worth ${nu:,.2f}$ \$/MWh."
            )

    st.subheader("Totals over the three intervals")
    left, right = st.columns(2)
    with left:
        ed.headline(r"Total offered cost (\$)", ed.money(together.total_cost))
    with right:
        ed.headline(r"Total consumer payment (\$)",
                    ed.money(together.payment(demands)))
    st.markdown("These are two separate quantities and they are never added "
                "together. The cost is what the generators offered to produce "
                "the energy,")
    st.latex(r"\text{cost} = \sum_{t} \sum_{k} c_k P_{k,t} \, \Delta T")
    st.markdown("while the payment is what the consumers hand over at the "
                "cleared price,")
    st.latex(r"\text{payment} = \sum_{t} \lambda_t \, D_t \, \Delta T")

    st.subheader("The one-megawatt probe")
    interval = st.radio(
        "Add one MW of demand in which interval?", options=list(range(1, T + 1)),
        format_func=lambda t: f"t{t}", horizontal=True, key=PROBE_KEY,
    )
    probe_demands = list(demands)
    probe_demands[interval - 1] += 1.0
    probe = ed.solve(probe_demands, ramps=ramps if ramps_on else None)

    if not probe.ok:
        ed.note(rf"**One MW more at $t_{interval}$ is not feasible.** "
                f"{probe.message}")
        return

    items = []
    for t in range(T):
        for k, gen in enumerate(ed.GENERATORS):
            move = probe.P[t][k] - together.P[t][k]
            if abs(move) < 1e-6:
                continue
            items.append(
                rf"- {gen.name} moves ${move:+,.0f}$ MW at $t_{t + 1}$, at "
                rf"$c_{k + 1} = {gen.offer:,.0f}$ \$/MWh: "
                rf"${move * gen.offer:+,.2f}$ \$/h"
            )
    chain = (probe.total_cost - together.total_cost) * ed.PER_HOUR
    st.markdown(
        rf"One more MW at $t_{interval}$ sets off this chain of movements:"
        "\n\n" + "\n".join(items)
    )
    st.latex(
        rf"\sum \text{{movements}} = {chain:,.2f} \ \$/\mathrm{{h}} "
        rf"= \lambda_{interval} = {together.lam[interval - 1]:,.2f} \ "
        rf"\$/\mathrm{{MWh}}"
    )
