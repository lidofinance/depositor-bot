import asyncio
import json

import aiofiles
import aiohttp

sync_config = {
    'branch': 'feature/shapella-upgrade',
    'repo': 'lidofinance/lido-dao',
    'syncMap': [
        {
            'local': 'interfaces/Lido.json',
            'remote': 'lib/abi/Lido.json',
        },
        {
            'local': 'interfaces/NodeOperatorRegistry.json',
            'remote': 'lib/abi/NodeOperatorsRegistry.json',
        },
        {
            'local': 'interfaces/DepositSecurityModule.json',
            'remote': 'lib/abi/DepositSecurityModule.json'
        }
    ],
}


async def get_file_from_github(repo, branch, file_path):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'https://raw.githubusercontent.com/{repo}/{branch}/{file_path}') as response:
            file_content = await response.text()
            return json.loads(file_content)


async def run():
    branch = sync_config['branch']
    repo = sync_config['repo']
    sync_map = sync_config['syncMap']
    for file in sync_map:
        local_path = file['local']
        remote_path = file['remote']
        file_content = await get_file_from_github(repo, branch, remote_path)
        async with aiofiles.open(local_path, 'w') as f:
            await f.write(json.dumps(file_content, indent=2))


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
