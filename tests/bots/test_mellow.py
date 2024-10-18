import pytest
import variables
from blockchain.deposit_strategy.base_deposit_strategy import MellowDepositStrategy
from bots.depositor import DepositorBot

from tests.conftest import COUNCIL_ADDRESS_1, COUNCIL_ADDRESS_2, COUNCIL_PK_1, COUNCIL_PK_2
from tests.utils.protocol_utils import get_deposit_message


# this fixture must be executed before others
@pytest.fixture(autouse=True)
def setup_mellow_env():
    variables.MELLOW_CONTRACT_ADDRESS = '0x078b1C03d14652bfeeDFadf7985fdf2D8a2e8108'


# 20529904 - is the block with mellow tx
# 20529995 - is the block with the fallback to regular tx
@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration,module_id',
    [[20529904, 2], [20529995, 2]],
    indirect=['web3_provider_integration'],
)
def test_depositor_bot_mellow_deposits(
    web3_provider_integration,
    web3_lido_integration,
    deposit_transaction_sender_integration,
    mellow_deposit_strategy_integration,
    base_deposit_strategy_integration,
    csm_strategy_integration,
    gas_price_calculator_integration,
    module_id,
    add_accounts_to_guardian,
):
    # Define the whitelist of deposit modules
    variables.DEPOSIT_MODULES_WHITELIST = [1, 2]

    # Get the latest block
    latest = web3_lido_integration.eth.get_block('latest')
    # Get the current nonce for the staking module
    old_module_nonce = web3_lido_integration.lido.staking_router.get_staking_module_nonce(module_id)

    # Create deposit messages
    deposit_messages = [
        get_deposit_message(web3_lido_integration, COUNCIL_ADDRESS_1, COUNCIL_PK_1, module_id),
        get_deposit_message(web3_lido_integration, COUNCIL_ADDRESS_1, COUNCIL_PK_1, module_id),
        get_deposit_message(web3_lido_integration, COUNCIL_ADDRESS_2, COUNCIL_PK_2, module_id),
    ]

    # Mine a new block
    web3_lido_integration.provider.make_request('anvil_mine', [1])

    # Initialize the DepositorBot
    db: DepositorBot = DepositorBot(
        web3_lido_integration,
        deposit_transaction_sender_integration,
        mellow_deposit_strategy_integration,
        base_deposit_strategy_integration,
        csm_strategy_integration,
    )

    # Clear the message storage and execute the bot without any messages
    db.message_storage.messages = []
    db.execute(latest)

    # Assert that the staking module nonce has not changed
    assert web3_lido_integration.lido.staking_router.get_staking_module_nonce(module_id) == old_module_nonce

    # Execute the bot with deposit messages and assert that the nonce has increased by 1
    db.message_storage.messages = deposit_messages

    # All the mellow specific checks
    mellow_strategy = MellowDepositStrategy(web3_lido_integration, gas_price_calculator_integration)
    initial_vault_balance = web3_lido_integration.lido.simple_dvt_staking_strategy.vault_balance()
    buffered = web3_lido_integration.lido.lido.get_buffered_ether()
    unfinalized = web3_lido_integration.lido.lido_locator.withdrawal_queue_contract.unfinalized_st_eth()
    deposited_keys = mellow_strategy.deposited_keys_amount(module_id)
    assert db.execute(latest)
    assert web3_lido_integration.lido.staking_router.get_staking_module_nonce(module_id) == old_module_nonce + 1
    actual_vault_balance = web3_lido_integration.lido.simple_dvt_staking_strategy.vault_balance()
    if buffered >= unfinalized and deposited_keys > 0 and initial_vault_balance >= variables.VAULT_DIRECT_DEPOSIT_THRESHOLD:
        assert initial_vault_balance > actual_vault_balance
    else:
        assert initial_vault_balance == actual_vault_balance
