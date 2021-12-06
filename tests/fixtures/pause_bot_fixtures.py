from tests.fixtures.common_fixtures import COMMON_FIXTURES


PAUSE_BOT_FIXTURES = {
    'eth_call': (
        (({'to': '0xDb149235B6F40dC08810AA69869783Be101790e7', 'data': '0xc7062e98'}, 'latest'), {'jsonrpc': '2.0', 'id': 11, 'result': '0x00000000000000000000000000000000000000000000000000000000000019f6'}),
        (({'to': '0xDb149235B6F40dC08810AA69869783Be101790e7', 'data': '0xb187bd26'}, '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'), {'jsonrpc': '2.0', 'id': 16, 'result': '0x0000000000000000000000000000000000000000000000000000000000000000'}),
    ),
    **COMMON_FIXTURES,
}


PAUSED_PROTOCOL_FIXTURES = {
    'eth_call': (
        (({'to': '0xDb149235B6F40dC08810AA69869783Be101790e7', 'data': '0xc7062e98'}, 'latest'), {'jsonrpc': '2.0', 'id': 15, 'result': '0x00000000000000000000000000000000000000000000000000000000000019f6'}),
        (({'to': '0xDb149235B6F40dC08810AA69869783Be101790e7', 'data': '0xb187bd26'}, '0xf7b1887b32ad3b9346f907947e2dffb5012de2b7cb7b6b84b950356237944d0c'), {'jsonrpc': '2.0', 'id': 14, 'result': '0x0000000000000000000000000000000000000000000000000000000000000001'}),
    ),
    **COMMON_FIXTURES,
}