"""Visual identity for the hub chrome.

The global Streamlit theme is light, because every vendored dashboard hardcodes
light-coloured boxes (`background-color: white`, `#f0f8ff`, `#f8f9fa`) with
default text colour — a dark global theme would put light text on them and make
them unreadable.

So the dark, animated treatment is scoped to `.hub-dark`, which only wraps hub
chrome: home, topic pages, locked teasers and admin. Experiment pages get a slim
dark header bar and nothing else.

Palette: Adelaide-inspired (red accent over deep navy), not official branding.
"""
from __future__ import annotations

import streamlit as st

PALETTE = {
    "ink": "#0B1020",
    "ink_soft": "#141A2E",
    "accent": "#C8102E",
    "accent_soft": "#F0435F",
    "cyan": "#31E1F7",
    "surface": "rgba(255,255,255,0.055)",
    "border": "rgba(255,255,255,0.13)",
    "text": "#F2F4F8",
    "text_dim": "rgba(242,244,248,0.66)",
}


def inject(css: str) -> None:
    st.markdown(css, unsafe_allow_html=True)


def dark_page_css() -> str:
    p = PALETTE
    return f"""<style>
.hub-dark {{
  background:
    radial-gradient(1100px 520px at 12% -10%, rgba(200,16,46,0.30), transparent 60%),
    radial-gradient(900px 460px at 88% 8%, rgba(49,225,247,0.16), transparent 62%),
    linear-gradient(168deg, {p['ink']} 0%, {p['ink_soft']} 100%);
  color: {p['text']};
  border-radius: 22px;
  padding: 2.6rem 2.2rem 2.2rem;
  margin-bottom: 1.4rem;
  position: relative;
  overflow: hidden;
}}
.hub-dark::after {{
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background-image:
    linear-gradient(rgba(255,255,255,0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.045) 1px, transparent 1px);
  background-size: 46px 46px;
  mask-image: radial-gradient(circle at 50% 0%, #000 0%, transparent 78%);
}}
.hub-dark h1, .hub-dark h2, .hub-dark h3, .hub-dark p, .hub-dark span {{
  color: {p['text']};
}}
.hub-eyebrow {{
  letter-spacing: .22em; text-transform: uppercase;
  font-size: .70rem; color: {p['cyan']}; font-weight: 700;
}}
.hub-title {{
  font-size: clamp(1.9rem, 4.2vw, 3.0rem); font-weight: 800;
  line-height: 1.06; margin: .35rem 0 .5rem;
  /* Solid colour first: browsers without background-clip: text support (and
     the .hub-title is applied to a <div>, which the .hub-dark h1/h2/h3/p/span
     fallback rule below does not cover) must still render visible text. The
     gradient below is a progressive enhancement on top of this. */
  color: {p['text']};
  background: linear-gradient(96deg, {p['text']} 12%, {p['accent_soft']} 58%, {p['cyan']} 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}}
.hub-sub {{ color: {p['text_dim']}; font-size: 1.02rem; max-width: 62ch; }}
.hub-progress {{
  height: 7px; border-radius: 99px; background: rgba(255,255,255,0.11);
  overflow: hidden; margin: 1.3rem 0 .45rem; max-width: 460px;
}}
.hub-progress > span {{
  display: block; height: 100%;
  background: linear-gradient(90deg, {p['accent']}, {p['cyan']});
}}
/* Cards sit in st.columns, which we cannot wrap in .hub-dark, so each card
   carries its own dark surface rather than relying on a parent. */
.hub-card {{
  background:
    linear-gradient(158deg, rgba(11,16,32,0.97) 0%, rgba(20,26,46,0.97) 100%);
  border: 1px solid {p['border']};
  color: {p['text']};
  border-radius: 16px; padding: 1.15rem 1.15rem 1rem;
  transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
  height: 100%;
}}
/* A card and its button are separate Streamlit elements, so the card only fills
   the tallest card in its row if every wrapper between the column and the card
   stretches. `div:has(.hub-card)` hits them all without depending on how deep
   Streamlit nests element containers this version. */
[data-testid="stColumn"]:has(.hub-card) > div {{ height: 100%; }}
[data-testid="stColumn"]:has(.hub-card) div:has(.hub-card) {{
  display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0;
}}
[data-testid="stColumn"]:has(.hub-card) .stButton {{ margin-top: .6rem; }}
[data-testid="stColumn"]:has(.hub-card) {{ margin-bottom: 1.1rem; }}
.hub-card h3, .hub-card span {{ color: {p['text']}; }}
.hub-card:hover {{
  transform: translateY(-4px);
  border-color: rgba(240,67,95,0.55);
  box-shadow: 0 14px 36px rgba(0,0,0,0.42);
}}
.hub-card.locked {{ opacity: .60; }}
.hub-card h3 {{ font-size: 1.10rem; margin: .3rem 0 .35rem; font-weight: 700; }}
.hub-card p {{ color: {p['text_dim']}; font-size: .89rem; margin: 0 0 .55rem; }}
.hub-chip {{
  display: inline-block; padding: .16rem .58rem; border-radius: 99px;
  font-size: .68rem; font-weight: 700; letter-spacing: .05em;
  border: 1px solid {p['border']}; color: {p['text_dim']};
}}
.hub-chip.open {{ color: {p['cyan']}; border-color: rgba(49,225,247,0.45); }}
@media (prefers-reduced-motion: reduce) {{
  .hub-card {{ transition: none; }}
  .hub-card:hover {{ transform: none; }}
}}
</style>"""


def experiment_header_css() -> str:
    p = PALETTE
    return f"""<style>
.hub-expbar {{
  background: linear-gradient(96deg, {p['ink']}, {p['ink_soft']});
  color: {p['text']};
  border-radius: 13px;
  padding: .78rem 1.05rem;
  margin-bottom: 1.05rem;
  display: flex; align-items: baseline; gap: .6rem; flex-wrap: wrap;
}}
.hub-expbar .crumb {{ color: {p['text_dim']}; font-size: .80rem; }}
.hub-expbar .now {{ color: {p['text']}; font-weight: 700; font-size: 1.02rem; }}
.hub-expbar .dot {{ color: {p['accent_soft']}; }}
</style>"""
