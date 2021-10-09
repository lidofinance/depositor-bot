import json
import os
from collections import Counter
from fractions import Fraction
from functools import wraps
from itertools import zip_longest
from pathlib import Path

from brownie import Wei, accounts, chain, interface, web3
from eth_abi.packed import encode_abi_packed
from eth_utils import encode_hex
from tqdm import trange, tqdm
from hexbytes import HexBytes

from joblib import Memory


cachedir = 'deposit_contract_cache'
mem = Memory(cachedir)

deposit_contract_deployment_block = 11052984  
end_block = 11283984
query_step = 1000
unreorgable_distance = 100
dc = interface.DepositContract("0x00000000219ab540356cBB839Cbe05303d7705Fa")


def toDict(dictToParse):
    # convert any 'AttributeDict' type found to 'dict'
    parsedDict = dict(dictToParse)
    for key, val in parsedDict.items():
        # check for nested dict structures to iterate through
        if  'dict' in str(type(val)).lower():
            parsedDict[key] = toDict(val)
        # convert 'HexBytes' type to 'str'
        elif 'HexBytes' in str(type(val)):
            parsedDict[key] = val.hex()
    return parsedDict


def peek_deposit_contract_events(from_block, to_block):
    contract = web3.eth.contract(str(dc), abi=dc.abi)
    logs = contract.events.DepositEvent().getLogs(fromBlock=from_block, toBlock=to_block)
    result = [toDict(log) for log in logs]
    return result   

peek_deposit_contract_historical_events = mem.cache(peek_deposit_contract_events)

def get_deposit_contract_events(deposit_contract_deployment_block, current_block):
    fresh_events = peek_deposit_contract_events(current_block - unreorgable_distance, current_block)
    historical_end = current_block - unreorgable_distance - 1
    historical_events = []
    for start in trange(deposit_contract_deployment_block, historical_end, query_step):
        end = min(start + query_step - 1, historical_end)
        logs = peek_deposit_contract_historical_events(start, end)
        historical_events += logs
    return historical_events + fresh_events

def build_used_pubkeys_map(deposit_events):
    used_pubkeys = set()
    for deposit_event in deposit_events:
        used_pubkeys.add(deposit_event['args']['pubkey'])
    return used_pubkeys

def main():
    deposit_events = get_deposit_contract_events(deposit_contract_deployment_block, end_block)
    used_pubkeys = build_used_pubkeys_map(deposit_events)
    print(used_pubkeys)