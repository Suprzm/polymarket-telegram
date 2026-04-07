import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

# Load environment variables from the .env file
load_dotenv()

def generate_polymarket_credentials():
    # Initialize the ClobClient with your private key and Polygon configuration
    # signature_type=1 is required for EOA (Externally Owned Account) authentication
    client = ClobClient(
        host="https://clob.polymarket.com", 
        key=os.getenv("POLY_PRIVATE_KEY"), 
        chain_id=POLYGON,
        signature_type=1
    )

    try:
        print("🚀 Attempting to Onboard and Create API Credentials...")
        
        # This method handles both the L2 onboarding (signing the terms) 
        # and the generation of your API Key, Secret, and Passphrase.
        creds = client.create_or_derive_api_creds()
        
        print("\n✨ SUCCESS! Copy the following lines into your .env file immediately:\n")
        print(f"POLY_API_KEY={creds.api_key}")
        print(f"POLY_API_SECRET={creds.api_secret}")
        print(f"POLY_API_PASSPHRASE={creds.api_passphrase}")
        
        print("\n⚠️  IMPORTANT: The API Secret is only shown ONCE. Store it securely.")
        print("If you lose it, you will have to delete these keys and generate new ones.")

    except Exception as e:
        print(f"❌ Error during generation: {e}")
        print("\nTroubleshooting Tip:")
        print("- Ensure your 'POLY_PRIVATE_KEY' in .env is correct.")
        print("- Make sure your wallet has a tiny amount of POL (ex-MATIC) to be seen as active.")
        print("- Verify your internet connection to the Polymarket CLOB host.")

if __name__ == "__main__":
    generate_polymarket_credentials()