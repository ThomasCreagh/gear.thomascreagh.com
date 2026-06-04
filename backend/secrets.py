import os


def read_secret(env_var: str, default: str = "") -> str:
    """Read a secret from env var. If the value is a file path, read the file."""
    value = os.getenv(env_var, default)
    if value and value.startswith("/") and os.path.isfile(value):
        with open(value, "r") as f:
            return f.read().strip()
    return value
