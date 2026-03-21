import os
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from supabase import create_client, Client
from dotenv import load_dotenv

logger = logging.getLogger("supabase")
logger.setLevel(logging.DEBUG)

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

if not url or not key:
    raise EnvironmentError("SUPABASE_URL or SUPABASE_KEY not found in env")

print(f"[SUPABASE] Connecting to: {url}")
try:
    supabase: Client = create_client(url, key)
    print("[SUPABASE] [OK] Client initialized successfully")
except Exception as e:
    print(f"[SUPABASE] [ERROR] Failed to initialize client: {e}")
    raise

_executor = ThreadPoolExecutor(max_workers=4)


async def test_connection() -> bool:
    def _test():
        try:
            result = supabase.table("wallets").select("user_id").limit(1).execute()
            print("[SUPABASE] [OK] Connection test passed")
            return True
        except Exception as e:
            print(f"[SUPABASE] [ERROR] Connection test failed: {e}")
            return False
    
    return await asyncio.get_event_loop().run_in_executor(_executor, _test)


async def get_wallet(user_id: str) -> dict | None:
    def _fetch():
        try:
            result = (
                supabase.table("wallets")
                .select("*")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            return result.data if result.data else None
        except Exception as e:
            print(f"[SUPABASE] [ERROR] get_wallet failed: {e}")
            raise
    
    return await asyncio.get_event_loop().run_in_executor(_executor, _fetch)


async def wallet_exists(user_id: str) -> bool:
    def _check():
        try:
            result = (
                supabase.table("wallets")
                .select("user_id")
                .eq("user_id", user_id)
                .execute()
            )
            return bool(result.data)
        except Exception as e:
            print(f"[SUPABASE] [ERROR] wallet_exists failed: {e}")
            raise
    
    return await asyncio.get_event_loop().run_in_executor(_executor, _check)


async def create_wallet(
    user_id: str,
    username: str,
    pin_hash: str,
    seed_phrase: str,
    ltc_address: str,
    ltc_private_key: str,
    sol_address: str,
    sol_private_key: str,
) -> dict:
    def _insert():
        try:
            print(f"[SUPABASE] Creating wallet for user {user_id}...")
            wallet_data = {
                "user_id": user_id,
                "username": username,
                "pin_hash": pin_hash,
                "seed_phrase": seed_phrase,
                "ltc_address": ltc_address,
                "ltc_private_key": ltc_private_key,
                "sol_address": sol_address,
                "sol_private_key": sol_private_key,
            }
            
            print(f"[SUPABASE] Inserting: {list(wallet_data.keys())}")
            response = supabase.table("wallets").insert(wallet_data).execute()
            
            print(f"[SUPABASE] Response data: {response.data}")
            print(f"[SUPABASE] Response count: {len(response.data) if response.data else 0}")
            
            if response.data and len(response.data) > 0:
                print(f"[SUPABASE] [OK] Wallet created successfully for {user_id}")
                return response.data[0]
            else:
                raise Exception(f"Insert returned no data: {response}")
        except Exception as e:
            print(f"[SUPABASE] [ERROR] create_wallet failed: {str(e)}")
            raise
    
    return await asyncio.get_event_loop().run_in_executor(_executor, _insert)


async def update_last_accessed(user_id: str) -> None:
    def _update():
        try:
            print(f"[SUPABASE] Updating last_accessed for {user_id}...")
            supabase.table("wallets").update(
                {"last_accessed": "now()"}
            ).eq("user_id", user_id).execute()
            print(f"[SUPABASE] [OK] Updated last_accessed")
        except Exception as e:
            print(f"[SUPABASE] [ERROR] update_last_accessed failed: {e}")
            raise
    
    await asyncio.get_event_loop().run_in_executor(_executor, _update)


async def update_currency(user_id: str, currency: str) -> None:
    def _update():
        try:
            print(f"[SUPABASE] Updating currency to {currency} for {user_id}...")
            supabase.table("wallets").update(
                {"currency": currency}
            ).eq("user_id", user_id).execute()
            print(f"[SUPABASE] ✅ Currency updated")
        except Exception as e:
            print(f"[SUPABASE] ❌ update_currency failed: {e}")
            raise

    await asyncio.get_event_loop().run_in_executor(_executor, _update)


async def update_pin(user_id: str, new_pin_hash: str) -> None:
    def _update():
        try:
            print(f"[SUPABASE] Updating PIN for {user_id}...")
            supabase.table("wallets").update(
                {"pin_hash": new_pin_hash}
            ).eq("user_id", user_id).execute()
            print(f"[SUPABASE] ✅ PIN updated")
        except Exception as e:
            print(f"[SUPABASE] ❌ update_pin failed: {e}")
            raise

    await asyncio.get_event_loop().run_in_executor(_executor, _update)


async def delete_wallet(user_id: str) -> None:
    def _delete():
        try:
            print(f"[SUPABASE] Deleting wallet for {user_id}...")
            supabase.table("wallets").delete().eq("user_id", user_id).execute()
            print(f"[SUPABASE] [OK] Wallet deleted")
        except Exception as e:
            print(f"[SUPABASE] [ERROR] delete_wallet failed: {e}")
            raise
    
    await asyncio.get_event_loop().run_in_executor(_executor, _delete)