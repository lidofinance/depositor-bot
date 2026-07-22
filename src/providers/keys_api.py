import logging
from dataclasses import dataclass
from typing import NamedTuple

from metrics.metrics import KEYS_API_REQUESTS_DURATION
from providers.http_provider import HTTPProvider, data_is_dict

logger = logging.getLogger(__name__)


class LidoKey(NamedTuple):
    """Minimal Lido key representation — only fields used downstream.

    Always access via named attributes (.key, .index, .operatorIndex);
    don't rely on tuple-like behavior (positional index, == with plain tuple).
    """

    key: str
    index: int
    operatorIndex: int

    @classmethod
    def from_response(cls, **kwargs) -> 'LidoKey':
        return cls(
            key=kwargs['key'].lower(),
            index=kwargs['index'],
            operatorIndex=kwargs['operatorIndex'],
        )


@dataclass
class KeysApiStatus:
    appVersion: str
    chainId: int

    @classmethod
    def from_response(cls, **kwargs) -> 'KeysApiStatus':
        return cls(appVersion=kwargs['appVersion'], chainId=kwargs['chainId'])


def group_keys_by_operator(keys: list[LidoKey], operator_ids: list[int]) -> dict[int, list[LidoKey]]:
    """Group keys by their operatorIndex, keeping only operators in `operator_ids`.

    Every requested operator gets an entry (empty list if it has no keys); keys whose operator
    is not requested are dropped.
    """
    wanted = set(operator_ids)
    result: dict[int, list[LidoKey]] = {op_id: [] for op_id in operator_ids}
    for k in keys:
        if k.operatorIndex in wanted:
            result[k.operatorIndex].append(k)
    return result


class KeysAPIClient(HTTPProvider):
    """
    Lido Keys API client.
    Docs: https://keys-api.lido.fi/api/static/index.html
    """

    PROMETHEUS_HISTOGRAM = KEYS_API_REQUESTS_DURATION

    def __init__(
        self,
        host: str,
        request_timeout: int = 30,
        retry_total: int = 3,
        retry_backoff_factor: int = 1,
    ):
        super().__init__(
            hosts=[host],
            request_timeout=request_timeout,
            retry_total=retry_total,
            retry_backoff_factor=retry_backoff_factor,
        )

    def get_module_used_keys(self, module_id: int) -> list[LidoKey]:
        """
        Get all used (deposited) keys for a staking module.
        GET /v1/modules/{module_id}/keys?used=true
        """
        data, _ = self._get(
            endpoint='v1/modules/{}/keys',
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
        result = group_keys_by_operator(all_keys, operator_ids)

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
