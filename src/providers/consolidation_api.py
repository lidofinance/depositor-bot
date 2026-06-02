import logging

from prometheus_client import Histogram
from providers.http_provider import HTTPProvider, data_is_dict

logger = logging.getLogger(__name__)

CONSOLIDATION_API_REQUESTS_DURATION = Histogram(
    'consolidation_api_requests_duration_seconds',
    'Consolidation API request duration',
    ['endpoint', 'code', 'domain'],
)


class ConsolidationApiError(Exception):
    """Raised when the consolidation service is not ready or returns an error.

    A failure here must NOT be treated as "validators are free": per the API
    contract, on 500 / VALIDATION_FAILED / "Chain is not yet indexed" the caller
    has to retry later instead of assuming nobody is consolidating.
    """


class ConsolidationApiClient(HTTPProvider):
    """
    Consolidation-bot API client.

    Returns, per node operator, the signing-key indices that participate in a
    pending consolidation (the module's role — source or target — is selected by
    `module_id`). Used as a guard before operating on a validator (e.g. top-up):
    such keys must be excluded.

    POST /api/v1/consolidation-requests/pending/keys
    No auth. Empty operatorIds list is allowed and returns an empty result.
    """

    PROMETHEUS_HISTOGRAM = CONSOLIDATION_API_REQUESTS_DURATION

    PENDING_KEYS_ENDPOINT = 'api/v1/consolidation-requests/pending/keys'

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

    def get_pending_consolidation_key_indices(self, module_id: int, operator_ids: list[int]) -> dict[int, set[int]]:
        """
        Return, per operator, the signing-key indices that take part in a pending
        consolidation (submitted but not yet executed or removed).

        The module's role is resolved from `module_id`: if it is the source
        module the source indices are returned, if it is the target module the
        target indices are returned. If `module_id` is neither, the service
        returns an empty result, i.e. {}.

        Operators without pending keys are omitted from the result, so
        `len(result) <= len(operator_ids)`. An empty result is a valid answer
        meaning "nobody is consolidating".

        An empty `operator_ids` returns {} without hitting the network.

        Raises ConsolidationApiError if the service is unavailable or not yet
        indexed — the caller must retry rather than treat the keys as free.
        """
        if not operator_ids:
            return {}

        try:
            data, _ = self._post_without_fallbacks(
                self.hosts[0],
                endpoint=self.PENDING_KEYS_ENDPOINT,
                json={'moduleId': module_id, 'operatorIds': operator_ids},
                retval_validator=data_is_dict,
            )
        except Exception as e:
            raise ConsolidationApiError('Consolidation API request failed.') from e

        result = data.get('result')
        if not isinstance(result, list):
            raise ConsolidationApiError(f'Unexpected consolidation API response: {data}')

        by_operator: dict[int, set[int]] = {}
        try:
            for item in result:
                by_operator[item['operatorId']] = set(item['keyIndices'])
        except (KeyError, TypeError) as e:
            raise ConsolidationApiError(f'Unexpected consolidation API response: {data}') from e

        logger.info(
            {
                'msg': 'Fetched pending consolidation key indices.',
                'module_id': module_id,
                'requested_operators': len(operator_ids),
                'operators_with_pending': len(by_operator),
            }
        )
        return by_operator
