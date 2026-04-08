import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

load_dotenv()

def run_test():
    print("🔐 Test auth L2...")
    
    host = "https://clob.polymarket.com"
    key = os.getenv("POLY_PRIVATE_KEY")
    funder = os.getenv("POLY_FUNDER_ADDRESS")  # Polymarket proxy address

    if not key or not funder:
        print("❌ Error: POLY_PRIVATE_KEY or POLY_FUNDER_ADDRESS missing in .env")
        return

    try:
        client = ClobClient(
            host,
            key=key,
            chain_id=POLYGON,
            signature_type=0,   # EOA (MetaMask)
            funder=funder
        )
        
        derived_address = client.get_address()
        print(f"✅ Client initialized!")
        print(f"🔑 Signer (MetaMask): {derived_address}")
        print(f"💼 Funder (Proxy):    {funder}")
        print("✨ Everything looks ready for trading!")

    except Exception as e:
        print(f"❌ Error while testing: {e}")

if __name__ == "__main__":
    run_test()