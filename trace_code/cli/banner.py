ASCII_LOGO = r"""
 _____                    _____          _
|_   _| __ __ _  ___ ___ / ____|___   __| | ___
  | || '__/ _` |/ __/ _ \\ |   / _ \\ / _` |/ _ \\
  | || | | (_| | (_|  __/ |__| (_) | (_| |  __/
  |_||_|  \\__,_|\\___\\___|\\____\\___/ \\__,_|\\___|
"""


def render_banner(show_banner: bool = True) -> str:
    if not show_banner:
        return ""
    return ASCII_LOGO.strip("\n")
