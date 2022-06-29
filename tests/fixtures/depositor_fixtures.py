from tests.fixtures.common_fixtures import COMMON_FIXTURES
from tests.fixtures.gas_fee_fixtures import GAS_FEE_FIXTURES


DEPOSITOR_BASE_FIXTURES = {
    'eth_call': (
        (({'to': '0x710B3303fB508a84F10793c1106e32bE873C24cd', 'data': '0x062b662e'}, 'latest'), {'jsonrpc': '2.0', 'id': 11, 'result': '0x0000000000000000000000000000000000000000000000000000000000000001'}),
        (({'to': '0x710B3303fB508a84F10793c1106e32bE873C24cd', 'data': '0xc6dda2c3'}, 'latest'), {'jsonrpc': '2.0', 'id': 12, 'result': '0x1670745baff8f26a6c2e451bc4eedecf0009a8271dcf5d224e8ab295f22b0863'}),
        (({'to': '0x00000000219ab540356cBB839Cbe05303d7705Fa', 'data': '0xc5f2892f'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x4eff65af4dac60f23b625a5d9c80f9cc36b0754cd1db072cd47bd6d053e2f94e'}),
        (({'to': '0x55032650b14df07b85bF18A3a3eC8E0Af2e028d5', 'data': '0xd07442f1'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x0000000000000000000000000000000000000000000000000000000000000043'}),
        (({'to': '0x710B3303fB508a84F10793c1106e32bE873C24cd', 'data': '0xe78a5875'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x0000000000000000000000000000000000000000000000000000000000000001'}),
        (({'to': '0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84', 'data': '0x47b714e0'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x0000000000000000000000000000000000000000001111271e5ec338bae335ab'}),
        (({'from': '0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84', 'to': '0x55032650b14df07b85bF18A3a3eC8E0Af2e028d5', 'data': '0x41bc716f0000000000000000000000000000000000000000000000000000000000000001'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x000000000000000000000000000000000000000000000000000000000000004000000000000000000000000000000000000000000000000000000000000000a00000000000000000000000000000000000000000000000000000000000000030a6c073f8bc871eea37b7b6dacaaac419473076fb05d7a4631173d1dc70c2adb47b9c0235d0ffb29e240ccab19e6152e8000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000060a9d0b8d92e82182d933a26786a7b394843d5d19ef565b0214b2d9b7e82f6eb66d5cade6cbad25256ee7555b33c2c2f861148ec0ab495baefd06ff503c6c9006ff68e307f8a0f911573093d8258522d2666619a396d7fbe2cefb84940a1a48826'}),
    ),
    'eth_accounts': (
        ((), {'jsonrpc': '2.0', 'id': 0, 'result': []}),
    ),
    'eth_getBalance': (
        (['0x3f17f1962B36e491b30A40b2405849e597Ba5FB5', {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}], {'jsonrpc': '2.0', 'id': 0, 'result': '0xffffffffffffffff'}),
    ),
    **GAS_FEE_FIXTURES,
    **COMMON_FIXTURES,
}

DEPOSITOR_BASE_FIXTURES_SMALL_BALANCE = {
    **DEPOSITOR_BASE_FIXTURES,
    'eth_getBalance': (
        (['0x3f17f1962B36e491b30A40b2405849e597Ba5FB5', {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}], {'jsonrpc': '2.0', 'id': 0, 'result': '0xfff'}),
    ),
}

DEPOSITOR_FIXTURES_WITH_HIGH_GAS = {
    **DEPOSITOR_BASE_FIXTURES,
    'eth_getBlockByNumber': (
        (('latest', False), {'jsonrpc': '2.0', 'id': 15,
                             'result': {'baseFeePerGas': '0xffbf193d7', 'difficulty': '0x29aa4945316813',
                                        'extraData': '0x486976656f6e2065752d6865617679', 'gasLimit': '0x1c9c380',
                                        'gasUsed': '0x65fe32',
                                        'hash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c',
                                        'logsBloom': '0x092000900100008810000000805c080000000000000008000001606044086000080101400080020080005883004901909220824588002c900088840040212040880004004021410a8822000810002020800100088240050104000c03802844101a00002012004482014408221000189000008840081064082000003404288c0800820120104030000044008a0821000241000401910080180021084201100401071880289001a00202000080080810401000001021802010183c1000100c2000210003032200081028010d20005600400000024203991230848a000201026008a131202a0400090000419000010008a00000a880305102502000090000001220',
                                        'miner': '0x1ad91ee08f21be3de0ba2ba6918e714da6b45836',
                                        'mixHash': '0x98630b099b638f63942ba8ff6b65b8a7b26dd38c6e125528104aeff50c01d02a',
                                        'nonce': '0x0000030ab4a3b4d8', 'number': '0xd17320',
                                        'parentHash': '0xc2ea9185d4821a13da4a2975c85673eff34944e92c0b5d3516a3b4482ac2ab58',
                                        'receiptsRoot': '0x3f30031d0a235a05e183de7416a42a2bdef7cbcbabd581282cfc8b2e239b9abe',
                                        'sha3Uncles': '0x1dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d49347',
                                        'size': '0x63ff',
                                        'stateRoot': '0x22b47b4d4370336d5a0ffb7423b1a40257b23fdcfe28a3ec45a21e60590e1dd8',
                                        'timestamp': '0x61a88d67', 'totalDifficulty': '0x78d36e1e439ded9742d',
                                        'transactions': [],
                                        'transactionsRoot': '0xfa0b8a5325ea94fd117575c1aedf498ccaccdca636334f938b3b3184426f749c',
                                        'uncles': []}}),
        (('pending', False), {'jsonrpc': '2.0', 'id': 0,
                              'result': {'baseFeePerGas': '0x994a1533d7f', 'difficulty': '0x29be4af025287c',
                                         'extraData': '0xd883010a0c846765746888676f312e31372e33856c696e7578',
                                         'gasLimit': '0x1c95111', 'gasUsed': '0x1b68674', 'hash': None,
                                         'logsBloom': '0x57aa6b0f5ba66e9fbecbbec7849fcff758cddfdfbeb53b3ee5e9bb7d7f7bdfcf79fe7df2bdccb9b3d3e9dff8fcffd7d5ba2bf9139feffdb5f73ffe3bb23ef82d26fa5fa7af73bf2ce9afb63efaff5f7f6ef6387464cfb554b5f7b7ff96e35f753a41fbbf7fb5de9abf76d7d87dbefff6fffaf271ffbf37cf769f5d37b4affeed7f12b75b57fef817f3d72fbd0ff366cc5575ad3ddf361f2dcbae546fe9bfedd6bb5babcb6eee27f9eefd4fd3fdb94f29fb7eca707fffa7f355f3973e1efdbe93efebfbf7cda9997baf3bd9af57fbfd55ffeeff585f0efd7f779fbfab78de60fd8cfe3debfef5c3bdf9d53f9f97adff87c3e3cdc9f1f6f3f9255ffa56e8db7bef',
                                         'miner': None,
                                         'mixHash': '0x0000000000000000000000000000000000000000000000000000000000000000',
                                         'nonce': None, 'number': '0xd18e3e',
                                         'parentHash': '0x01802ffbfec338704593f416bb06005afb88c2a343d5a405d6d3f5359422a41c',
                                         'receiptsRoot': '0xa67cb02111fe0430601215c03aa86a2a95a032487c1644f7561e7d7ef58a4677',
                                         'sha3Uncles': '0x1dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d49347',
                                         'size': '0x19b97',
                                         'stateRoot': '0xdbffeb5d663c710239c0b8bf57b562848e8bd6d55117ad29cbb9fe930ac0e11a',
                                         'timestamp': '0x61aa03ce', 'totalDifficulty': None, 'transactions': [],
                                         'transactionsRoot': '0xaeade20445251ded37c5efce433e9a526683d340da591774ac14acb4ca7a11d3',
                                         'uncles': []}}),
    ),
}

DEPOSITOR_FIXTURES_WITH_DEPOSIT_PROHIBIT = {
    **DEPOSITOR_BASE_FIXTURES,
    'eth_call': (
        (({'to': '0x710B3303fB508a84F10793c1106e32bE873C24cd', 'data': '0x062b662e'}, 'latest'), {'jsonrpc': '2.0', 'id': 11, 'result': '0x0000000000000000000000000000000000000000000000000000000000000001'}),
        (({'to': '0x710B3303fB508a84F10793c1106e32bE873C24cd', 'data': '0xc6dda2c3'}, 'latest'), {'jsonrpc': '2.0', 'id': 12, 'result': '0x1670745baff8f26a6c2e451bc4eedecf0009a8271dcf5d224e8ab295f22b0863'}),
        (({'to': '0x00000000219ab540356cBB839Cbe05303d7705Fa', 'data': '0xc5f2892f'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x4eff65af4dac60f23b625a5d9c80f9cc36b0754cd1db072cd47bd6d053e2f94e'}),
        (({'to': '0x55032650b14df07b85bF18A3a3eC8E0Af2e028d5', 'data': '0xd07442f1'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x0000000000000000000000000000000000000000000000000000000000000043'}),
        (({'to': '0x710B3303fB508a84F10793c1106e32bE873C24cd', 'data': '0xe78a5875'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x0000000000000000000000000000000000000000000000000000000000000000'}),
        (({'to': '0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84', 'data': '0x47b714e0'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x0000000000000000000000000000000000000000000011271e5ec338bae335ab'}),
        (({'from': '0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84', 'to': '0x55032650b14df07b85bF18A3a3eC8E0Af2e028d5', 'data': '0x41bc716f0000000000000000000000000000000000000000000000000000000000000001'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x000000000000000000000000000000000000000000000000000000000000004000000000000000000000000000000000000000000000000000000000000000a00000000000000000000000000000000000000000000000000000000000000030a6c073f8bc871eea37b7b6dacaaac419473076fb05d7a4631173d1dc70c2adb47b9c0235d0ffb29e240ccab19e6152e8000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000060a9d0b8d92e82182d933a26786a7b394843d5d19ef565b0214b2d9b7e82f6eb66d5cade6cbad25256ee7555b33c2c2f861148ec0ab495baefd06ff503c6c9006ff68e307f8a0f911573093d8258522d2666619a396d7fbe2cefb84940a1a48826'}),
    ),
}

DEPOSITOR_FIXTURES_NOT_ENOUGH_BUFFERED_ETHER = {
    **DEPOSITOR_BASE_FIXTURES,
    'eth_call': (
        (({'to': '0x710B3303fB508a84F10793c1106e32bE873C24cd', 'data': '0x062b662e'}, 'latest'), {'jsonrpc': '2.0', 'id': 11, 'result': '0x0000000000000000000000000000000000000000000000000000000000000001'}),
        (({'to': '0x710B3303fB508a84F10793c1106e32bE873C24cd', 'data': '0xc6dda2c3'}, 'latest'), {'jsonrpc': '2.0', 'id': 12, 'result': '0x1670745baff8f26a6c2e451bc4eedecf0009a8271dcf5d224e8ab295f22b0863'}),
        (({'to': '0x00000000219ab540356cBB839Cbe05303d7705Fa', 'data': '0xc5f2892f'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x4eff65af4dac60f23b625a5d9c80f9cc36b0754cd1db072cd47bd6d053e2f94e'}),
        (({'to': '0x55032650b14df07b85bF18A3a3eC8E0Af2e028d5', 'data': '0xd07442f1'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x0000000000000000000000000000000000000000000000000000000000000043'}),
        (({'to': '0x710B3303fB508a84F10793c1106e32bE873C24cd', 'data': '0xe78a5875'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x0000000000000000000000000000000000000000000000000000000000000001'}),
        (({'to': '0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84', 'data': '0x47b714e0'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x0000000000000000000000000000000000000000000000000e5ec338bae335ab'}),
        (({'from': '0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84', 'to': '0x55032650b14df07b85bF18A3a3eC8E0Af2e028d5', 'data': '0x41bc716f0000000000000000000000000000000000000000000000000000000000000001'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x000000000000000000000000000000000000000000000000000000000000004000000000000000000000000000000000000000000000000000000000000000a00000000000000000000000000000000000000000000000000000000000000030a6c073f8bc871eea37b7b6dacaaac419473076fb05d7a4631173d1dc70c2adb47b9c0235d0ffb29e240ccab19e6152e8000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000060a9d0b8d92e82182d933a26786a7b394843d5d19ef565b0214b2d9b7e82f6eb66d5cade6cbad25256ee7555b33c2c2f861148ec0ab495baefd06ff503c6c9006ff68e307f8a0f911573093d8258522d2666619a396d7fbe2cefb84940a1a48826'}),
    ),
}

DEPOSITOR_FIXTURES_NO_FREE_KEYS = {
    **DEPOSITOR_BASE_FIXTURES,
    'eth_call': (
        (({'to': '0x710B3303fB508a84F10793c1106e32bE873C24cd', 'data': '0x062b662e'}, 'latest'), {'jsonrpc': '2.0', 'id': 11, 'result': '0x0000000000000000000000000000000000000000000000000000000000000001'}),
        (({'to': '0x710B3303fB508a84F10793c1106e32bE873C24cd', 'data': '0xc6dda2c3'}, 'latest'), {'jsonrpc': '2.0', 'id': 12, 'result': '0x1670745baff8f26a6c2e451bc4eedecf0009a8271dcf5d224e8ab295f22b0863'}),
        (({'to': '0x00000000219ab540356cBB839Cbe05303d7705Fa', 'data': '0xc5f2892f'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x4eff65af4dac60f23b625a5d9c80f9cc36b0754cd1db072cd47bd6d053e2f94e'}),
        (({'to': '0x55032650b14df07b85bF18A3a3eC8E0Af2e028d5', 'data': '0xd07442f1'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x0000000000000000000000000000000000000000000000000000000000000043'}),
        (({'to': '0x710B3303fB508a84F10793c1106e32bE873C24cd', 'data': '0xe78a5875'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x0000000000000000000000000000000000000000000000000000000000000001'}),
        (({'to': '0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84', 'data': '0x47b714e0'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x0000000000000000000000000000000000000000000011271e5ec338bae335ab'}),
        (({'from': '0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84', 'to': '0x55032650b14df07b85bF18A3a3eC8E0Af2e028d5', 'data': '0x41bc716f0000000000000000000000000000000000000000000000000000000000000001'}, {'blockHash': '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'}), {'jsonrpc': '2.0', 'id': 0, 'result': '0x0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'}),
    ),
}
