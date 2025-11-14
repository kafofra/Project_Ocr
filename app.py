import os
import uuid
import time
import json
import csv
from datetime import datetime
from threading import Lock
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from extractor import ImportDeclarationExtractor

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'outputs')

# --- Fichiers Maîtres (remplacent la base de données) ---
MASTER_JSON_PATH = os.path.join(BASE_DIR, 'GLOBAL_HISTORY.json')
MASTER_CSV_PATH = os.path.join(BASE_DIR, 'GLOBAL_HISTORY.csv')
# Verrou pour empêcher deux écritures simultanées qui corrompraient les fichiers
FILE_LOCK = Lock()

for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER]:
    os.makedirs(folder, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# --- Initialisation des fichiers maîtres ---
def init_master_files():
    with FILE_LOCK:
        # Si le JSON maître n'existe pas, on le crée avec une liste vide
        if not os.path.exists(MASTER_JSON_PATH):
            with open(MASTER_JSON_PATH, 'w', encoding='utf-8') as f:
                json.dump([], f)
        
        # Pour le CSV maître, on attendra la première extraction pour connaître les en-têtes exacts,
        # ou on peut l'initialiser plus tard.

init_master_files()

# --- Fonctions utilitaires pour les fichiers maîtres ---
def append_to_master_json(record):
    """Lit tout le JSON, ajoute l'enregistrement, et réécrit tout (sécurisé par Lock)"""
    with FILE_LOCK:
        try:
            with open(MASTER_JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = []
        
        data.append(record)
        
        with open(MASTER_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

def append_to_master_csv(flat_data):
    """Ajoute une ligne au CSV maître (sécurisé par Lock)"""
    with FILE_LOCK:
        file_exists = os.path.exists(MASTER_CSV_PATH)
        with open(MASTER_CSV_PATH, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=flat_data.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(flat_data)

# --- Endpoints API ---

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "online", "storage": "Flat Files (No DB)"}), 200

@app.route('/api/history', methods=['GET'])
def get_history():
    """Lit le fichier JSON maître pour le dashboard"""
    try:
        with FILE_LOCK:
            if not os.path.exists(MASTER_JSON_PATH):
                 return jsonify([])
            with open(MASTER_JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
        # On renvoie les 50 derniers, inversés pour avoir les plus récents en premier
        return jsonify(data[-50:][::-1])
    except Exception as e:
        return jsonify([]), 200 # En cas d'erreur (ex: fichier vide), on renvoie une liste vide

@app.route('/api/extract/batch', methods=['POST'])
def batch_extract():
    if 'files' not in request.files:
        return jsonify({"error": "Aucun fichier détecté"}), 400
    
    files = request.files.getlist('files')
    results = []

    for file in files:
        if file.filename == '': continue
        
        task_id = str(uuid.uuid4())
        original_name = secure_filename(file.filename)
        file_ext = os.path.splitext(original_name)[1].lower()
        
        if file_ext not in ['.pdf', '.txt']:
            results.append({"filename": original_name, "status": "error", "error": "Format invalide"})
            continue

        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{task_id}{file_ext}")
        file.save(temp_path)

        try:
            extractor = ImportDeclarationExtractor()
            # 1. Extraction
            text = extractor.extract_from_pdf(temp_path) if file_ext == '.pdf' else open(temp_path, 'r', encoding='utf-8').read()
            data = extractor.extract_all_fields(text)
            
            # 2. Sauvegarde des fichiers INDIVIDUELS (pour téléchargement immédiat facile)
            base_name = f"SGS_{datetime.now().strftime('%Y%m%d')}_{task_id[:6]}"
            json_link = f"{base_name}.json"
            csv_link = f"{base_name}.csv"
            extractor.save_to_json(data, os.path.join(app.config['OUTPUT_FOLDER'], json_link))
            extractor.save_to_csv(data, os.path.join(app.config['OUTPUT_FOLDER'], csv_link))

            # 3. Ajout aux fichiers MAÎTRES (GLOBAL_HISTORY)
            stats = data['_statistics']
            
            # Préparation de l'enregistrement pour l'historique JSON Master
            history_record = {
                "id": task_id,
                "filename": original_name,
                "date": datetime.now().isoformat(),
                "status": "success",
                "fields_found": stats['extracted_fields'],
                "total_fields": stats['total_fields'],
                # On garde les liens vers les fichiers individuels pour le téléchargement depuis l'historique
                "json_path": json_link, 
                "csv_path": csv_link,
                # Optionnel : on peut aussi sauvegarder TOUTES les données extraites dans l'historique JSON
                # "full_data": data 
            }
            append_to_master_json(history_record)

            # Préparation et ajout au Master CSV
            # On aplatit les données et on ajoute les métadonnées (date, nom fichier...)
            flat_data = extractor._flatten_dict(data)
            # On retire les stats techniques du CSV métier pour qu'il reste propre
            keys_to_remove = [k for k in flat_data.keys() if k.startswith('_statistics')]
            for k in keys_to_remove:
                del flat_data[k]
            # On ajoute des colonnes utiles au début
            master_csv_record = {
                "Extraction_ID": task_id,
                "Date_Extraction": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "Fichier_Source": original_name,
                **flat_data
            }
            append_to_master_csv(master_csv_record)

            results.append({
                "filename": original_name,
                "status": "success",
                "stats": stats,
                "downloads": {"json": f"/api/download/{json_link}", "csv": f"/api/download/{csv_link}"}
            })

        except Exception as e:
             # En cas d'erreur, on l'ajoute aussi à l'historique JSON pour garder une trace
            error_record = {
                "id": task_id, "filename": original_name, "date": datetime.now().isoformat(),
                "status": "error", "error_msg": str(e), "fields_found": 0, "total_fields": 0,
                "json_path": "", "csv_path": ""
            }
            append_to_master_json(error_record)
            results.append({"filename": original_name, "status": "error", "error": str(e)})
        finally:
            if os.path.exists(temp_path): os.remove(temp_path)

    return jsonify({"batch_results": results})

@app.route('/api/download/<path:filename>')
def download_file(filename):
    # Petit hack : si on demande "GLOBAL_CSV", on renvoie le fichier maître
    if filename == "GLOBAL_CSV":
        return send_from_directory(BASE_DIR, 'GLOBAL_HISTORY.csv', as_attachment=True)
    if filename == "GLOBAL_JSON":
        return send_from_directory(BASE_DIR, 'GLOBAL_HISTORY.json', as_attachment=True)
        
    return send_from_directory(app.config['OUTPUT_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    print("🟢 SERVEUR V2.1 (NO-DB) PRÊT SUR LE PORT 5000")
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)