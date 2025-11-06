import json
import logging
import socket
import subprocess
import time

logger = logging.getLogger(__name__)


class anvil_fork:
    """
    --dump-state
    --load-state

    --state
    """

    def __init__(self, path_to_anvil, fork_url, block_number=None, port='8545'):
        self.path_to_anvil = path_to_anvil
        self.fork_url = fork_url
        self.port = port
        self.block_number = block_number

    def __enter__(self):
        # Validate fork URL
        if not self.fork_url or not self.fork_url.startswith(('http://', 'https://', 'ws://', 'wss://')):
            error_msg = (
                'Invalid fork URL. '
                'Please set WEB3_RPC_ENDPOINTS environment variable with a valid RPC endpoint. '
                'Example: export WEB3_RPC_ENDPOINTS=https://eth.llamarpc.com'
            )
            logger.error({'msg': error_msg})
            raise ValueError(error_msg)

        block_command = tuple()
        if self.block_number is not None:
            block_command = ('--fork-block-number', str(self.block_number))

        anvil_command = [
            f'{self.path_to_anvil}anvil',
            '-f',
            self.fork_url,
            '-p',
            self.port,
            *block_command,
            '--block-time',
            '12',
            '--auto-impersonate',
        ]

        logger.info(
            {
                'msg': 'Starting Anvil fork process',
                'port': self.port,
                'block_number': self.block_number,
            }
        )

        try:
            self.process = subprocess.Popen(
                anvil_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as error:
            logger.error(
                {
                    'msg': 'Failed to start Anvil process',
                    'error': str(error),
                    'command': ' '.join(anvil_command),
                }
            )
            raise

        # Check if process started successfully (initial wait)
        time.sleep(2)
        poll_result = self.process.poll()
        if poll_result is not None:
            stdout, stderr = self.process.communicate()
            logger.error(
                {
                    'msg': 'Anvil process exited immediately',
                    'exit_code': poll_result,
                    'stdout': stdout,
                    'stderr': stderr,
                }
            )
            raise RuntimeError(f'Anvil failed to start. Exit code: {poll_result}. Error: {stderr}')

        # Wait for the port to be accessible and Anvil to respond to RPC calls
        max_attempts = 30  # Increased from 10
        base_sleep = 0.5

        for attempt in range(max_attempts):
            # Check if process is still alive
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate(timeout=1)
                logger.error(
                    {
                        'msg': 'Anvil process died during startup',
                        'stdout': stdout[:500] if stdout else '',
                        'stderr': stderr[:500] if stderr else '',
                    }
                )
                raise RuntimeError('Anvil process died during startup')

            # Check if port is open
            if self._is_port_open('localhost', int(self.port)):
                # Port is open, now verify Anvil is responding to RPC calls
                if self._check_rpc_health():
                    logger.info(
                        {
                            'msg': 'Anvil fork started successfully',
                            'port': self.port,
                            'attempt': attempt + 1,
                            'time_taken': f'{(attempt + 1) * base_sleep:.1f}s',
                        }
                    )
                    return self.process
                else:
                    logger.debug({'msg': 'Port open but RPC not responding yet', 'attempt': attempt + 1})

            # Exponential backoff with max cap
            sleep_time = min(base_sleep * (1.2**attempt), 3.0)
            time.sleep(sleep_time)

        # If we get here, Anvil failed to become ready
        # Clean up the process
        self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()

        logger.error(
            {
                'msg': 'Anvil failed to become ready after maximum attempts',
                'port': self.port,
                'max_attempts': max_attempts,
                'timeout': f'{max_attempts * base_sleep}s',
            }
        )
        raise RuntimeError(
            f'Anvil failed to become ready on port {self.port} after {max_attempts} attempts. '
            'The port may be in use or Anvil is not responding to RPC calls.'
        )

    def _is_port_open(self, host: str, port: int) -> bool:
        """Check if a port is open and accessible"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                return result == 0
        except Exception as error:
            logger.debug(
                {
                    'msg': 'Error checking port',
                    'host': host,
                    'port': port,
                    'error': str(error),
                }
            )
            return False

    def _check_rpc_health(self) -> bool:
        """
        Verify that Anvil is responding to RPC calls.
        Sends a simple eth_blockNumber request to verify it's working.
        """
        import urllib.error
        import urllib.request

        url = f'http://localhost:{self.port}'

        # Prepare JSON-RPC request
        data = json.dumps({'jsonrpc': '2.0', 'method': 'eth_blockNumber', 'params': [], 'id': 1}).encode('utf-8')

        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json'},
            )

            with urllib.request.urlopen(req, timeout=2) as response:
                result = json.loads(response.read().decode('utf-8'))

                # Check if we got a valid response
                if 'result' in result:
                    logger.debug(
                        {
                            'msg': 'RPC health check passed',
                            'block_number': result['result'],
                        }
                    )
                    return True
                else:
                    logger.debug(
                        {
                            'msg': 'RPC health check failed - no result in response',
                            'response': result,
                        }
                    )
                    return False

        except urllib.error.URLError as e:
            logger.debug(
                {
                    'msg': 'RPC health check failed - connection error',
                    'error': str(e),
                }
            )
            return False
        except socket.timeout:
            logger.debug({'msg': 'RPC health check failed - timeout'})
            return False
        except Exception as e:
            logger.debug(
                {
                    'msg': 'RPC health check failed - unexpected error',
                    'error': str(e),
                    'error_type': type(e).__name__,
                }
            )
            return False

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'process') and self.process:
            logger.info(
                {
                    'msg': 'Terminating Anvil fork process',
                    'port': self.port,
                }
            )
            self.process.terminate()

            # Wait for process to terminate
            try:
                self.process.wait(timeout=5)
                logger.info({'msg': 'Anvil process terminated successfully'})
            except subprocess.TimeoutExpired:
                logger.warning({'msg': 'Anvil process did not terminate gracefully, killing it'})
                self.process.kill()
                self.process.wait()
                logger.info({'msg': 'Anvil process killed'})
