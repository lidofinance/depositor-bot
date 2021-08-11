import time
import warnings

from brownie import accounts, chain, interface, web3
from brownie.network.contract import BrownieEnvironmentWarning
from click import secho, prompt, Choice


warnings.filterwarnings('ignore', category=BrownieEnvironmentWarning)


MIN_BUFFERED_ETHER = 32*8*10**18
MAX_GAS_PRICE = 100 * 10**9


def get_account():
    return accounts.load(prompt('account', type=Choice(accounts.load())))


def get_lido(user=None):
    return interface.Lido('0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84', owner=user)


def main():
    user = get_account()
    lido = get_lido(user)

    for block in chain.new_blocks():
        secho(f'>>> {block.number}', dim=True)

        gas_price = web3.eth.generate_gas_price()
        secho(f'Gas price: {gas_price/10**9} gwei')
        if gas_price > MAX_GAS_PRICE:
            continue

        is_stopped = lido.isStopped()
        secho(f'Lido is stopped: {is_stopped}')
        if lido.isStopped():
            continue

        buffered_ether = lido.getBufferedEther() / 10**18
        secho(f'Lido\'s buffered ether: {buffered_ether}')
        if lido.getBufferedEther() < MIN_BUFFERED_ETHER:
            continue

        try: 
            tx = lido.depositBufferedEther(150, {
                'gas_price': gas_price,
                'from': user,
                'gas_limit': 10000000,
            })

            secho(str(tx))
        except Exception as e:
            secho(str(e))
        
        time.sleep(120)
