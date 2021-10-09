import json
import time
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

#TODO - dump is unsafe! rewrite to safe storage later
import joblib


cachedir = 'deposit_contract_cache'
mem = Memory(cachedir)
key_cache_path = os.path.join(cachedir, 'deposit_keys_pickle.dump')



deposit_contract_deployment_block = 11052984  
end_block = web3.eth.block_number
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

def collect_deposit_contract_historical_events(deposit_contract_deployment_block, current_block):
    fresh_events = peek_deposit_contract_events(current_block - unreorgable_distance, current_block)
    historical_end = current_block - unreorgable_distance - 1
    historical_events = []
    for start in trange(deposit_contract_deployment_block, historical_end, query_step):
        end = min(start + query_step - 1, historical_end)
        logs = peek_deposit_contract_historical_events(start, end)
        historical_events += logs
    return historical_events + fresh_events

def deposit_events_to_pubkeys(deposit_events):
    used_pubkeys = set()
    for deposit_event in deposit_events:
        used_pubkeys.add(deposit_event['args']['pubkey'])
    return used_pubkeys

def collect_fresh_pubkeys(from_block, to_block):
    fresh_events = peek_deposit_contract_events(from_block, to_block)
    return deposit_events_to_pubkeys(fresh_events)

def collect_cached_pubkeys(from_block, to_block):
    fresh_events = peek_deposit_contract_historical_events(from_block, to_block)
    return deposit_events_to_pubkeys(fresh_events)

#chp (1500) = chp(1000) + cfp(500)
#chp (1,4) = сhp(1,2) + cfp(3,4) 

def collect_historical_pubkeys(from_block, to_block, query_step):

    saved_pubkeys = {'last_block' : 0, 'pubkeys': set()}

    try: 
        saved_pubkeys = joblib.load(key_cache_path)
    except:
        print("No saved pubkey dump")

    collection_start = max(from_block, saved_pubkeys['last_block'] +1)

    historical_events = []
    for start in trange(collection_start, to_block, query_step):
        end = min(start + query_step - 1, to_block)
        collected_pubkeys = collect_cached_pubkeys(start, end)
        saved_pubkeys['pubkeys'] = saved_pubkeys['pubkeys'].union(collected_pubkeys)
        saved_pubkeys['last_block'] = end

    joblib.dump(saved_pubkeys, key_cache_path)

    return saved_pubkeys['pubkeys']




def build_used_pubkeys_map(from_block, to_block, unreorgable_distance, query_step):
    length = to_block - from_block + 1
    unreorgable_length = length - unreorgable_distance
    historical_length = unreorgable_length - unreorgable_length % unreorgable_distance
    historical_period_end = from_block + historical_length - 1

    historical_pubkeys = collect_historical_pubkeys(from_block, to_block, query_step)

    fresh_pubkeys = collect_fresh_pubkeys(historical_period_end + 1, to_block)

    return historical_pubkeys.union(fresh_pubkeys)


def main():
    tic = time.perf_counter()
    used_pubkeys = build_used_pubkeys_map(deposit_contract_deployment_block, 
                                end_block, 
                                unreorgable_distance,
                                query_step)
    toc = time.perf_counter()
    print(f"Got {len(used_pubkeys)} in {toc - tic:0.4f} seconds")