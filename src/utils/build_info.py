import json
from pathlib import Path

# Placeholders in the repo; the Docker build fills the file from the BUILD_VERSION, BUILD_BRANCH and BUILD_COMMIT build args.
BUILD_INFO_PATH = Path(__file__).resolve().parents[2] / 'build-info.json'
BUILD_INFO_KEYS: tuple[str, ...] = ('version', 'branch', 'commit')
UNKNOWN = 'unknown'


def load_build_info(path: Path = BUILD_INFO_PATH) -> tuple[dict[str, str], str | None]:
    """Return version, branch and commit of this build, and why the file could not be used (None when it could).

    Missing or unreadable values are 'unknown'. It does not log: it runs while `variables` is imported, before logging
    is configured, so the caller logs the error.
    """
    info = dict.fromkeys(BUILD_INFO_KEYS, UNKNOWN)

    try:
        with open(path) as file:
            data = json.load(file)
    except FileNotFoundError:
        return info, None
    except (OSError, ValueError) as error:
        return info, f'Failed to read {path}: {error}'

    if not isinstance(data, dict):
        return info, f'{path} is not a JSON object.'

    for key in BUILD_INFO_KEYS:
        value = data.get(key)
        if value:
            info[key] = str(value)

    return info, None
