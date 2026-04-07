import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

load_dotenv()

def generate_everything():
    client = ClobClient(
        host="https://clob.polymarket.com", 
        key=os.getenv("POLY_PRIVATE_KEY"), 
        chain_id=POLYGON,
        signature_type=1
    )

    try:
        print("🚀 Tentative de création/dérivation des credentials...")
        
        # C'est la fonction que ton scan a trouvée !
        creds = client.create_or_derive_api_creds()
        
        print("\n✨ ENFIN ! Voici tes accès pour le .env :\n")
        print(f"POLY_API_KEY={creds.api_key}")
        print(f"POLY_API_SECRET={creds.api_secret}")
        print(f"POLY_API_PASSPHRASE={creds.api_passphrase}")
        print("\n⚠️ Copie-les vite, le secret ne sera plus jamais affiché !")

    except Exception as e:
        print(f"❌ Erreur persistante : {e}")
        print("\n💡 Si ça bloque encore avec une erreur 400, c'est le signal ultime :")
        print("Polymarket refuse la création sur un compte à 0.00$.")
        print("Envoie 0.5 POL (ex-MATIC) sur ton adresse et relance.")

if __name__ == "__main__":
    generate_everything()