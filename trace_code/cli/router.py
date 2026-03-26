KNOWN_COMMANDS = {"/help", "/config", "/sessions", "/health", "/exit"}


def route_user_input(user_input: str) -> str:
    text = user_input.strip()
    if text in KNOWN_COMMANDS:
        return "builtin"
    return "agent"
