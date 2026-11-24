from unittest.mock import MagicMock, Mock

import pytest
from requests import Response

from providers.consensus import CL_REQUESTS_DURATION
from providers.http_provider import HTTPProvider, NoHostsProvided, NotOkResponse, _domain, data_is_any, data_is_dict


@pytest.mark.unit
def test_urljoin():
    join = HTTPProvider._urljoin
    assert join('http://localhost', 'api') == 'http://localhost/api'
    assert join('http://localhost/', 'api') == 'http://localhost/api'
    assert join('http://localhost', '/api') == 'http://localhost/api'
    assert join('http://localhost/', '/api') == 'http://localhost/api'
    assert join('http://localhost', 'api/') == 'http://localhost/api/'
    assert join('http://localhost/', 'api/') == 'http://localhost/api/'
    assert join('http://localhost/token', 'api') == 'http://localhost/token/api'
    assert join('http://localhost/token/', 'api') == 'http://localhost/token/api'


@pytest.mark.unit
def test_no_providers():
    with pytest.raises(NoHostsProvided):
        HTTPProvider([], 5 * 60, 1, 1)


@pytest.mark.unit
def test_all_fallbacks_ok():
    provider = HTTPProvider(['http://localhost:1', 'http://localhost:2'], 5 * 60, 1, 1)
    provider._get_without_fallbacks = lambda host, endpoint, path_params, query_params, stream, **_: (host, endpoint)

    assert provider._get('test') == ('http://localhost:1', 'test')
    assert len(provider.get_all_providers()) == 2


@pytest.mark.unit
def test_all_fallbacks_bad():
    provider = HTTPProvider(['http://localhost:1', 'http://localhost:2'], 5 * 60, 1, 1)

    with pytest.raises(Exception):  # noqa: B017
        provider._get('test')


@pytest.mark.unit
def test_first_fallback_bad():
    def _simple_get(host, endpoint, *args, **kwargs):
        if host == 'http://localhost:1':
            raise Exception('Bad host')  # pylint: disable=broad-exception-raised
        return host, endpoint

    provider = HTTPProvider(['http://localhost:1', 'http://localhost:2'], 5 * 60, 1, 1)
    provider._get_without_fallbacks = _simple_get

    assert provider._get('test') == ('http://localhost:2', 'test')


@pytest.mark.unit
def test_force_raise():
    class CustomError(Exception):
        pass

    def _simple_get(host, endpoint, *args, **kwargs):
        if host == 'http://localhost:1':
            raise Exception('Bad host')  # pylint: disable=broad-exception-raised
        return host, endpoint

    provider = HTTPProvider(['http://localhost:1', 'http://localhost:2'], 5 * 60, 1, 1)
    provider._get_without_fallbacks = Mock(side_effect=_simple_get)

    with pytest.raises(CustomError):
        provider._get('test', force_raise=lambda _: CustomError())

    provider._get_without_fallbacks.assert_called_once_with(
        'http://localhost:1',
        'test',
        None,
        None,
        stream=False,
        retval_validator=data_is_any,
    )


@pytest.mark.unit
def test_retval_validator():
    provider = HTTPProvider(['http://localhost:1', 'http://localhost:2'], 5 * 60, 1, 1)
    provider.PROMETHEUS_HISTOGRAM = CL_REQUESTS_DURATION

    resp = Response()
    resp.status_code = 200
    resp._content = b'{"data": {}}'
    provider.session.get = Mock(return_value=resp)

    def failed_validation(*args, **kwargs):
        raise ValueError('Validation failed')

    with pytest.raises(ValueError, match='Validation failed'):
        provider._get('test', retval_validator=failed_validation)


def _observations(endpoint: str) -> dict | None:
    """Labels of the one CL_REQUESTS_DURATION count sample for this endpoint, or None if it was never observed."""
    [metric] = CL_REQUESTS_DURATION.collect()
    samples = [s for s in metric.samples if s.name.endswith('_count') and s.labels['endpoint'] == endpoint and s.value == 1]
    return samples[0].labels if len(samples) == 1 else None


@pytest.mark.unit
def test_system_exit_during_request_is_not_replaced():
    # SIGTERM handler raises SystemExit mid-request: the duration timer must still get labels, or it raises ValueError
    # on exit and a clean shutdown becomes exit code 1.
    provider = HTTPProvider(['http://localhost:1'], 5 * 60, 1, 1)
    provider.PROMETHEUS_HISTOGRAM = CL_REQUESTS_DURATION
    provider.session.get = Mock(side_effect=SystemExit(0))

    with pytest.raises(SystemExit):
        provider._get_without_fallbacks('http://localhost:1', 'test-sigterm')

    assert _observations(endpoint='test-sigterm') == {'code': '0', 'domain': 'localhost:1', 'endpoint': 'test-sigterm'}


@pytest.mark.unit
def test_failed_request_is_observed_with_code_0():
    provider = HTTPProvider(['http://localhost:1'], 5 * 60, 1, 1)
    provider.PROMETHEUS_HISTOGRAM = CL_REQUESTS_DURATION
    provider.session.get = Mock(side_effect=ConnectionError('refused'))

    with pytest.raises(NotOkResponse):
        provider._get_without_fallbacks('http://localhost:1', 'test-refused')

    assert _observations(endpoint='test-refused') == {'code': '0', 'domain': 'localhost:1', 'endpoint': 'test-refused'}


@pytest.mark.unit
def test_data_is_dict():
    # dict passes silently; anything else raises with the endpoint in the message
    data_is_dict({}, {}, endpoint='v1/test')
    data_is_dict({'a': 1}, {}, endpoint='v1/test')

    for bad in ([], [1, 2], 1, 'str', None):
        with pytest.raises(ValueError, match='Expected mapping response from v1/test'):
            data_is_dict(bad, {}, endpoint='v1/test')


@pytest.mark.unit
def test_custom_error_provided():
    class CustomError(NotOkResponse):
        pass

    class TestProvider(HTTPProvider):
        PROVIDER_EXCEPTION = CustomError
        PROMETHEUS_HISTOGRAM = MagicMock()

        def call(self):
            return self._get('invalid_url')

        def _get_chain_id_with_provider(self, provider_index: int) -> int:
            return 1

    provider = TestProvider(['http://example.com/'], 1, 1, 1)

    with pytest.raises(CustomError):
        provider.call()


@pytest.mark.unit
def test_user_agent_names_the_app():
    provider = HTTPProvider(['http://localhost:1'], 5 * 60, 1, 1)

    assert provider.session.headers['User-Agent'].startswith('depositor-bot/')


@pytest.mark.unit
@pytest.mark.parametrize(
    'url,expected',
    [
        ('https://user:cl-password@beacon.example/', 'beacon.example'),
        ('http://beacon.example:5052/eth', 'beacon.example:5052'),
        ('https://beacon.example/token/abc', 'beacon.example'),
    ],
)
def test_metric_domain_label_has_no_credentials(url, expected):
    assert _domain(url) == expected
