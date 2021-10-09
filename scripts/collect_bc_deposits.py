from brownie import interface, web3
from tqdm import trange

from joblib import Memory

from scripts.depositor_utils.constants import DEPOSIT_CONTRACT

cachedir = 'deposit_contract_cache'
mem = Memory(cachedir)

deposit_contract_deployment_block = 11052984  
end_block = 11283984
query_step = 1000
unreorgable_distance = 100
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
