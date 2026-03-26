from trace_code.cli.router import route_user_input


def test_routes_known_commands_to_builtin() -> None:
    assert route_user_input("/help") == "builtin"
    assert route_user_input(" /config ") == "builtin"
    assert route_user_input("/health") == "builtin"


def test_routes_unknown_input_to_agent() -> None:
    assert route_user_input("implement a function") == "agent"
