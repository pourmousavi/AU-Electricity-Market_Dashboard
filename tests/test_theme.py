from hub import theme


def test_palette_has_required_tokens() -> None:
    required = {"ink", "ink_soft", "accent", "accent_soft", "cyan",
                "surface", "border", "text", "text_dim"}
    assert required <= set(theme.PALETTE)


def test_dark_css_is_wrapped_in_a_style_tag() -> None:
    css = theme.dark_page_css()
    assert css.strip().startswith("<style>")
    assert css.strip().endswith("</style>")


def test_dark_css_scopes_itself_to_hub_chrome() -> None:
    """The dark treatment must never leak into a vendored experiment body."""
    css = theme.dark_page_css()
    assert ".hub-dark" in css


def test_experiment_header_css_does_not_restyle_the_page_background() -> None:
    css = theme.experiment_header_css()
    assert ".stApp" not in css
    assert ".hub-expbar" in css
