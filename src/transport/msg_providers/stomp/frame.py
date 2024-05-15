from typing import Optional, Callable

Byte = {'LF': '\x0a', 'NULL': '\x00'}


class Frame:
	ack: Optional[Callable]
	nack: Optional[Callable]

	def __init__(self, command: str, headers: dict, body: Optional[str]):
		self.command = command
		self.headers = headers
		self.body = '' if body is None else body

	def __str__(self):
		lines = [self.command]

		skip_content_length = 'content-length' in self.headers

		for name, value in self.headers.items():
			lines.append(name + ':' + value)

		if self.body and not skip_content_length:
			lines.append(f'content-length:{len(self.body)}')

		lines.append(Byte['LF'] + self.body)
		return Byte['LF'].join(lines)

	@staticmethod
	def unmarshall_single(data):
		if data == '\n':
			return

		lines = data.split(Byte['LF'])

		command = lines[0].strip()
		headers = {}

		# get all headers
		i = 1
		while lines[i] != '':
			# get key, value from raw header
			(key, value) = lines[i].split(':')
			headers[key] = value
			i += 1

		body = None if lines[i + 1] == Byte['NULL'] else lines[i + 1][:-1]

		return Frame(command, headers, body)

	@staticmethod
	def marshall(command, headers, body):
		return str(Frame(command, headers, body)) + Byte['NULL']
