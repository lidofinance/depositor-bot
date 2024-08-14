import pytest
from eth_typing import Hash32

import variables
from blockchain.deposit_strategy.base_deposit_strategy import MellowDepositStrategy
from blockchain.deposit_strategy.deposit_transaction_sender import Sender
from bots.depositor import DepositorBot
from tests.conftest import DSM_OWNER, COUNCIL_ADDRESS_1, COUNCIL_PK_1, COUNCIL_ADDRESS_2, COUNCIL_PK_2
from tests.utils.protocol_utils import get_deposit_message


# this fixture must be executed before others
@pytest.fixture(autouse=True)
def setup_environment():
    variables.MELLOW_CONTRACT_ADDRESS = '0x078b1C03d14652bfeeDFadf7985fdf2D8a2e8108'


@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration,module_id',
    [[20526731, 2]],
    indirect=['web3_provider_integration'],
)
def test_depositor_bot_mellow_deposits(
    web3_provider_integration,
    web3_lido_integration,
    deposit_transaction_sender_integration,
    mellow_deposit_strategy_integration,
    base_deposit_strategy_integration,
    gas_price_calculator_integration,
    module_id,
    add_accounts_to_guardian,
):
    # Disable mellow integration
    variables.MELLOW_CONTRACT_ADDRESS = '0x078b1C03d14652bfeeDFadf7985fdf2D8a2e8108'
    # Define the whitelist of deposit modules
    variables.DEPOSIT_MODULES_WHITELIST = [1, 2]

    # Set the balance for the first account
    web3_lido_integration.provider.make_request(
        'anvil_setBalance',
        [
            web3_lido_integration.eth.accounts[0],
            '0x500000000000000000000000',
        ],
    )

    # Submit multiple transactions
    for _ in range(15):
        web3_lido_integration.lido.lido.functions.submit(web3_lido_integration.eth.accounts[0]).transact(
            {
                'from': web3_lido_integration.eth.accounts[0],
                'value': 10000 * 10 ** 18,
            }
        )

    # Set the maximum number of deposits
    web3_lido_integration.lido.deposit_security_module.functions.setMaxDeposits(100).transact({'from': DSM_OWNER})

    # Get the latest block
    latest = web3_lido_integration.eth.get_block('latest')
    onwer = '0x5E362eb2c0706Bd1d134689eC75176018385430B'
    web3_lido_integration.provider.make_request('anvil_impersonateAccount', [onwer])
    web3_lido_integration.provider.make_request('anvil_setBalance',
                                                [onwer, '0x500000000000000000000000'])

    quorum = [{'type': 'deposit', 'depositRoot': '0x1b54d36f901a68c7a0a19d8ef041ae8ecea4f54c32c31f71fa717b0ca81841a9',
               'nonce': 221, 'blockNumber': 20526731,
               'blockHash': '0x1e83f8386509b288611be8643e855b88445f41a0261bf5db7f178fa4ab3004de',
               'guardianAddress': '0x70997970C51812dc3A010C7d01b50e0d17dc79C8', 'guardianIndex': 8, 'stakingModuleId': 2,
               'signature': {'r': '0x7c5d4227e65821b9ff05f79f8d5f1387a3dbaf08ca8d8bfd90f5b38a362c4596',
                             's': '0x342bc24d49a782a41ce618f15064841409a83e458c11a37d7c7f810c79bd6585', 'v': 28}},
              {'type': 'deposit', 'depositRoot': '0x1b54d36f901a68c7a0a19d8ef041ae8ecea4f54c32c31f71fa717b0ca81841a9',
               'nonce': 221, 'blockNumber': 20526731,
               'blockHash': '0x1e83f8386509b288611be8643e855b88445f41a0261bf5db7f178fa4ab3004de',
               'guardianAddress': '0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC', 'guardianIndex': 8, 'stakingModuleId': 2,
               'signature': {'r': '0x7791641b0385b8679f1793b7390e0c98bbb0c2a0aa07696357e86c73153ee815',
                             's': '0x246cd3ef672d2da59d4e4fbe938f321e74d8b5b9ab2ce79bf2faf6d6407d1049', 'v': 27}}]
    block_number = quorum[0]['blockNumber']
    block_hash = Hash32(bytes.fromhex(quorum[0]['blockHash'][2:]))
    deposit_root = Hash32(bytes.fromhex(quorum[0]['depositRoot'][2:]))
    staking_module_nonce = quorum[0]['nonce']
    payload = b''
    guardian_signs = Sender._prepare_signs_for_deposit(quorum)
    web3_lido_integration.lido.simple_dvt_staking_strategy.staking_module_contract.convert_and_deposit(
        block_number,
        block_hash,
        deposit_root,
        staking_module_nonce,
        payload,
        guardian_signs,
    ).transact({'from': onwer})
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
        gas_price_calculator_integration,
        mellow_deposit_strategy_integration,
        base_deposit_strategy_integration,
    )

    # Clear the message storage and execute the bot without any messages
    db.message_storage.messages = []
    db.execute(latest)

    # Assert that the staking module nonce has not changed
    assert web3_lido_integration.lido.staking_router.get_staking_module_nonce(module_id) == old_module_nonce

    # Execute the bot with deposit messages and assert that the nonce has increased by 1
    db.message_storage.messages = deposit_messages

    # All the mellow specific checks
    mellow_strategy = MellowDepositStrategy(web3_lido_integration)
    initial_vault_balance = web3_lido_integration.lido.simple_dvt_staking_strategy.vault_balance()
    buffered = web3_lido_integration.lido.lido.get_buffered_ether()
    unfinalized = web3_lido_integration.lido.lido_locator.withdrawal_queue_contract.unfinalized_st_eth()
    deposited_keys = mellow_strategy.deposited_keys_amount(module_id)
    assert db.execute(latest)
    assert web3_lido_integration.lido.staking_router.get_staking_module_nonce(module_id) == old_module_nonce + 1
    actual_deposited_keys = mellow_strategy.deposited_keys_amount(module_id)
    event = web3_lido_integration.lido.simple_dvt_staking_strategy.events.ConvertAndDeposit
    for e in event.get_logs(fromBlock=20526731, toBlock=latest.number + 1):
        print(e)
    actual_vault_balance = web3_lido_integration.lido.simple_dvt_staking_strategy.vault_balance()
    if buffered >= unfinalized and deposited_keys > 0 and initial_vault_balance >= variables.VAULT_DIRECT_DEPOSIT_THRESHOLD:
        assert initial_vault_balance > actual_vault_balance
    else:
        assert initial_vault_balance == actual_vault_balance
