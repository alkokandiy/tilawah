"""Color themes. Each theme maps semantic roles to ANSI colors.

Roles: border, title, accent, text, dim, highlight, progress_fill,
progress_empty, art (motif), error, ok. Values are colorama-free ANSI color
names resolved by the TUI/renderer to curses colors or SGR codes.
"""

THEMES = {
    "night": {
        "label": "Night — dark green & gold",
        "border": "gold",
        "title": "gold",
        "accent": "gold",
        "text": "pale_green",
        "dim": "dark_green",
        "highlight": "bright_gold",
        "progress_fill": "gold",
        "progress_empty": "dark_green",
        "art": "gold",
        "error": "red",
        "ok": "green",
        "bg": "black",
    },
    "dawn": {
        "label": "Dawn — warm sepia",
        "border": "brown",
        "title": "bright_yellow",
        "accent": "orange",
        "text": "cream",
        "dim": "brown",
        "highlight": "bright_yellow",
        "progress_fill": "orange",
        "progress_empty": "brown",
        "art": "orange",
        "error": "red",
        "ok": "green",
        "bg": "black",
    },
    "minimal": {
        "label": "Minimal — plain black/white for low-color terminals",
        "border": "white",
        "title": "white",
        "accent": "white",
        "text": "white",
        "dim": "gray",
        "highlight": "white",
        "progress_fill": "white",
        "progress_empty": "gray",
        "art": "white",
        "error": "white",
        "ok": "white",
        "bg": "black",
    },
}

# Approximate SGR foreground codes for non-curses renderers.
SGR = {
    "black": 30, "red": 31, "green": 32, "brown": 33, "gold": 33,
    "orange": 33, "dark_green": 32, "blue": 34, "magenta": 35,
    "cyan": 36, "gray": 37, "white": 37, "cream": 37, "pale_green": 32,
    "bright_gold": 93, "bright_yellow": 93,
}

# Map to curses base colors for the curses TUI.
CURSES_COLOR = {
    "black": 0, "red": 1, "green": 2, "brown": 3, "gold": 3,
    "orange": 3, "dark_green": 2, "blue": 4, "magenta": 5,
    "cyan": 6, "gray": 7, "white": 7, "cream": 7, "pale_green": 2,
    "bright_gold": 3, "bright_yellow": 3,
}


def get(name):
    return THEMES.get(name, THEMES["night"])


def names():
    return list(THEMES)
