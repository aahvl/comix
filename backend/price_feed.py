import aiohttp
import asyncio
import time
import logging

logger = logging.getLogger("price_feed")

_COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=solana,litecoin"
    "&vs_currencies=usd,gbp,eur"
)

_cache: dict = {}
_cache_time: float = 0.0
_CACHE_TTL = 60 

async def get_prices() -> dict:
    """
    Fetch current SOL and LTC prices in USD, GBP, EUR.
    Returns cached result if within TTL.

    Return shape:
        {
            "sol": {"usd": 150.00, "gbp": 120.00, "eur": 140.00},
            "ltc": {"usd": 80.00,  "gbp": 64.00,  "eur": 75.00},
            "updated_at": 1712345678.0
        }
    """
    global _cache, _cache_time

    now = time.time()
    if _cache and (now - _cache_time) < _CACHE_TTL:
        return _cache

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(_COINGECKO_URL, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    logger.warning(f"[PRICE] CoinGecko returned {resp.status}")
                    return _cache or _fallback()
                data = await resp.json()

        _cache = {
            "sol": {
                "usd": data["solana"]["usd"],
                "gbp": data["solana"]["gbp"],
                "eur": data["solana"]["eur"],
            },
            "ltc": {
                "usd": data["litecoin"]["usd"],
                "gbp": data["litecoin"]["gbp"],
                "eur": data["litecoin"]["eur"],
            },
            "updated_at": time.time(),
        }
        _cache_time = time.time()
        logger.info(f"[PRICE] Updated - SOL ${_cache['sol']['usd']} | LTC ${_cache['ltc']['usd']}")
        return _cache

    except Exception as e:
        logger.error(f"[PRICE] Failed to fetch prices: {e}")
        return _cache or _fallback()


def _fallback() -> dict:
    """Return zeroed prices if API is completely unreachable."""
    return {
        "sol": {"usd": 0.0, "gbp": 0.0, "eur": 0.0},
        "ltc": {"usd": 0.0, "gbp": 0.0, "eur": 0.0},
        "updated_at": time.time(),
    }


def format_price(amount: float, currency: str) -> str:
    """Format a fiat value with the correct currency symbol."""
    symbols = {"usd": "$", "gbp": "£", "eur": "€"}
    symbol = symbols.get(currency.lower(), "$")
    return f"{symbol}{amount:,.2f}"


async def get_sol_balance(address: str) -> float:
    """
    Fetch SOL balance for a given public key using the Solana mainnet RPC.
    Returns balance in SOL (not lamports).
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [address]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.mainnet-beta.solana.com",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                data = await resp.json()
                lamports = data.get("result", {}).get("value", 0)
                return lamports / 1_000_000_000
    except Exception as e:
        logger.error(f"[BALANCE] SOL fetch failed for {address}: {e}")
        return 0.0


async def get_ltc_balance(address: str) -> float:
    """
    Fetch LTC balance using the free Blockcypher API (no key needed).
    Returns balance in LTC.
    """
    url = f"https://api.blockcypher.com/v1/ltc/main/addrs/{address}/balance"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    logger.warning(f"[BALANCE] Blockcypher returned {resp.status} for {address}")
                    return 0.0
                data = await resp.json()
                satoshis = data.get("final_balance", 0)
                return satoshis / 100_000_000
    except Exception as e:
        logger.error(f"[BALANCE] LTC fetch failed for {address}: {e}")
        return 0.0