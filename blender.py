import bpy
import requests
import json

# ========== KONFIGURACJA ==========
COMPUTE_URL = "http://localhost:8081"
GH_FILE = r"C:\gh_definitions\cylinder.gh"  # ZMIEŃ NA SWOJĄ ŚCIEŻKĘ!

# Parametry
params = {
    "radius": 3.0,
    "height": 8.0
}

# ========== FUNKCJA TESTOWA ==========
def test_grasshopper_connection():
    """Prosty test połączenia"""
    
    print("=" * 50)
    print("TEST POŁĄCZENIA Z GRASSHOPPER")
    print("=" * 50)
    
    # 1. Sprawdź czy Compute działa
    try:
        response = requests.get(f"{COMPUTE_URL}/healthcheck", timeout=5)
        print("✓ Rhino.Compute działa:", response.text)
    except Exception as e:
        print("✗ BŁĄD: Nie można połączyć z Rhino.Compute")
        print(f"  Upewnij się że rhino.compute.exe działa!")
        return False
    
    # 2. Sprawdź czy plik GH istnieje
    import os
    if not os.path.exists(GH_FILE):
        print(f"✗ BŁĄD: Nie znaleziono pliku: {GH_FILE}")
        return False
    print(f"✓ Plik GH znaleziony: {GH_FILE}")
    
    # 3. Wyślij definicję do Compute
    try:
        with open(GH_FILE, 'rb') as f:
            gh_bytes = f.read()
        
        # Przygotuj request w formacie base64
        import base64
        gh_base64 = base64.b64encode(gh_bytes).decode('utf-8')
        
        # Przygotuj inputy
        inputs = {
            "radius": params["radius"],
            "height": params["height"]
        }
        
        # Wyślij do Compute
        url = f"{COMPUTE_URL}/grasshopper"
        payload = {
            "algo": gh_base64,
            "pointer": None,
            "values": [
                {
                    "ParamName": "RH_IN:radius",
                    "InnerTree": {
                        "0": [{"type": "System.Double", "data": params["radius"]}]
                    }
                },
                {
                    "ParamName": "RH_IN:height", 
                    "InnerTree": {
                        "0": [{"type": "System.Double", "data": params["height"]}]
                    }
                }
            ]
        }
        
        print("⏳ Wysyłam definicję do Rhino.Compute...")
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            print("✓ Otrzymano odpowiedź z Grasshoppera!")
            result = response.json()
            
            # Sprawdź czy są outputy
            if 'values' in result and len(result['values']) > 0:
                print(f"✓ Otrzymano {len(result['values'])} outputów")
                return result
            else:
                print("⚠ Uwaga: Brak outputów w odpowiedzi")
                return None
        else:
            print(f"✗ BŁĄD: {response.status_code}")
            print(response.text)
            return None
            
    except Exception as e:
        print(f"✗ BŁĄD podczas wykonywania: {e}")
        import traceback
        traceback.print_exc()
        return None

# ========== URUCHOM TEST ==========
result = test_grasshopper_connection()

if result:
    print("\n" + "=" * 50)
    print("🎉 SUKCES! Połączenie działa!")
    print("Teraz możesz użyć pełnego skryptu do importu geometrii")
    print("=" * 50)