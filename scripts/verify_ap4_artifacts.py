#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""FIT/FDT and AArch64 ELF readers for the read-only AP artifact gate."""
from pathlib import Path
import argparse
import hashlib
import json
import lzma
import gzip
import re
import struct
import subprocess
import sys
import time

ROOT_DEFAULT = '/home/xrdev/projects/xr1710g/openwrt'
OUT = Path(__file__).resolve().parent

def sha(data):
    return hashlib.sha256(data).hexdigest()

class FDT:
    def __init__(self, data):
        self.data = data
        header = struct.unpack_from('>10I', data)
        assert header[0] == 0xd00dfeed, 'FDT magic'
        self.total = header[1]
        strings = data[header[3]:header[3] + header[8]]
        cursor, stack = header[2], []
        self.nodes = {}
        while True:
            token = struct.unpack_from('>I', data, cursor)[0]; cursor += 4
            if token == 1:
                end = data.index(b'\0', cursor)
                name = data[cursor:end].decode()
                cursor = (end + 4) & ~3
                stack.append(name)
                self.nodes['/' + '/'.join(stack[1:])] = {}
            elif token == 2:
                stack.pop()
            elif token == 3:
                length, name_offset = struct.unpack_from('>II', data, cursor); cursor += 8
                end = strings.index(b'\0', name_offset)
                name = strings[name_offset:end].decode()
                self.nodes['/' + '/'.join(stack[1:])][name] = data[cursor:cursor + length]
                cursor = (cursor + length + 3) & ~3
            elif token == 4:
                continue
            elif token == 9:
                break
            else:
                raise ValueError('Unexpected FDT token')
    def string(self, node, prop):
        return self.nodes[node][prop].rstrip(b'\0').decode()
    def uint(self, node, prop):
        return int.from_bytes(self.nodes[node][prop], 'big')
    def payload(self, node):
        props = self.nodes[node]
        if 'data' in props:
            value = props['data']
        else:
            size = self.uint(node, 'data-size')
            offset = self.uint(node, 'data-position') if 'data-position' in props else ((self.total + 3) & ~3) + self.uint(node, 'data-offset')
            value = self.data[offset:offset + size]
            assert len(value) == size, 'FIT payload size'
        compression = props.get('compression', b'none\0').rstrip(b'\0')
        if compression == b'none': return value
        if compression == b'lzma': return lzma.decompress(value)
        if compression == b'gzip': return gzip.decompress(value)
        raise ValueError('Unsupported FIT compression: ' + repr(compression))

class ELF64:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        assert self.data[:6] == b'\x7fELF\x02\x01', 'Expected little-endian ELF64'
        assert struct.unpack_from('<H', self.data, 18)[0] == 183, 'Expected AArch64'
        shoff = struct.unpack_from('<Q', self.data, 40)[0]
        shsize, shcount, string_index = struct.unpack_from('<HHH', self.data, 58)
        self.sections = []
        for index in range(shcount):
            values = struct.unpack_from('<IIQQQQIIQQ', self.data, shoff + index * shsize)
            self.sections.append(dict(zip(['name_offset', 'type', 'flags', 'addr', 'offset', 'size', 'link', 'info', 'align', 'entry_size'], values)))
        shstrings = self.section_bytes(string_index)
        for section in self.sections:
            offset = section['name_offset']; end = shstrings.index(b'\0', offset)
            section['name'] = shstrings[offset:end].decode()
        self.symbols = {}
        for section in self.sections:
            if section['type'] != 2: continue
            strings = self.section_bytes(section['link'])
            for offset in range(section['offset'], section['offset'] + section['size'], section['entry_size']):
                name_off, info, other, shndx, value, size = struct.unpack_from('<IBBHQQ', self.data, offset)
                if name_off == 0: continue
                name = strings[name_off:strings.index(b'\0', name_off)].decode()
                self.symbols[name] = {'section': shndx, 'value': value, 'size': size, 'type': info & 15}
    def section_bytes(self, index):
        section = self.sections[index]
        if section['type'] == 8: return b'\0' * section['size']
        return self.data[section['offset']:section['offset'] + section['size']]
    def symbol_bytes(self, name):
        symbol = self.symbols[name]; section = self.sections[symbol['section']]
        offset = symbol['value'] - section['addr']
        return self.section_bytes(symbol['section'])[offset:offset + symbol['size']]
    def function_normalized(self, name):
        symbol = self.symbols[name]
        value = bytearray(self.symbol_bytes(name))
        for section in self.sections:
            if section['type'] != 4 or section['info'] != symbol['section']: continue
            for offset in range(section['offset'], section['offset'] + section['size'], section['entry_size']):
                target, info, addend = struct.unpack_from('<QQq', self.data, offset)
                rel_type = info & 0xffffffff
                width = 8 if rel_type in (257, 260) else 4
                relative = target - symbol['value']
                if 0 <= relative < len(value): value[relative:relative + width] = b'\0' * width
        return bytes(value)

def extract_function(text, signature):
    start = text.index(signature); opening = text.index('{', start); depth = 0
    for index in range(opening, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if not depth: return text[start:index + 1]
    raise ValueError('Unterminated source function')
