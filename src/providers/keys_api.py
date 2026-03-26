import logging
from dataclasses import dataclass

from prometheus_client import Histogram

from src.providers.http_provider import HTTPProvider, data_is_dict

logger = logging.getLogger(__name__)

KEYS_API_REQUESTS_DURATION = Histogram(
    'keys_api_requests_duration_seconds',
    'Keys API request duration',
    ['endpoint', 'code', 'domain'],
)


@dataclass
class LidoKey:
    index: int
    operatorIndex: int
    depositSignature: str
    key: str
    used: bool
    moduleAddress: str
    vetted: bool

    @classmethod
    def from_response(cls, **kwargs) -> 'LidoKey':
        return cls(
            index=kwargs['index'],
            operatorIndex=kwargs['operatorIndex'],
            depositSignature=kwargs['depositSignature'],
            key=kwargs['key'].lower(),
            used=kwargs['used'],
            moduleAddress=kwargs['moduleAddress'],
            vetted=kwargs['vetted'],
        )


@dataclass
class KeysApiStatus:
    appVersion: str
    chainId: int

    @classmethod
    def from_response(cls, **kwargs) -> 'KeysApiStatus':
        return cls(appVersion=kwargs['appVersion'], chainId=kwargs['chainId'])


class KeysAPIClient(HTTPProvider):
    """
    Lido Keys API client.
    Docs: https://keys-api.lido.fi/api/static/index.html
    """

    PROMETHEUS_HISTOGRAM = KEYS_API_REQUESTS_DURATION

    def __init__(
        self,
        hosts: list[str],
        request_timeout: int = 30,
        retry_total: int = 3,
        retry_backoff_factor: int = 1,
    ):
        super().__init__(
            hosts=hosts,
            request_timeout=request_timeout,
            retry_total=retry_total,
            retry_backoff_factor=retry_backoff_factor,
        )

    def get_module_used_keys(self, module_id: int) -> list[LidoKey]:
        """
        Get all used (deposited) keys for a staking module.
        GET /v1/modules/{module_id}/operators/keys?used=true
        """
        data, _ = self._get(
            endpoint='v1/modules/{}/operators/keys',
            path_params=[module_id],
            query_params={'used': 'true'},
            retval_validator=data_is_dict,
        )
        keys = [LidoKey.from_response(**k) for k in data['keys']]
        logger.info(
            {
                'msg': 'Fetched used keys from Keys API.',
                'module_id': module_id,
                'keys_count': len(keys),
            }
        )
        return keys

    def get_module_operator_used_keys(self, module_id: int, operator_ids: list[int]) -> dict[int, list[LidoKey]]:
        """
        Get used keys grouped by operator.
        """
        all_keys = self.get_module_used_keys(module_id)
        operator_ids_set = set(operator_ids)
        result: dict[int, list[LidoKey]] = {op_id: [] for op_id in operator_ids}
        for k in all_keys:
            if k.operatorIndex in operator_ids_set:
                result[k.operatorIndex].append(k)

        logger.info(
            {
                'msg': 'Grouped keys by operator.',
                'module_id': module_id,
                'total_keys': len(all_keys),
                'operators': {op_id: len(keys) for op_id, keys in result.items()},
            }
        )
        return result

    def _get_chain_id_with_provider(self, provider_index: int) -> int:
        data, _ = self._get_without_fallbacks(self.hosts[provider_index], 'v1/status', retval_validator=data_is_dict)
        return KeysApiStatus.from_response(**data).chainId
