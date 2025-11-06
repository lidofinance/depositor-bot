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

        # Check if process started successfully
        time.sleep(1)
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

        # Wait for the port to be accessible
        max_attempts = 10
        for attempt in range(max_attempts):
            if self._is_port_open('localhost', int(self.port)):
                logger.info(
                    {
                        'msg': 'Anvil fork started successfully',
                        'port': self.port,
                        'attempt': attempt + 1,
                    }
                )
                return self.process
            time.sleep(0.5)

        # If we get here, the port never became accessible
        logger.warning(
            {
                'msg': 'Anvil process started but port not accessible',
                'port': self.port,
                'max_attempts': max_attempts,
            }
        )
        return self.process

    def _is_port_open(self, host, port):
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
