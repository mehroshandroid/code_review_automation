DEFAULT_COMPILE_MODES = {"Android": "compiler", ".NET": "compiler", "iOS": "static"}
ALLOWED_COMPILE_MODES = {"Android": ("compiler", "local", "static"), ".NET": ("compiler", "static"), "iOS": ("compiler", "static")}


def effective_compile_modes(stored: dict | None) -> dict:
    """Org overrides on top of the defaults, ignoring unknown platforms."""
    return {**DEFAULT_COMPILE_MODES, **{k: v for k, v in (stored or {}).items() if k in DEFAULT_COMPILE_MODES}}
