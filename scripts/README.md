# scripts/

## test_relay_signature.py

Ad-hoc tool for verifying that the `X-Flashbots-Signature` header is accepted by a live Flashbots relay.

### Background

The Flashbots relay authenticates requests via an `X-Flashbots-Signature` header. The signing algorithm is:

```
hashedBody  = keccak256(raw_request_body)          # 32 bytes
messageHash = personal_sign(hex(hashedBody))        # "0x<64 hex chars>" as UTF-8 text
signature   = ecrecover_sign(messageHash, key)
header      = "<address>:0x<signature_hex>"
```

The critical subtlety: Go's `Hash.Hex()` returns the hash with a `0x` prefix, so the message being signed is the 66-character string `"0xabcd..."`, not the 64-character string `"abcd..."`. The `0x` prefix must also be present on the signature in the header.

### Usage

```sh
RELAY_RPC=https://rpc.flashbots.net \
AUCTION_BUNDLER_PRIVATE_KEY=0x<your_key> \
poetry run python scripts/test_relay_signature.py
```

| Env var | Default | Description |
|---|---|---|
| `RELAY_RPC` | `https://rpc.flashbots.net` | Relay endpoint to test against |
| `AUCTION_BUNDLER_PRIVATE_KEY` | — | Private key used to sign the header (not your wallet key) |

### What it does

Sends the same `eth_sendPrivateTransaction` request multiple times, varying the signing approach, JSON body format, signature prefix, and address casing. A `✓` means the relay accepted the signature (status 200 or a non-signature error). A `✗` means `invalid flashbots signature`.

The first block (`THE FIX`) tests the correct implementation. The remaining blocks are for reference — they should all fail.
