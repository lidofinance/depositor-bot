import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class InconsistentProviders(Exception):
    pass


class NotHealthyProvider(Exception):
    pass


class ProviderConsistencyModule(ABC):
    """
    Checks that at least one provided host is alive and the responding hosts' chain ids are consistent.
    """

    def check_providers_consistency(self) -> int | None:
        chain_id = None
        providers_count = len(self.get_all_providers())

        for provider_index in range(providers_count):
            try:
                curr_chain_id = self._get_chain_id_with_provider(provider_index)
            except Exception as error:
                # Only the error type: the message can carry the host URL, which may embed an API key.
                logger.warning(
                    {
                        'msg': f'Provider [{provider_index}] is not responding, skipping it in the chain id check.',
                        'error': type(error).__name__,
                    }
                )
                continue

            if chain_id is None:
                chain_id = curr_chain_id
            elif chain_id != curr_chain_id:
                raise InconsistentProviders(
                    f'Different chain ids detected for {provider_index=}. Expected {curr_chain_id=}, got {chain_id=}.'
                )

        if providers_count and chain_id is None:
            raise NotHealthyProvider(f'None of {providers_count} providers responded.')

        return chain_id

    @abstractmethod
    def get_all_providers(self) -> list[Any]:
        """Returns list of hosts or providers."""
        raise NotImplementedError('get_all_providers should be implemented')

    @abstractmethod
    def _get_chain_id_with_provider(self, provider_index: int) -> int:
        """Does a health check call and returns chain_id for current host."""
        raise NotImplementedError('_get_chain_id_with_provider should be implemented')
