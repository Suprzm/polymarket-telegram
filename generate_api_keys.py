import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

load_dotenv()

def generate_polymarket_credentials():
    key = os.getenv("POLY_PRIVATE_KEY")
    funder = os.getenv("POLY_FUNDER_ADDRESS")  # Polymarket proxy address

    if not key or not funder:
        print("❌ Error: POLY_PRIVATE_KEY or POLY_FUNDER_ADDRESS missing in .env")
        return

    client = ClobClient(
        host="https://clob.polymarket.com",
        key=key,
        chain_id=POLYGON,
        signature_type=0,   # EOA (MetaMask)
        funder=funder
    )

    try:
        print("🚀 Attempting to create API credentials...")

        creds = client.create_or_derive_api_creds()

        print("\n✨ SUCCESS! Copy the following lines into your .env file:\n")
        print(f"POLY_API_KEY={creds.api_key}")
        print(f"POLY_API_SECRET={creds.api_secret}")
        print(f"POLY_API_PASSPHRASE={creds.api_passphrase}")

        print("\n⚠️  IMPORTANT: The API Secret is only shown ONCE. Store it securely.")
        print("If you lose it, run this script again to derive the same credentials.")

    except Exception as e:
        print(f"❌ Error during generation: {e}")
        print("\nTroubleshooting:")
        print("- Check POLY_PRIVATE_KEY is correct (starts with 0x)")
        print("- Check POLY_FUNDER_ADDRESS matches your proxy on polymarket.com/profile")
        print("- Make sure your wallet has a tiny amount of POL for gas")

if __name__ == "__main__":
    generate_polymarket_credentials()