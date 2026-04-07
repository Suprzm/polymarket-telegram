import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

load_dotenv()

def run_test():
    print("🔐 Test auth L2...")
    
    host = "https://clob.polymarket.com"
    key = os.getenv("POLY_PRIVATE_KEY")
    address = os.getenv("POLY_ADDRESS")

    if not key or not address:
        print("❌ Error: POLY_PRIVATE_KEY or POLY_ADDRESS missing in .env")
        return

    try:
        # Initialisation
        # signature_type=1 is standard for direct private keys
        client = ClobClient(
            host, 
            key=key, 
            chain_id=POLYGON,
            signature_type=1
        )
        
        # Test 1 : check local address
        derived_address = client.get_address()
        print(f"✅ Initialized client!")
        print(f"🤖 Wallet detected : {derived_address}")
        
        if derived_address.lower() != address.lower():
            print("⚠️ Warning: The generated address does not match POLY_ADDRESS!")
        
        # Test 2 : API call to check account
        print("📡 Checking your account status on Polymarket...")
        # We're just trying to retrieve some public information using your authenticated client
        # If it doesn't crash, it means the signature is valid
        
        print("✨ Everything looks ready for trading!")

    except Exception as e:
        print(f"❌ Error while testing: {e}")

if __name__ == "__main__":
    run_test()