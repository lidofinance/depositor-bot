import logging

from prometheus_client import Histogram

from src.providers.http_provider import HTTPProvider, NotOkResponse, data_is_dict

logger = logging.getLogger(__name__)

CL_REQUESTS_DURATION = Histogram(
    'cl_requests_duration_seconds',
    'CL API request duration',
    ['endpoint', 'code', 'domain'],
)


class ConsensusClientError(NotOkResponse):
    pass


class ConsensusClient(HTTPProvider):
    """Beacon API client for top-up proof construction."""

    PROVIDER_EXCEPTION = ConsensusClientError
    PROMETHEUS_HISTOGRAM = CL_REQUESTS_DURATION

    API_GET_BLOCK_DETAILS = 'eth/v2/beacon/blocks/{}'
    API_GET_BLOCK_HEADER = 'eth/v1/beacon/headers/{}'
    API_GET_STATE = 'eth/v2/debug/beacon/states/{}'

    def get_block_details(self, block_id: str) -> dict:
        """
        GET /eth/v2/beacon/blocks/{block_id}
        Returns block message with slot, proposer_index.
        """
        data, _ = self._get(
            self.API_GET_BLOCK_DETAILS,
            path_params=(block_id,),
            retval_validator=data_is_dict,
        )
        return data['message']

    def get_block_header(self, block_id: str) -> dict:
        """
        GET /eth/v1/beacon/headers/{block_id}
        Returns full header with parent_root, state_root, body_root.
        """
        data, _ = self._get(
            self.API_GET_BLOCK_HEADER,
            path_params=(block_id,),
            retval_validator=data_is_dict,
        )
        return data['header']['message']

    def get_beacon_state_ssz(self, slot: int) -> bytes:
        """
        GET /eth/v2/debug/beacon/states/{slot} with Accept: application/octet-stream
        Returns raw SSZ bytes.
        """
        # SSZ request bypasses _get because it needs custom Accept header and raw bytes
        errors = []
        for host in self.hosts:
            try:
                url = self._urljoin(host, self.API_GET_STATE.format(slot))
                response = self.session.get(
                    url,
                    headers={'Accept': 'application/octet-stream'},
                    timeout=300,
                )
                if response.status_code != 200:
                    raise ConsensusClientError(
                        f'SSZ request failed [{response.status_code}]',
                        status=response.status_code,
                        text=response.text,
                    )
                logger.info({
                    'msg': 'Fetched beacon state SSZ.',
                    'slot': slot,
                    'size_bytes': len(response.content),
                })
                return response.content
            except Exception as e:
                errors.append(e)
                logger.warning({'msg': f'SSZ fetch failed from host.', 'error': str(e)})

        raise errors[-1]

    def _get_chain_id_with_provider(self, provider_index: int) -> int:
        data, _ = self._get_without_fallbacks(
            self.hosts[provider_index],
            'eth/v1/config/spec',
            retval_validator=data_is_dict,
        )
        return int(data['DEPOSIT_CHAIN_ID'])
