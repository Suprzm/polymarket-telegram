import requests
import json

# Configuration
GAMMA_API = "https://gamma-api.polymarket.com"

def parse_json_field(field):
    """
    Fonction utilitaire pour transformer une string JSON en liste Python,
    ou retourner la liste si elle est déjà au bon format.
    """
    if isinstance(field, str):
        try:
            return json.loads(field)
        except (json.JSONDecodeError, TypeError):
            return []
    return field if isinstance(field, list) else []

def get_tokens_from_market(market):
    """
    Extrait proprement les noms d'outcomes (Yes/No) et les Token IDs.
    Règle le problème d'affichage des caractères '[' ou '"'.
    """
    # Extraction et parsing sécurisé des deux champs clés
    tokens = parse_json_field(market.get('clobTokenIds', []))
    outcomes = parse_json_field(market.get('outcomes', []))
    
    results = []
    if tokens:
        for i, token_id in enumerate(tokens):
            # Récupère le nom (ex: "Yes"), sinon utilise l'index
            name = outcomes[i] if i < len(outcomes) else f"Outcome {i}"
            results.append({"outcome": name, "id": token_id})
    return results

def search_polymarket(query, limit=5):
    """
    Recherche globale via l'endpoint /events (idéal pour trouver 'Trump', 'Bitcoin', etc.)
    """
    url = f"{GAMMA_API}/events"
    params = {
        "q": query,
        "active": "true",
        "closed": "false",
        "limit": limit
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        events = response.json()
        
        if not events:
            print(f"❌ Aucun résultat trouvé pour : '{query}'")
            return

        print(f"\n{'='*80}")
        print(f"🔍 RÉSULTATS DE RECHERCHE : {query.upper()}")
        print(f"{'='*80}")

        for event in events:
            print(f"\n📅 ÉVÉNEMENT : {event.get('title')}")
            print(f"🔗 URL: https://polymarket.com/event/{event.get('slug')}")
            
            markets = event.get('markets', [])
            for m in markets:
                print(f"   📊 Marché : {m.get('question')}")
                tokens = get_tokens_from_market(m)
                
                if tokens:
                    for t in tokens:
                        print(f"       • {t['outcome']}: {t['id']}")
                else:
                    print("       ⚠️ Aucun Token ID disponible.")
                    
    except Exception as e:
        print(f"❌ Erreur lors de la recherche : {e}")

def get_market_by_slug(slug):
    """
    Récupère les détails d'un marché spécifique par son slug.
    """
    url = f"{GAMMA_API}/markets"
    params = {"slug": slug}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        markets = response.json()
        
        if not markets:
            print(f"❌ Aucun marché trouvé pour le slug : '{slug}'")
            return
            
        market = markets[0]
        print(f"\n🎯 MARCHÉ TROUVÉ : {market.get('question')}")
        print(f"{'-'*40}")
        
        tokens = get_tokens_from_market(market)
        for t in tokens:
            print(f"   • {t['outcome']} : {t['id']}")
            
    except Exception as e:
        print(f"❌ Erreur : {e}")

def interactive_mode():
    """Interface utilisateur simplifiée."""
    print("\n" + "!"*40)
    print("  POLYMARKET TOKEN ID FINDER v2.0")
    print("!"*40)
    
    while True:
        print("\nOPTIONS :")
        print("1. Rechercher par mot-clé (ex: Trump, Elon, Fed)")
        print("2. Chercher par Slug précis")
        print("3. Quitter")
        
        choice = input("\nVotre choix (1-3) : ").strip()
        
        if choice == "1":
            q = input("Entrez votre recherche : ").strip()
            search_polymarket(q)
        elif choice == "2":
            s = input("Entrez le slug (ex: will-trump-release-the-epstein-files...) : ").strip()
            get_market_by_slug(s)
        elif choice == "3":
            print("👋 Fin du programme.")
            break
        else:
            print("❌ Option invalide, réessayez.")

if __name__ == "__main__":
    interactive_mode()