"""
Ad-hoc script to test X-Flashbots-Signature variants against a live relay.

Tries every combination of:
  - signing approach: primitive= (32-byte hash) vs text= (hex string)
  - JSON body: compact vs spaced
  - signature: with/without 0x prefix
  - address: checksum vs lowercase

Usage:
    RELAY_RPC=https://relay.flashbots.net \
    AUCTION_BUNDLER_PRIVATE_KEY=0x<your_key> \
    poetry run python scripts/test_relay_signature.py
"""

import json
import os
import sys

import requests
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

RELAY_RPC = os.environ.get('RELAY_RPC', 'https://rpc.flashbots.net')
PRIVATE_KEY = os.environ.get('AUCTION_BUNDLER_PRIVATE_KEY')

if not PRIVATE_KEY:
    print('ERROR: set AUCTION_BUNDLER_PRIVATE_KEY env var')
    sys.exit(1)

signer = Account.from_key(PRIVATE_KEY)
print(f'Signer address: {signer.address}')
print(f'Relay: {RELAY_RPC}')


def make_dummy_raw_tx() -> str:
    """A real RLP-encoded EIP-1559 tx, signed with the test key. Will fail on-chain but is structurally valid."""
    tx = {
        'chainId': 1,
        'nonce': 0,
        'maxFeePerGas': 30_000_000_000,
        'maxPriorityFeePerGas': 1_000_000_000,
        'gas': 21000,
        'to': '0x0000000000000000000000000000000000000000',
        'value': 0,
        'data': b'',
        'type': 2,
    }
    signed = signer.sign_transaction(tx)
    return '0x' + signed.raw_transaction.hex()


RAW_TX = make_dummy_raw_tx()
print(f'Dummy raw tx (first 20 chars): {RAW_TX[:20]}...\n')


def body_template():
    return {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'eth_sendPrivateTransaction',
        'params': [{'tx': RAW_TX}],
    }


def run_variants(use_primitive: bool):
    sign_label = 'primitive=' if use_primitive else 'text=hex'

    for body_str, body_label in [
        (json.dumps(body_template(), separators=(',', ':')), 'compact'),
        (json.dumps(body_template()), 'spaced'),
    ]:
        body_hash = Web3.keccak(text=body_str)
        message = encode_defunct(primitive=body_hash) if use_primitive else encode_defunct(text=body_hash.hex())
        sig_bytes = signer.sign_message(message).signature

        sig_normalized = sig_bytes[:64] + bytes([sig_bytes[64] - 27])  # v: 27/28 → 0/1
        for sig_str, sig_label in [
            (sig_bytes.hex(), 'v=27/28 no-0x'),
            ('0x' + sig_bytes.hex(), 'v=27/28 0x'),
            ('0x' + sig_normalized.hex(), 'v=0/1 0x'),
            ('0x' + sig_bytes[:64].hex(), 'no-v 0x'),
        ]:
            for addr, addr_label in [
                (signer.address, 'checksum'),
                (signer.address.lower(), 'lower'),
            ]:
                raw = requests.post(
                    url=RELAY_RPC,
                    data=body_str,
                    headers={
                        'Content-Type': 'application/json',
                        'X-Flashbots-Signature': f'{addr}:{sig_str}',
                    },
                    timeout=10,
                )
                error_msg = ''
                if raw.text:
                    error_msg = raw.json().get('error', {}).get('message', '')
                ok = raw.status_code != 403 or 'signature' not in error_msg.lower()
                marker = '✓' if ok else '✗'
                print(f'  {marker} sign={sign_label} body={body_label} sig={sig_label} addr={addr_label} → {raw.status_code} {error_msg!r}')


# Sanity check: verify the signature locally before hitting the relay
_body = json.dumps(body_template(), separators=(',', ':'))
_hash = Web3.keccak(text=_body)
_msg = encode_defunct(primitive=_hash)
_signed = signer.sign_message(_msg)
_recovered = Account.recover_message(_msg, signature=_signed.signature)
print(f'Local signature check: recovered={_recovered} match={_recovered == signer.address}')
print(f'Signature bytes (hex): {_signed.signature.hex()}')
print(f'v byte (last byte): {_signed.signature[-1]} (expected 27 or 28 for eth_account, 0 or 1 for raw ecrecover)\n')

# THE FIX: Go's crypto.Keccak256Hash().Hex() returns "0x..." WITH 0x prefix.
# accounts.TextHash signs that 66-char string. Python's HexBytes.hex() returns
# WITHOUT 0x, so we must add it explicitly.
print('--- THE FIX: text= with 0x prefix ---')
for body_str, body_label in [
    (json.dumps(body_template(), separators=(',', ':')), 'compact'),
    (json.dumps(body_template()), 'spaced'),
]:
    body_hash_hex = '0x' + Web3.keccak(text=body_str).hex()
    message = encode_defunct(text=body_hash_hex)
    sig_bytes = signer.sign_message(message).signature
    for sig_str, sig_label in [('0x' + sig_bytes.hex(), '0x'), (sig_bytes.hex(), 'no-0x')]:
        raw = requests.post(
            url=RELAY_RPC,
            data=body_str,
            headers={'Content-Type': 'application/json', 'X-Flashbots-Signature': f'{signer.address}:{sig_str}'},
            timeout=10,
        )
        error_msg = raw.json().get('error', {}).get('message', '') if raw.text else ''
        ok = raw.status_code != 403 or 'signature' not in error_msg.lower()
        print(f'  {"✓" if ok else "✗"} body={body_label} sig={sig_label} → {raw.status_code} {error_msg!r}')

print()
run_variants(use_primitive=True)
print()
run_variants(use_primitive=False)

# Extra: sign the raw body text directly (no pre-hashing)
print('\n--- sign=raw body (no pre-hash) ---')
for body_str, body_label in [
    (json.dumps(body_template(), separators=(',', ':')), 'compact'),
    (json.dumps(body_template()), 'spaced'),
]:
    message = encode_defunct(text=body_str)
    sig_bytes = signer.sign_message(message).signature
    for sig_str, sig_label in [(sig_bytes.hex(), 'no-0x'), ('0x' + sig_bytes.hex(), '0x')]:
        raw = requests.post(
            url=RELAY_RPC,
            data=body_str,
            headers={
                'Content-Type': 'application/json',
                'X-Flashbots-Signature': f'{signer.address}:{sig_str}',
            },
            timeout=10,
        )
        error_msg = raw.json().get('error', {}).get('message', '') if raw.text else ''
        ok = raw.status_code != 403 or 'signature' not in error_msg.lower()
        print(f'  {"✓" if ok else "✗"} body={body_label} sig={sig_label} → {raw.status_code} {error_msg!r}')
