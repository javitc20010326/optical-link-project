from __future__ import annotations


def crc16_ccitt(data: bytes, initial: int = 0xFFFF) -> int:
    crc = initial
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def bits_to_bytes(bits: list[int]) -> bytes:
    out = bytearray()
    for start in range(0, len(bits) - 7, 8):
        value = 0
        for bit in bits[start : start + 8]:
            value = (value << 1) | (1 if bit else 0)
        out.append(value)
    return bytes(out)


def bytes_to_bits(data: bytes) -> list[int]:
    bits: list[int] = []
    for value in data:
        for shift in range(7, -1, -1):
            bits.append((value >> shift) & 1)
    return bits
