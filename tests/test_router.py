from hub.router import Route, parse_route, route_params


def test_empty_params_give_home() -> None:
    assert parse_route({}) == Route(view="home", topic_id=None, experiment_id=None)


def test_topic_route_parses_integer_id() -> None:
    assert parse_route({"view": "topic", "topic": "4"}) == Route("topic", 4, None)


def test_experiment_route_keeps_id_string() -> None:
    route = parse_route({"view": "experiment", "exp": "dispatch_pareto_frontier"})
    assert route == Route("experiment", None, "dispatch_pareto_frontier")


def test_admin_route() -> None:
    assert parse_route({"admin": "1"}).view == "admin"


def test_unknown_view_falls_back_home() -> None:
    assert parse_route({"view": "teleport"}).view == "home"


def test_non_integer_topic_falls_back_home() -> None:
    assert parse_route({"view": "topic", "topic": "abc"}).view == "home"


def test_topic_view_without_id_falls_back_home() -> None:
    assert parse_route({"view": "topic"}).view == "home"


def test_experiment_view_without_id_falls_back_home() -> None:
    assert parse_route({"view": "experiment"}).view == "home"


def test_route_params_round_trip() -> None:
    for route in (
        Route("home", None, None),
        Route("topic", 7, None),
        Route("experiment", None, "consumer_model"),
    ):
        assert parse_route(route_params(route)) == route
