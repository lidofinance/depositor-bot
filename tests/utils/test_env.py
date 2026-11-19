import traceback
from pathlib import Path

import pytest

from utils.env import from_file_or_env

pytestmark = pytest.mark.unit

ENV_NAME = 'SOME_SECRET'


@pytest.fixture
def secret_file(tmp_path: Path) -> Path:
    return tmp_path / 'secret'


def test_value_from_env(monkeypatch):
    monkeypatch.setenv(ENV_NAME, 'from-env')

    assert from_file_or_env(ENV_NAME) == 'from-env'


def test_unset_gives_none(monkeypatch):
    monkeypatch.delenv(ENV_NAME, raising=False)
    monkeypatch.delenv(f'{ENV_NAME}_FILE', raising=False)

    assert from_file_or_env(ENV_NAME) is None


def test_value_from_file_without_trailing_whitespace(monkeypatch, secret_file):
    secret_file.write_text('from-file \r\n')
    monkeypatch.setenv(f'{ENV_NAME}_FILE', str(secret_file))

    assert from_file_or_env(ENV_NAME) == 'from-file'


def test_file_wins_over_env(monkeypatch, secret_file):
    secret_file.write_text('from-file')
    monkeypatch.setenv(f'{ENV_NAME}_FILE', str(secret_file))
    monkeypatch.setenv(ENV_NAME, 'from-env')

    assert from_file_or_env(ENV_NAME) == 'from-file'


def test_empty_file_gives_empty_string(monkeypatch, secret_file):
    secret_file.write_text('\n')
    monkeypatch.setenv(f'{ENV_NAME}_FILE', str(secret_file))
    monkeypatch.setenv(ENV_NAME, 'from-env')

    assert from_file_or_env(ENV_NAME) == ''


def test_missing_file_fails(monkeypatch, tmp_path):
    monkeypatch.setenv(f'{ENV_NAME}_FILE', str(tmp_path / 'missing'))

    with pytest.raises(ValueError, match='SOME_SECRET_FILE'):
        from_file_or_env(ENV_NAME)


def test_required_and_unset_fails(monkeypatch):
    monkeypatch.delenv(ENV_NAME, raising=False)
    monkeypatch.delenv(f'{ENV_NAME}_FILE', raising=False)

    with pytest.raises(ValueError, match='SOME_SECRET or SOME_SECRET_FILE'):
        from_file_or_env(ENV_NAME, required=True)


def test_required_accepts_empty_env(monkeypatch):
    monkeypatch.setenv(ENV_NAME, '')

    assert from_file_or_env(ENV_NAME, required=True) == ''


def test_binary_file_fails_without_quoting_its_content(monkeypatch, secret_file):
    secret_file.write_bytes(b'\xff\xfe' + b'secret-bytes')
    monkeypatch.setenv(f'{ENV_NAME}_FILE', str(secret_file))

    with pytest.raises(ValueError, match='not UTF-8') as error:
        from_file_or_env(ENV_NAME)

    # The whole traceback, including a chained cause, is what a crash would print.
    printed = ''.join(traceback.format_exception(error.value))
    assert str(secret_file) in printed
    assert 'secret-bytes' not in printed
    assert 'xff' not in printed
    assert 'UnicodeDecodeError' not in printed
