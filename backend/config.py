import os


def read_secret(env_var: str, default: str = "") -> str:
    """Read a secret from env var or a _PATH variant pointing to a file."""
    # Check for _PATH variant first (agenix convention)
    path_value = os.getenv(env_var + "_PATH", "")
    if path_value and os.path.isfile(path_value):
        with open(path_value, "r") as f:
            return f.read().strip()
    # Fall back to direct value
    value = os.getenv(env_var, default)
    if value and value.startswith("/") and os.path.isfile(value):
        with open(value, "r") as f:
            return f.read().strip()
    return value
