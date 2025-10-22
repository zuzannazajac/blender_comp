import bpy
import requests
import json
import base64
import os

# ========== KONFIGURACJA ==========
HOPS_URL = "http://localhost:6500"
GH_FILE = r"C:\gh_definitions\cylinder.gh"  # ZMIEŃ NA SWOJĄ ŚCIEŻKĘ!

params = {
    "radius": 5.0,
    "height": 10.0
}

# ========== TEST POŁĄCZENIA ==========
def test_hops():
    """Test czy Hops działa"""
    try:
        response = requests.get(f"{HOPS_URL}/healthcheck", timeout=5)
        if response.status_code == 200:
            print("✓ Hops działa!")
            return True
        else:
            print("✗ Hops nie odpowiada poprawnie")
            return False
    except:
        print("✗ BŁĄD: Nie można połączyć z Hops")
        print("  Upewnij się że Rhino i Grasshopper są uruchomione!")
        print("  Hops automatycznie startuje z Grasshopperem")
        return False

# ========== WYWOŁANIE GRASSHOPPER - KROK 1: /io ==========
def upload_definition():
    """Krok 1: Wyślij definicję do /io i otrzymaj pointer"""
    
    if not os.path.exists(GH_FILE):
        print(f"✗ Nie znaleziono pliku: {GH_FILE}")
        return None
    
    # Wczytaj plik .gh jako base64
    with open(GH_FILE, 'rb') as f:
        gh_bytes = f.read()
    gh_base64 = base64.b64encode(gh_bytes).decode('utf-8')
    
    # Request do /io
    url = f"{HOPS_URL}/io"
    payload = {
        "absolutetolerance": 0.01,
        "angletolerance": 1.0,
        "algo": gh_base64,
        "pointer": None,
        "values": []  # Puste - jeszcze nie wysyłamy wartości
    }
    
    try:
        print("⏳ Wysyłam definicję do /io...")
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            pointer = result.get('pointer')
            print(f"✓ Otrzymano pointer: {pointer}")
            
            # Wyświetl informacje o inputach/outputach
            if 'values' in result:
                print(f"  Znaleziono {len(result['values'])} parametrów:")
                for param in result['values']:
                    name = param.get('ParamName', 'Unknown')
                    print(f"    - {name}")
            
            return pointer
        else:
            print(f"✗ Błąd {response.status_code}: {response.text}")
            return None
            
    except Exception as e:
        print(f"✗ Błąd podczas /io: {e}")
        return None

# ========== WYWOŁANIE GRASSHOPPER - KROK 2: /solve ==========
def solve_definition(pointer):
    """Krok 2: Wyślij parametry do /solve używając pointera"""
    
    # Przygotuj wartości w formacie DataTree
    values = []
    
    for param_name, value in params.items():
        values.append({
            "ParamName": param_name,
            "InnerTree": {
                "0": [{
                    "type": "System.Double",
                    "data": str(value)
                }]
            }
        })
    
    # Request do /solve
    url = f"{HOPS_URL}/solve"
    payload = {
        "absolutetolerance": 0.01,
        "angletolerance": 1.0,
        "algo": None,  # Nie wysyłamy ponownie - używamy pointera
        "pointer": pointer,
        "values": values,
        "cachesolve": False
    }
    
    try:
        print(f"⏳ Rozwiązuję z parametrami: {params}")
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print("✓ Otrzymano wynik!")
            
            # Sprawdź błędy
            if result.get('errors'):
                print("⚠ UWAGA - Błędy w definicji:")
                for error in result['errors']:
                    print(f"  - {error}")
            
            # Sprawdź ostrzeżenia
            if result.get('warnings'):
                print("⚠ Ostrzeżenia:")
                for warning in result['warnings']:
                    print(f"  - {warning}")
            
            return result
        else:
            print(f"✗ Błąd {response.status_code}: {response.text}")
            return None
            
    except Exception as e:
        print(f"✗ Błąd podczas /solve: {e}")
        return None

# ========== IMPORT DO BLENDERA ==========
def import_to_blender(result):
    """Konwertuj wynik z Hops na Blender mesh"""
    
    if not result or 'values' not in result:
        print("✗ Brak danych do importu")
        return
    
    try:
        import rhino3dm as rh
    except ImportError:
        print("✗ BŁĄD: Brak modułu rhino3dm")
        print("Zainstaluj: pip install rhino3dm")
        return
    
    # Wyczyść scenę
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    print("✓ Wyczyszczono scenę")
    
    # Przetworz outputy
    count = 0
    for output in result['values']:
        param_name = output.get('ParamName', 'Unknown')
        print(f"  Przetwarzam: {param_name}")
        
        if 'InnerTree' not in output:
            continue
            
        for branch_path, items in output['InnerTree'].items():
            for item in items:
                if 'data' not in item:
                    continue
                
                try:
                    # Dekoduj geometrię z base64
                    geom_data = base64.b64decode(item['data'])
                    
                    # Użyj rhino3dm do parsowania
                    geom = rh.CommonObject.Decode(geom_data)
                    
                    if geom is None:
                        print(f"    ⚠ Nie udało się zdekodować obiektu")
                        continue
                    
                    # Konwersja mesh
                    if isinstance(geom, rh.Mesh):
                        verts = [(v.X, v.Y, v.Z) for v in geom.Vertices]
                        faces = []
                        
                        for face in geom.Faces:
                            if face.IsQuad:
                                faces.append([face.A, face.B, face.C, face.D])
                            else:
                                faces.append([face.A, face.B, face.C])
                        
                        # Stwórz Blender mesh
                        mesh = bpy.data.meshes.new(f"GH_{param_name}_{count}")
                        mesh.from_pydata(verts, [], faces)
                        mesh.update()
                        
                        # Dodaj do sceny
                        obj = bpy.data.objects.new(f"GH_{param_name}_{count}", mesh)
                        bpy.context.collection.objects.link(obj)
                        
                        print(f"    ✓ Mesh: {len(verts)} wierzchołków, {len(faces)} ścian")
                        count += 1
                    
                    elif isinstance(geom, rh.Brep):
                        # Konwertuj Brep na mesh
                        print(f"    → Konwertuję Brep na mesh...")
                        mesh = rh.Mesh()
                        for face in geom.Faces:
                            face_mesh = face.GetMesh(rh.MeshType.Default)
                            if face_mesh:
                                mesh.Append(face_mesh)
                        
                        if mesh.Vertices.Count > 0:
                            verts = [(v.X, v.Y, v.Z) for v in mesh.Vertices]
                            faces = []
                            
                            for face in mesh.Faces:
                                if face.IsQuad:
                                    faces.append([face.A, face.B, face.C, face.D])
                                else:
                                    faces.append([face.A, face.B, face.C])
                            
                            bl_mesh = bpy.data.meshes.new(f"GH_{param_name}_{count}")
                            bl_mesh.from_pydata(verts, [], faces)
                            bl_mesh.update()
                            
                            obj = bpy.data.objects.new(f"GH_{param_name}_{count}", bl_mesh)
                            bpy.context.collection.objects.link(obj)
                            
                            print(f"    ✓ Brep→Mesh: {len(verts)} wierzchołków")
                            count += 1
                    
                    else:
                        print(f"    ⚠ Nieobsługiwany typ: {type(geom)}")
                        
                except Exception as e:
                    print(f"    ⚠ Błąd importu: {e}")
                    continue
    
    if count == 0:
        print("⚠ Nie zaimportowano żadnych obiektów")
    else:
        print(f"🎉 Import zakończony! Zaimportowano {count} obiektów")

# ========== GŁÓWNA FUNKCJA ==========
def run():
    """Główna funkcja - pełny workflow"""
    
    print("=" * 60)
    print("GRASSHOPPER → BLENDER przez Hops")
    print("=" * 60)
    
    # 1. Test połączenia
    if not test_hops():
        return
    
    # 2. Wyślij definicję i otrzymaj pointer
    pointer = upload_definition()
    if not pointer:
        return
    
    # 3. Rozwiąż z parametrami
    result = solve_definition(pointer)
    
    # 4. Importuj do Blendera
    if result:
        import_to_blender(result)
    else:
        print("✗ Brak wyniku do zaimportowania")

# ========== URUCHOM ==========
run()

# ========== REAL-TIME LOOP (opcjonalnie) ==========
def real_time_loop(interval=2.0):
    """Ciągłe odświeżanie co X sekund"""
    import time
    
    print("\n🔄 Uruchomiono tryb real-time (Ctrl+C aby zatrzymać)")
    print(f"   Odświeżanie co {interval} sekund")
    
    # Pierwszy raz: upload definicji
    pointer = upload_definition()
    if not pointer:
        print("✗ Nie udało się załadować definicji")
        return
    
    try:
        iteration = 0
        while True:
            iteration += 1
            print(f"\n--- Iteracja {iteration} ---")
            
            # Możesz tutaj zmieniać params dynamicznie
            # np. params['radius'] = 3 + iteration * 0.5
            
            result = solve_definition(pointer)
            if result:
                import_to_blender(result)
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n⏹ Zatrzymano real-time loop")

# Odkomentuj aby uruchomić w pętli:
# real_time_loop(interval=2.0)