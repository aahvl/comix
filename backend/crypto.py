import hashlib
import hmac
import struct
import asyncio
from concurrent.futures import ThreadPoolExecutor
from mnemonic import Mnemonic
from solders.keypair import Keypair
import bip32utils
 
from backend.security import encrypt, decrypt
 
def generate_mnemonic() -> str:
    mnemo = Mnemonic("english")
    return mnemo.generate(strength=128)

def mnemonic_to_seed(mnemonic: str) -> bytes:
    return Mnemonic.to_seed(mnemonic, passphrase="")

def _derive_ltc_key(seed: bytes) -> bip32utils.BIP32Key:
    root_key = bip32utils.BIP32Key.fromEntropy(seed)
    derived = (
        root_key
        .ChildKey(44 + bip32utils.BIP32_HARDEN) 
        .ChildKey(2 + bip32utils.BIP32_HARDEN)
        .ChildKey(0 + bip32utils.BIP32_HARDEN)
        .ChildKey(0)
        .ChildKey(0)
    )
    return derived

def generate_ltc_wallet(seed: bytes) -> dict:
    key = _derive_ltc_key(seed)
    pub_key_bytes = key.PublicKey()
    

    sha256_hash = hashlib.sha256(pub_key_bytes).digest()
    ripemd160 = hashlib.new("ripemd160")
    ripemd160.update(sha256_hash)
    pub_key_hash = ripemd160.digest()

    versioned = b"\x30" + pub_key_hash
    checksum = hashlib.sha256(hashlib.sha256(versioned).digest()).digest()[:4]
    ltc_address = _base58_encode(versioned + checksum)

    raw_priv = key.PrivateKey()
    wif_versioned = b"\xb0" + raw_priv + b"\x01"
    wif_checksum = hashlib.sha256(hashlib.sha256(wif_versioned).digest()).digest()[:4]
    wif = _base58_encode(wif_versioned + wif_checksum)

    return {
        "address": ltc_address,
        "private_key": encrypt(wif),
    }


def _base58_encode(data: bytes) -> str:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    num = int.from_bytes(data, "big")
    result = ""
    while num > 0:
        num, rem = divmod(num, 58)
        result = alphabet[rem] + result
    for byte in data:
        if byte == 0:
            result = "1" + result
        else:
            break
    return result or "1"

def generate_sol_wallet(seed: bytes) -> dict:
    derived = _slip10_derive(seed, [44 + 0x80000000, 501 + 0x80000000, 0 + 0x80000000, 0, 0])
    keypair = Keypair.from_seed(derived[:32])

    pub_key = str(keypair.pubkey())
    priv_bytes = bytes(keypair)
    priv_b58 = _base58_encode(priv_bytes)

    return {
        "address": pub_key,
        "private_key": encrypt(priv_b58),
    }

def _slip10_derive(seed: bytes, path: list[int]) -> bytes:
    key = b"ed25519 seed"
    data = seed
    I = hmac.new(key, data, hashlib.sha512).digest()
    k_L, k_R = I[:32], I[32:]

    for index in path:
        data = b"\x00" + k_L + struct.pack(">L", index)
        I = hmac.new(k_R, data, hashlib.sha512).digest()
        k_L, k_R = I[:32], I[32:]

    return k_L

def generate_wallet() -> dict:
    mnemonic = generate_mnemonic()
    seed = mnemonic_to_seed(mnemonic)

    ltc = generate_ltc_wallet(seed)
    sol = generate_sol_wallet(seed)

    return {
        "seed_phrase": encrypt(mnemonic),
        "ltc_address": ltc["address"],
        "ltc_private_key": ltc["private_key"],
        "sol_address": sol["address"],
        "sol_private_key": sol["private_key"],
    }
