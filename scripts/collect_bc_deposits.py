import os
import time

#TODO: joblib.load is unsafe, don't use it
import joblib

from brownie import interface, web3

from scripts.depositor_utils.constants import DEPOSIT_CONTRACT, DEPOSIT_CONTRACT_DEPLOY_BLOCK, UNREORGABLE_DISTANCE, EVENT_QUERY_STEP
                        

#TODO read from config instead of constants
cachedir = 'deposit_contract_cache'
mem = joblib.Memory(cachedir)
key_cache_path = os.path.join(cachedir, 'deposit_keys_pickle.dump')


dc = interface.DepositContract(DEPOSIT_CONTRACT[web3.eth.chain_id])


def to_dict(dict_to_parse):
    # convert any 'AttributeDict' type found to 'dict'
    parsed_dict = dict(dict_to_parse)
    for key, val in parsed_dict.items():
        # check for nested dict structures to iterate through
        if 'dict' in str(type(val)).lower():
            parsed_dict[key] = to_dict(val)
        # convert 'HexBytes' type to 'str'
        elif 'HexBytes' in str(type(val)):
            parsed_dict[key] = val.hex()
    return parsed_dict


def peek_deposit_contract_events(from_block, to_block):
    contract = web3.eth.contract(str(dc), abi=dc.abi)
    logs = contract.events.DepositEvent().getLogs(fromBlock=from_block, toBlock=to_block)
    result = [to_dict(log) for log in logs]
    return result   


peek_deposit_contract_historical_events = mem.cache(peek_deposit_contract_events)

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


def collect_historical_pubkeys(from_block, to_block, query_step):

    saved_pubkeys = {'last_block' : 0, 'pubkeys': set()}

    try: 
        saved_pubkeys = joblib.load(key_cache_path)
    except:
        print("No saved pubkey dump")

    collection_start = max(from_block, saved_pubkeys['last_block'] +1)

    historical_events = []
    for start in range(collection_start, to_block, query_step):
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
    used_pubkeys = build_used_pubkeys_map(DEPOSIT_CONTRACT_DEPLOY_BLOCK[web3.eth.chain_id], 
                                web3.eth.block_number, 
                                UNREORGABLE_DISTANCE,
                                EVENT_QUERY_STEP)
    toc = time.perf_counter()
    print(f"Got {len(used_pubkeys)} in {toc - tic:0.4f} seconds")

