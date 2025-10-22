import bpy
import requests
import json
import base64
import os

# ========== KONFIGURACJA ==========
HOPS_URL = "http://localhost:6500"

# OPCJA 1: Podaj ścieżkę bezpośrednio
GH_FILE = r"C:\gh_definitions\cylinder.gh"  # ZMIEŃ NA SWOJĄ ŚCIEŻKĘ!

# OPCJA 2: Wybierz plik przez dialog (odkomentuj poniższe 3 linijki)
# from tkinter import Tk
# from tkinter.filedialog import askopenfilename
# GH_FILE = askopenfilename(title="Wybierz plik Grasshopper", filetypes=[("Grasshopper", "*.gh *.ghx")])

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

# ========== ROZWIĄZANIE DEFINICJI ==========
def solve_directly():
    """Rozwiąż bezpośrednio wysyłając algo + values"""
    
    if not os.path.exists(GH_FILE):
        print(f"✗ Nie znaleziono pliku: {GH_FILE}")
        return None
    
    # Wczytaj plik .gh jako base64
    with open(GH_FILE, 'rb') as f:
        gh_bytes = f.read()
    gh_base64 = base64.b64encode(gh_bytes).decode('utf-8')
    
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
    
    # Wyślij do /grasshopper endpoint
    url = f"{HOPS_URL}/grasshopper"
    payload = {
        "algo": gh_base64,
        "pointer": None,
        "values": values
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
            print(f"✗ Błąd {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return None
            
    except Exception as e:
        print(f"✗ Błąd: {e}")
        import traceback
        traceback.print_exc()
        return None

# ========== IMPORT DO BLENDERA (POPRAWIONY) ==========
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
            print(f"    ⚠ Brak InnerTree")
            continue
            
        for branch_path, items in output['InnerTree'].items():
            print(f"    Branch: {branch_path}, Items: {len(items)}")
            for idx, item in enumerate(items):
                if 'data' not in item:
                    print(f"      Item {idx}: brak 'data'")
                    continue
                
                item_type = item.get('type', 'Unknown')
                print(f"      Item {idx}: type={item_type}")
                
                try:
                    # Parsuj JSON - to jest format Hops!
                    if isinstance(item['data'], str):
                        data_json = json.loads(item['data'])
                    else:
                        data_json = item['data']
                    
                    print(f"        → Format danych: version={data_json.get('version')}")
                    
                    # KLUCZ: Decode() przyjmuje SŁOWNIK, nie bajty!
                    geom = rh.CommonObject.Decode(data_json)
                    
                    if geom is None:
                        print(f"        ⚠ Nie udało się zdekodować geometrii")
                        continue
                    
                    print(f"        → Typ geometrii: {type(geom).__name__}")
                    
                    # Konwersja Mesh
                    if isinstance(geom, rh.Mesh):
                        verts = [(v.X, v.Y, v.Z) for v in geom.Vertices]
                        faces = []
                        
                        # Faces w rhino3dm zwraca tuple (A, B, C, D) lub (A, B, C, 0) dla trójkątów
                        for i in range(geom.Faces.Count):
                            face = geom.Faces[i]
                            # face to tuple: (A, B, C, D) gdzie D może być == C dla trójkąta
                            if len(face) == 4 and face[3] != face[2]:  # Quad
                                faces.append([face[0], face[1], face[2], face[3]])
                            else:  # Triangle
                                faces.append([face[0], face[1], face[2]])
                        
                        # Stwórz Blender mesh
                        mesh = bpy.data.meshes.new(f"GH_{param_name}_{count}")
                        mesh.from_pydata(verts, [], faces)
                        mesh.update()
                        
                        # Dodaj do sceny
                        obj = bpy.data.objects.new(f"GH_{param_name}_{count}", mesh)
                        bpy.context.collection.objects.link(obj)
                        
                        print(f"        ✓ Mesh: {len(verts)} wierzchołków, {len(faces)} ścian")
                        count += 1
                    
                    # Konwersja Brep
                    elif isinstance(geom, rh.Brep):
                        print(f"        → Konwertuję Brep na mesh...")
                        brep_mesh = rh.Mesh()
                        
                        # Iteruj przez powierzchnie Brep
                        for face_idx in range(len(geom.Faces)):
                            face = geom.Faces[face_idx]
                            face_mesh = face.GetMesh(rh.MeshType.Default)
                            if face_mesh:
                                brep_mesh.Append(face_mesh)
                        
                        if len(brep_mesh.Vertices) > 0:
                            verts = [(v.X, v.Y, v.Z) for v in brep_mesh.Vertices]
                            faces = []
                            
                            # Tak samo jak dla Mesh - używamy indeksowania
                            for i in range(brep_mesh.Faces.Count):
                                face = brep_mesh.Faces[i]
                                if len(face) == 4 and face[3] != face[2]:
                                    faces.append([face[0], face[1], face[2], face[3]])
                                else:
                                    faces.append([face[0], face[1], face[2]])
                            
                            # Stwórz Blender mesh
                            bl_mesh = bpy.data.meshes.new(f"GH_{param_name}_{count}")
                            bl_mesh.from_pydata(verts, [], faces)
                            bl_mesh.update()
                            
                            obj = bpy.data.objects.new(f"GH_{param_name}_{count}", bl_mesh)
                            bpy.context.collection.objects.link(obj)
                            
                            print(f"        ✓ Brep→Mesh: {len(verts)} wierzchołków, {len(faces)} ścian")
                            count += 1
                        else:
                            print(f"        ⚠ Brep nie ma wierzchołków po konwersji")
                    
                    # Konwersja Curve
                    elif isinstance(geom, rh.Curve):
                        print(f"        → Konwertuję Curve...")
                        # Spróbuj zrobić mesh z curve (pipe, extrude, etc)
                        # lub stwórz krzywą Blendera
                        print(f"        ⚠ Import krzywych nie zaimplementowany")
                    
                    else:
                        print(f"        ⚠ Nieobsługiwany typ: {type(geom).__name__}")
                    
                except Exception as e:
                    print(f"        ⚠ Błąd importu: {e}")
                    import traceback
                    traceback.print_exc()
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
    
    # 2. Rozwiąż definicję
    result = solve_directly()
    
    # 3. Importuj do Blendera
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
    
    try:
        iteration = 0
        while True:
            iteration += 1
            print(f"\n--- Iteracja {iteration} ---")
            
            # Możesz tutaj zmieniać params dynamicznie
            # np. params['radius'] = 3 + iteration * 0.5
            
            result = solve_directly()
            if result:
                import_to_blender(result)
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n⏹ Zatrzymano real-time loop")

# Odkomentuj aby uruchomić w pętli:
# real_time_loop(interval=2.0)