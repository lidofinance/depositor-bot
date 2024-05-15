def from_hex_string_to_bytes(hex_string):
	if hex_string.startswith('0x'):
		return bytes.fromhex(hex_string[2:])
	return bytes.fromhex(hex_string)
