"""Bounded 32-bit codec layouts; candidates must match this profile's DB salt.

Reference: SQLCipher v4.5.4 src/crypto.h codec_ctx (17 integer fields),
current src/sqlcipher.c codec_ctx (15 integer fields), and nichirin's measured
16-field prefix. The four pointer fields before read_ctx keep the same order.
This reads no passwords or login/session tokens and writes no process memory.
"""
import struct
from kanao.process import CodecContext


def resolve32(address,blob,read_memory,salts):
    if len(blob)<88:
        return None
    if (struct.unpack_from('<I',blob,4)[0]!=256000 or
        struct.unpack_from('<I',blob,16)[0]!=32 or
        struct.unpack_from('<I',blob,28)[0]!=4096 or
        not any(struct.unpack_from('<I',blob,offset)[0]==80 for offset in (32,36))):
        return None
    for salt_offset in (60,64,68):
        salt_pointer=struct.unpack_from('<I',blob,salt_offset)[0]
        if not salt_pointer:
            continue
        salt=read_memory(salt_pointer,16)
        if salt not in salts:
            continue
        context_pointer=struct.unpack_from('<I',blob,salt_offset+16)[0]
        if not context_pointer:
            continue
        key_pointer_bytes=read_memory(context_pointer+8,4)
        if key_pointer_bytes is None or len(key_pointer_bytes)!=4:
            continue
        key_pointer=struct.unpack('<I',key_pointer_bytes)[0]
        if not key_pointer:
            continue
        key=read_memory(key_pointer,32)
        if key is not None and len(key)==32:
            return CodecContext(address=address,salt=salt,key=key)
    return None
