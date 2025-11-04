from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse
import glob
import json
import os
from typing import List, Dict
from fastapi.templating import Jinja2Templates
from fastapi import Request
import re

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Fonction utilitaire pour charger et fusionner les données sans doublons

def load_and_merge_json_files() -> List[Dict]:
    files = glob.glob("smartelia_machines_*.json")
    # Correction du pattern pour matcher le nom de fichier
    file_date_pattern = re.compile(r"smartelia_machines_(\d{8}_\d{6})\.json")
    file_dates = {}
    for file in files:
        m = file_date_pattern.search(file)
        if m:
            file_dates[file] = m.group(1)
    # Trier les fichiers par date croissante
    sorted_files = sorted(file_dates.items(), key=lambda x: x[1])
    # Pour chaque hostname, garder la donnée la plus récente
    latest_data = {}
    for file, date in sorted_files:
        with open(file, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                for entry in data:
                    hostname = entry.get('hostname')
                    if not hostname:
                        continue
                    # Ajout de la date de récupération (depuis le nom du fichier)
                    entry['date_recuperation'] = date
                    # Remplacement de full_charge_capacity par max_capacity
                    battery_details = entry.get('battery_details', {})
                    if 'full_charge_capacity' in battery_details:
                        battery_details['max_capacity'] = battery_details.get('full_charge_capacity')
                    entry['battery_details'] = battery_details
                    # On écrase si plus récent
                    latest_data[hostname] = entry
            except Exception as e:
                print(f"Erreur lors de la lecture de {file}: {e}")
    return list(latest_data.values())

@app.get("/machines", response_class=JSONResponse)
def get_machines():
    """Retourne la liste fusionnée des machines sans doublons."""
    data = load_and_merge_json_files()
    return data

@app.get("/machines/html", response_class=HTMLResponse)
def get_machines_html(request: Request):
    data = load_and_merge_json_files()
    print(f"Nombre de machines à afficher : {len(data)}")
    if data:
        print("Premier élément :", data[0])
    columns = [
        'ip', 'mac', 'hostname', 'model_info', 'macos_version', 'model_identifier',
        'taille', 'annee', 'disk_free', 'ram_info', 'open_apps',
        'battery_status', 'battery_details', 'current_user', 'date_recuperation'
    ]
    return templates.TemplateResponse(
        "machines_table.html",
        {"request": request, "data": data, "columns": columns}
    )

@app.get("/")
def root():
    return {"message": "Bienvenue sur l'API de visualisation des machines SMARTELIA."} 