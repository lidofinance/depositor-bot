import json

import pytest

from utils.build_info import UNKNOWN, load_build_info

pytestmark = pytest.mark.unit

ALL_UNKNOWN = {'version': UNKNOWN, 'branch': UNKNOWN, 'commit': UNKNOWN}


def test_missing_file_gives_unknown(tmp_path):
    assert load_build_info(tmp_path / 'build-info.json') == (ALL_UNKNOWN, None)


def test_reads_all_values(tmp_path):
    path = tmp_path / 'build-info.json'
    expected = {'version': '1.2.0', 'branch': 'main', 'commit': 'abc123'}
    path.write_text(json.dumps(expected))

    assert load_build_info(path) == (expected, None)


def test_missing_keys_stay_unknown(tmp_path):
    path = tmp_path / 'build-info.json'
    path.write_text(json.dumps({'version': '1.2.0', 'commit': ''}))

    assert load_build_info(path) == ({**ALL_UNKNOWN, 'version': '1.2.0'}, None)


def test_broken_json_gives_unknown(tmp_path):
    path = tmp_path / 'build-info.json'
    path.write_text('{not json')

    info, error = load_build_info(path)
    assert info == ALL_UNKNOWN
    assert error is not None
    assert str(path) in error


def test_non_object_json_gives_unknown(tmp_path):
    path = tmp_path / 'build-info.json'
    path.write_text('["1.2.0"]')

    info, error = load_build_info(path)
    assert info == ALL_UNKNOWN
    assert error == f'{path} is not a JSON object.'


def test_escaped_values_round_trip(tmp_path):
    # The Docker build writes the file with json.dump; a quote or backslash in a branch name must survive.
    path = tmp_path / 'build-info.json'
    expected = {'version': '1.2.0', 'branch': 'fix/"quoted"\\path', 'commit': 'abc123'}
    path.write_text(json.dumps(expected))

    assert load_build_info(path) == (expected, None)


def test_does_not_log(tmp_path, caplog):
    # Runs while `variables` is imported, before logging is configured.
    path = tmp_path / 'build-info.json'
    path.write_text('{not json')

    with caplog.at_level('DEBUG'):
        load_build_info(path)

    assert caplog.records == []
