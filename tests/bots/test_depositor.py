import unittest
from datetime import datetime, timedelta
from unittest import mock
from unittest.mock import MagicMock, Mock, patch

import pytest
import variables
from bots.depositor import DepositorBot

from tests.conftest import COUNCIL_ADDRESS_1, COUNCIL_ADDRESS_2, COUNCIL_PK_1, COUNCIL_PK_2, DSM_OWNER
from tests.utils.protocol_utils import get_deposit_message


@pytest.mark.unit
class TestGetPreferredToDepositModules(unittest.TestCase):
    def setUp(self):
        # Mock dependencies
        self.mock_w3 = MagicMock()
        self.mock_sender = MagicMock()
        self.mock_general_strategy = MagicMock()
        self.mock_csm_strategy = MagicMock()

        # Initialize the bot
        self.bot = DepositorBot(
            w3=self.mock_w3, sender=self.mock_sender, base_deposit_strategy=self.mock_general_strategy, csm_strategy=self.mock_csm_strategy
        )

        # Set up initial state
        self.now = datetime.now()
        self.bot._module_last_heart_beat = {
            1: self.now - timedelta(minutes=2),  # Healthy
            2: self.now - timedelta(minutes=10),  # Unhealthy
            3: self.now - timedelta(minutes=4),  # Healthy
        }

        # Mock whitelist
        variables.DEPOSIT_MODULES_WHITELIST = [1, 2, 3]

    @patch('datetime.datetime')
    def test_get_preferred_to_deposit_modules(self, mock_datetime):
        mock_datetime.now.return_value = self.now

        # Mock staking router module IDs and digests
        self.mock_w3.lido.staking_router.get_staking_module_ids.return_value = [1, 2, 3]
        self.mock_w3.lido.staking_router.get_staking_module_digests.return_value = [
            [0, 0, [1], [5, 2]],  # Module 1: 3 validators
            [0, 0, [2], [7, 6]],  # Module 2: 1 validator
            [0, 0, [3], [10, 4]],  # Module 3: 6 validators
        ]

        # Mock module healthiness and quorum
        self.bot._get_quorum = MagicMock(side_effect=[True, False, True])
        self.bot._is_module_healthy = MagicMock(side_effect=[True, False, True])

        # Call the method
        result = self.bot._get_preferred_to_deposit_modules()

        # Expected output: Module 3 (6 validators, healthy)
        self.assertEqual([3], result)

        # Verify calls to dependent methods
        self.bot._get_quorum.assert_any_call(1)
        self.bot._get_quorum.assert_any_call(2)
        self.bot._get_quorum.assert_any_call(3)
        self.bot._is_module_healthy.assert_any_call(1)
        self.bot._is_module_healthy.assert_any_call(2)
        self.bot._is_module_healthy.assert_any_call(3)

    def test_empty_whitelist(self):
        # Empty whitelist
        variables.DEPOSIT_MODULES_WHITELIST = []

        # Mock module IDs and digests
        self.mock_w3.lido.staking_router.get_staking_module_ids.return_value = []
        self.mock_w3.lido.staking_router.get_staking_module_digests.return_value = []

        # Call the method
        result = self.bot._get_preferred_to_deposit_modules()

        # Expected output: No modules available
        self.assertEqual([], result)

    def test_no_healthy_modules(self):
        # Mock staking router module IDs and digests
        self.mock_w3.lido.staking_router.get_staking_module_ids.return_value = [1, 2]
        self.mock_w3.lido.staking_router.get_staking_module_digests.return_value = [
            [0, 0, [1], [3, 1]],  # Module 1: 2 validators
            [0, 0, [2], [7, 5]],  # Module 2: 2 validators
        ]

        # Mock module healthiness and quorum
        self.bot._get_quorum = MagicMock(side_effect=[True, True, True])
        self.bot._is_module_healthy = MagicMock(side_effect=[False, False])

        # Call the method
        result = self.bot._get_preferred_to_deposit_modules()

        # Expected output: Include all modules as no healthy modules are found
        self.assertEqual([1, 2], result)

    def test_module_sorting_by_validator_difference(self):
        # Mock staking router module IDs and digests
        self.mock_w3.lido.staking_router.get_staking_module_ids.return_value = [1, 2, 3]
        self.mock_w3.lido.staking_router.get_staking_module_digests.return_value = [
            [0, 0, [1], [6, 2]],  # Module 1: 4 validators
            [0, 0, [2], [8, 3]],  # Module 2: 5 validators
            [0, 0, [3], [7, 6]],  # Module 3: 1 validator
        ]

        # Mock module healthiness and quorum
        self.bot._get_quorum = MagicMock(side_effect=[True, True, True])
        self.bot._is_module_healthy = MagicMock(side_effect=[True, True, True])

        # Call the method
        result = self.bot._get_preferred_to_deposit_modules()

        # Expected output: Sorted by validator difference: Module 2, Module 1, Module 3
        self.assertEqual([2], result)


@pytest.fixture
def depositor_bot(
    web3_lido_unit,
    deposit_transaction_sender,
    base_deposit_strategy,
    block_data,
    csm_strategy,
):
    with mock.patch('web3.eth.Eth.chain_id', new_callable=mock.PropertyMock) as _:
        variables.MESSAGE_TRANSPORTS = ''
        variables.DEPOSIT_MODULES_WHITELIST = [1, 2]
        web3_lido_unit.lido.staking_router.get_staking_module_ids = Mock(return_value=[1, 2])
        web3_lido_unit.eth.get_block = Mock(return_value=block_data)
        yield DepositorBot(web3_lido_unit, deposit_transaction_sender, base_deposit_strategy, csm_strategy)


@pytest.fixture
def deposit_message():
    yield {
        'type': 'deposit',
        'depositRoot': '0x64dcf70a7ad7fc6b1a55db6b08b86e9d80736259916fcaef98f4710f0bac687b',
        'nonce': 12,
        'blockNumber': 10,
        'blockHash': '0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532',
        'guardianAddress': '0x43464Fe06c18848a2E2e913194D64c1970f4326a',
        'guardianIndex': 8,
        'stakingModuleId': 1,
        'signature': {
            'r': '0xc2235eb6983f80d19158f807d5d90d93abec52034ea7184bbf164ba211f00116',
            's': '0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0',
            '_vs': '0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0',
            'recoveryParam': 0,
            'v': 27,
        },
        'app': {'version': '1.0.3', 'name': 'lido-council-daemon'},
    }


@pytest.mark.unit
def test_depositor_one_module_deposited(depositor_bot, block_data):
    modules = list(range(10))
    depositor_bot._get_quorum = Mock(return_value=True)

    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=10 * 32 * 10**18)
    depositor_bot.w3.lido.staking_router.get_staking_module_ids = Mock(return_value=modules)
    depositor_bot.w3.lido.staking_router.get_staking_module_max_deposits_count = Mock(return_value=0)
    depositor_bot.w3.lido.deposit_security_module.get_max_deposits = Mock(return_value=10)
    depositor_bot.w3.lido.staking_router.get_staking_module_digests = Mock(
        return_value=[
            (0, 0, (1,), (10, 20, 10)),
            (0, 0, (2,), (0, 10, 10)),
        ]
    )
    depositor_bot._check_balance = Mock()
    depositor_bot._deposit_to_module = Mock(return_value=True)
    depositor_bot.execute(block_data)

    assert depositor_bot._deposit_to_module.call_count == 2


@pytest.mark.unit
@pytest.mark.parametrize(
    'is_depositable,quorum,is_gas_price_ok,is_deposited_keys_amount_ok',
    [
        pytest.param(True, True, True, True, marks=pytest.mark.xfail(raises=AssertionError, strict=True)),
        (False, True, True, True),
        (True, False, True, True),
        (True, True, False, True),
        (True, True, True, False),
    ],
)
def test_depositor_deposit_to_module(depositor_bot, is_depositable, quorum, is_gas_price_ok, is_deposited_keys_amount_ok):
    depositor_bot.w3.lido.deposit_security_module.can_deposit = Mock(return_value=is_depositable)
    depositor_bot._get_quorum = Mock(return_value=quorum)
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=is_gas_price_ok)
    strategy.can_deposit_keys_based_on_ether = Mock(return_value=is_deposited_keys_amount_ok)
    depositor_bot._select_strategy = Mock(return_value=strategy)
    depositor_bot.prepare_and_send_tx = Mock()

    assert not depositor_bot._deposit_to_module(1)
    assert depositor_bot.prepare_and_send_tx.call_count == 0


@pytest.fixture
def setup_deposit_message(depositor_bot, block_data):
    depositor_bot.w3.eth.get_block = Mock(return_value=block_data)
    depositor_bot.w3.lido.deposit_contract.get_deposit_root = Mock(
        return_value=b'd\xdc\xf7\nz\xd7\xfck\x1aU\xdbk\x08\xb8n\x9d\x80sbY\x91o\xca\xef\x98\xf4q\x0f\x0b\xach{'
    )
    depositor_bot.w3.lido.staking_router.get_staking_module_nonce = Mock(return_value=12)
    depositor_bot.w3.lido.deposit_security_module.get_guardians = Mock(return_value=['0x43464Fe06c18848a2E2e913194D64c1970f4326a'])


@pytest.mark.unit
def test_depositor_message_actualizer(setup_deposit_message, depositor_bot, deposit_message, block_data):
    message_filter = depositor_bot._get_message_actualize_filter()
    assert list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_depositor_message_actualizer_not_guardian(setup_deposit_message, depositor_bot, deposit_message, block_data):
    depositor_bot.w3.lido.deposit_security_module.get_guardians = Mock(return_value=['0x13464Fe06c18848a2E2e913194D64c1970f4326a'])
    message_filter = depositor_bot._get_message_actualize_filter()
    assert not list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_depositor_message_actualizer_no_selected_module(setup_deposit_message, depositor_bot, deposit_message, block_data):
    second = deposit_message.copy()
    second['stakingModuleId'] = 2

    message_filter = depositor_bot._get_module_messages_filter(2)
    assert not list(
        filter(
            message_filter,
            [
                deposit_message,
            ],
        )
    )
    assert len(list(filter(message_filter, [deposit_message, second]))) == 1


@pytest.mark.unit
def test_depositor_message_actualizer_outdated(setup_deposit_message, depositor_bot, deposit_message, block_data):
    deposit_message['blockNumber'] = block_data['number'] - 250
    message_filter = depositor_bot._get_message_actualize_filter()
    assert not list(filter(message_filter, [deposit_message]))

    deposit_message['blockNumber'] = block_data['number'] - 150
    assert list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_depositor_message_actualizer_nonce(setup_deposit_message, depositor_bot, deposit_message, block_data):
    message_filter = depositor_bot._get_module_messages_filter(1)

    assert list(filter(message_filter, [deposit_message]))

    deposit_message['nonce'] -= 10

    assert not list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_depositor_message_actualizer_root(setup_deposit_message, depositor_bot, deposit_message, block_data):
    deposit_message['depositRoot'] += '0x55dcf70a7ad7fc6b1a55db6b08b86e9d80736259916fcaef98f4710f0bac687b'
    message_filter = depositor_bot._get_message_actualize_filter()
    assert not list(filter(message_filter, [deposit_message]))

    deposit_message['blockNumber'] = block_data['number'] + 100
    assert list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_get_quorum(depositor_bot, setup_deposit_message):
    deposit_messages = [
        {
            'blockHash': '0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532',
            'guardianAddress': '0x43464Fe06c18848a2E2e913194D64c1970f4326a',
        },
        {
            'blockHash': '0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532',
            'guardianAddress': '0x43464Fe06c18848a2E2e913194D64c1970f4326a',
        },
        {
            'blockHash': '0x232e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532',
            'guardianAddress': '0x43464Fe06c18848a2E2e913194D64c1970f4326a',
        },
        {
            'blockHash': '0x232e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532',
            'guardianAddress': '0x33464Fe06c18848a2E2e913194D64c1970f4326a',
        },
    ]

    depositor_bot._get_module_messages_filter = Mock(return_value=lambda x: True)
    depositor_bot.w3.lido.deposit_security_module.get_guardian_quorum = Mock(return_value=2)
    depositor_bot.message_storage.get_messages_and_actualize = Mock(return_value=deposit_messages[:2])
    assert not depositor_bot._get_quorum(1)

    depositor_bot.message_storage.get_messages_and_actualize = Mock(return_value=deposit_messages[:4])
    quorum = depositor_bot._get_quorum(1)
    assert quorum
    assert deposit_messages[2] in quorum
    assert deposit_messages[3] in quorum


@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration,module_id',
    [[{'block': 19628126}, 1], [{'block': 19628126}, 2]],
    indirect=['web3_provider_integration'],
)
def test_depositor_bot(
    web3_provider_integration,
    web3_lido_integration,
    deposit_transaction_sender_integration,
    base_deposit_strategy_integration,
    gas_price_calculator_integration,
    csm_strategy_integration,
    module_id,
    add_accounts_to_guardian,
):
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
                'value': 10000 * 10**18,
            }
        )

    # Set the maximum number of deposits
    web3_lido_integration.lido.deposit_security_module.functions.setMaxDeposits(100).transact({'from': DSM_OWNER})

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
    # this is done to ensure the deposit will be done to the target module
    web3_lido_integration.lido.staking_router.get_staking_module_ids = Mock(return_value=[module_id])

    # Initialize the DepositorBot
    db: DepositorBot = DepositorBot(
        web3_lido_integration,
        deposit_transaction_sender_integration,
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
    assert db.execute(latest)
    assert web3_lido_integration.lido.staking_router.get_staking_module_nonce(module_id) == old_module_nonce + 1
