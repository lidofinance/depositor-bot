from transport.msg_types.deposit import DepositMessageSchema

deposit_prefix = '0x1670745baff8f26a6c2e451bc4eedecf0009a8271dcf5d224e8ab295f22b0863'

deposit_messages = [
    {
        'type': 'deposit',
        'depositRoot': '0x106d039f9484a78fdbe081384f3b09822ca3e9336a1c25ad0285eb23d2069d5f',
        'keysOpIndex': 2430,
        'blockNumber': 15392540,
        'blockHash': '0x05b93378348344e17032b8d4c2b7f4a4bdb917a24979b8c1a90444e7805f44ba',
        'guardianAddress': '0x5fd0dDbC3351d009eb3f88DE7Cd081a614C519F1',
        'guardianIndex': 0,
        'nonce': 1,
        'signature': {
            'r': '0xd447223e7f2cb9ffd8031ffeca53c5c4470df6d9ab4e719faaa7d62be213edea',
            '_vs': '0xce85730e43f592d3f52288bc6c990898623ef03eaee808177e8ea629faf5290c',
            'recoveryParam': 1,
        },
        'app': {'version': '1.6.0', 'name': 'lido-council-daemon'},
        'stakingModuleId': 2,
    },
    {
        'type': 'deposit',
        'depositRoot': '0x106d039f9484a78fdbe081384f3b09822ca3e9336a1c25ad0285eb23d2069d5f',
        'keysOpIndex': 2430,
        'blockNumber': 15392540,
        'blockHash': '0x05b93378348344e17032b8d4c2b7f4a4bdb917a24979b8c1a90444e7805f44ba',
        'guardianAddress': '0xf82D88217C249297C6037BA77CE34b3d8a90ab43',
        'guardianIndex': 3,
        'nonce': 2,
        'signature': {
            'r': '0x40b53faa5ee2cfb37f5fc2e4cc4e16fb054af31d3960ade0d5003a2fc1ce8f8b',
            '_vs': '0x706d9e9e957181086f5b56aa27ff91ad22324c50c31b02d40482dab861dac005',
            'recoveryParam': 0,
        },
        'app': {'version': '1.6.0', 'name': 'lido-council-daemon'},
        'stakingModuleId': 2,
    },
    {
        'type': 'deposit',
        'depositRoot': '0x106d039f9484a78fdbe081384f3b09822ca3e9336a1c25ad0285eb23d2069d5f',
        'keysOpIndex': 2430,
        'blockNumber': 15392540,
        'blockHash': '0x05b93378348344e17032b8d4c2b7f4a4bdb917a24979b8c1a90444e7805f44ba',
        'guardianAddress': '0x14D5d5B71E048d2D75a39FfC5B407e3a3AB6F314',
        'guardianIndex': 2,
        'nonce': 3,
        'signature': {
            'r': '0xcc6a112e8370f0073a5f47f18cacef4ddb22144cdcfa77894697295d849c4527',
            '_vs': '0x0e84e80b8c34cfff2fc5521a446dad13fa5cb0090d9d729264beb821c12a9b75',
            'recoveryParam': 0,
        },
        'app': {'version': '1.6.0', 'name': 'lido-council-daemon'},
        'stakingModuleId': 2,
    },
    {
        'type': 'deposit',
        'depositRoot': '0x106d039f9484a78fdbe081384f3b09822ca3e9336a1c25ad0285eb23d2069d5f',
        'keysOpIndex': 2430,
        'blockNumber': 15392540,
        'blockHash': '0x05b93378348344e17032b8d4c2b7f4a4bdb917a24979b8c1a90444e7805f44ba',
        'guardianAddress': '0x7912Fa976BcDe9c2cf728e213e892AD7588E6AaF',
        'guardianIndex': 1,
        'nonce': 4,
        'signature': {
            'r': '0x1c658dd9f59570d54dbd1a0f531eee25ec7fa060baef1650ee69835f07bf40c5',
            's': '0x772399ccf32d4b5d557a494fcb8b794d5a434e62cbb57786bc2b749c3d636798',
            '_vs': '0x772399ccf32d4b5d557a494fcb8b794d5a434e62cbb57786bc2b749c3d636798',
            'recoveryParam': 0,
            'v': 27,
        },
        'app': {'version': '1.6.0', 'name': 'lido-council-daemon'},
        'stakingModuleId': 2,
    },
    {
        'type': 'deposit',
        'depositRoot': '0x106d039f9484a78fdbe081384f3b09822ca3e9336a1c25ad0285eb23d2069d5f',
        'keysOpIndex': 2430,
        'blockNumber': 15392540,
        'blockHash': '0x05b93378348344e17032b8d4c2b7f4a4bdb917a24979b8c1a90444e7805f44ba',
        'guardianAddress': '0xd4EF84b638B334699bcf5AF4B0410B8CCD71943f',
        'guardianIndex': 5,
        'nonce': 5,
        'signature': {
            'r': '0x287aef9f07fc451956893baea690206142e6f54a6d7d5a3370a437ef2bbed436',
            's': '0x288329c588cc76ba3262bca83d322748a6e24267c703315e0b97d98b25749e6d',
            '_vs': '0xa88329c588cc76ba3262bca83d322748a6e24267c703315e0b97d98b25749e6d',
            'recoveryParam': 1,
            'v': 28,
        },
        'app': {'version': '1.6.0', 'name': 'lido-council-daemon'},
        'stakingModuleId': 2,
    },
]


def test_deposit_schema():
    for dm in deposit_messages:
        assert DepositMessageSchema.is_valid(dm)
