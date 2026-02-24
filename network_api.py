from fastapi import FastAPI, Form
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, RedirectResponse
import glob
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict
from fastapi.templating import Jinja2Templates
from fastapi import Request
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
import re

load_dotenv()

AUTH_PIN = os.getenv("AUTH_PIN", "1234")
SECRET_KEY = os.getenv("SECRET_KEY", "changez-cette-cle-secrete")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
templates = Jinja2Templates(directory="templates")


def is_authenticated(request: Request) -> bool:
    return request.session.get("authenticated") is True

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
    # trackers pour calculer depuis quand le chargeur est branché à 100%
    charger_starts = {}
    latest_dt = {}

    for file, date in sorted_files:
        # tenter de parser la date extraite du nom de fichier et la formater lisiblement
        nice_date = date
        try:
            from datetime import datetime
            dt = datetime.strptime(date, "%Y%m%d_%H%M%S")
            nice_date = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            # si parse échoue, conserver la valeur brute
            pass

        with open(file, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                for entry in data:
                    hostname = entry.get('hostname')
                    if not hostname:
                        continue
                    # Ajout de la date de récupération (format lisible)
                    entry['date_recuperation'] = nice_date
                    # Remplacement de full_charge_capacity par max_capacity
                    battery_details = entry.get('battery_details', {})
                    if 'full_charge_capacity' in battery_details:
                        battery_details['max_capacity'] = battery_details.get('full_charge_capacity')
                    entry['battery_details'] = battery_details
                    # tracker du dernier dt connu pour ce hostname
                    if 'dt' in locals() and isinstance(dt, datetime):
                        latest_dt[hostname] = dt

                    # déterminer si, à ce moment, la machine est branchée et à 100%
                    batt = entry.get('battery_status', {}) or {}
                    percent = None
                    power_plugged = None
                    try:
                        if isinstance(batt, dict):
                            percent = batt.get('percent')
                            power_plugged = batt.get('power_plugged')
                    except Exception:
                        pass

                    # Prendre aussi en compte le champ drawing_from (ex: 'AC Power' / 'Battery Power')
                    drawing_from = None
                    try:
                        if isinstance(batt, dict):
                            drawing_from = batt.get('drawing_from')
                    except Exception:
                        drawing_from = None

                    is_charging_100 = False
                    if percent is not None and percent == 100:
                        # Si drawing_from indique 'Battery', considérer comme non branchée
                        if drawing_from:
                            sdraw = str(drawing_from).lower()
                            if 'battery' in sdraw:
                                is_charging_100 = False
                            else:
                                # otherwise fallback to power_plugged or textual checks
                                if isinstance(power_plugged, bool):
                                    is_charging_100 = power_plugged is True
                                else:
                                    s = str(power_plugged).lower()
                                    if 'ac' in s or 'charge' in s or 'true' in s or 'oui' in s:
                                        is_charging_100 = True
                        else:
                            # Pas de drawing_from, utiliser power_plugged
                            if isinstance(power_plugged, bool):
                                is_charging_100 = power_plugged is True
                            else:
                                s = str(power_plugged).lower()
                                if 'ac' in s or 'charge' in s or 'true' in s or 'oui' in s:
                                    is_charging_100 = True

                    # mettre à jour le démarrage du mode 100%+secteur
                    if is_charging_100 and 'dt' in locals() and isinstance(dt, datetime):
                        if hostname not in charger_starts:
                            charger_starts[hostname] = dt
                    else:
                        # si condition non satisfaite, supprimer tout démarrage enregistré
                        if hostname in charger_starts:
                            del charger_starts[hostname]

                    # On écrase si plus récent
                    latest_data[hostname] = entry
            except Exception as e:
                print(f"Erreur lors de la lecture de {file}: {e}")
    # Après avoir parcouru l'historique, compléter les entrées finales avec la durée si applicable
    for hostname, entry in latest_data.items():
        start = charger_starts.get(hostname)
        last = latest_dt.get(hostname)
        if start and last and isinstance(start, datetime) and isinstance(last, datetime):
            delta = last - start
            secs = int(delta.total_seconds())
            # formater en human readable
            days, rem = divmod(secs, 86400)
            hours, rem = divmod(rem, 3600)
            minutes, seconds = divmod(rem, 60)
            parts = []
            if days:
                parts.append(f"{days}d")
            if hours:
                parts.append(f"{hours}h")
            if minutes:
                parts.append(f"{minutes}m")
            if seconds and not parts:
                parts.append(f"{seconds}s")
            human = ' '.join(parts) if parts else '0s'
            entry['charger_100_since'] = start.strftime("%Y-%m-%d %H:%M:%S")
            entry['charger_100_duration_seconds'] = secs
            entry['charger_100_duration'] = human
        else:
            entry['charger_100_since'] = None
            entry['charger_100_duration_seconds'] = 0
            entry['charger_100_duration'] = None

    return list(latest_data.values())

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
async def login_submit(request: Request, pin: str = Form(...)):
    if pin == AUTH_PIN:
        request.session["authenticated"] = True
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "PIN incorrect. Réessayez."},
        status_code=401
    )


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


@app.get("/machines", response_class=JSONResponse)
def get_machines():
    """Retourne la liste fusionnée des machines sans doublons."""
    data = load_and_merge_json_files()
    return data

@app.get("/", response_class=HTMLResponse)
def get_machines_html(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    data = load_and_merge_json_files()
    print(f"Nombre de machines à afficher : {len(data)}")
    if data:
        print("Premier élément :", data[0])
    columns = [
        'ip', 'mac', 'hostname', 'model_info', 'macos_version', 'model_identifier',
        'taille', 'annee', 'disk_free', 'ram_info', 'open_apps',
        'battery_status', 'battery_details', 'current_user', 'date_recuperation',
        'charger_100_since', 'charger_100_duration'
    ]
    return templates.TemplateResponse(
        "machines_table.html",
        {"request": request, "data": data, "columns": columns}
    )

@app.get("/test")
def root():
    return {"message": "Bienvenue sur l'API de visualisation des machines SMARTELIA."}

@app.get("/installers/os_downloader.sh")
def download_os_downloader():
    """Endpoint pour télécharger le script os_downloader.sh"""
    file_path = "os_downloader.sh"
    if os.path.exists(file_path):
        return FileResponse(
            path=file_path,
            filename="os_downloader.sh",
            media_type="application/x-sh"
        )
    else:
        return JSONResponse(
            status_code=404,
            content={"error": "Le fichier os_downloader.sh n'a pas été trouvé"}
        )

@app.get("/installers/os_installer.sh")
def download_os_installer():
    """Endpoint pour télécharger le script os_installer.sh"""
    file_path = "os_installer.sh"
    if os.path.exists(file_path):
        return FileResponse(
            path=file_path,
            filename="os_installer.sh",
            media_type="application/x-sh"
        )
    else:
        return JSONResponse(
            status_code=404,
            content={"error": "Le fichier os_installer.sh n'a pas été trouvé"}
        )

@app.get("/files/{filename}")
def download_file(filename: str):
    """Endpoint générique pour télécharger des fichiers depuis le dossier 'files'"""
    # Chemin vers le dossier files
    files_dir = "files"
    file_path = os.path.join(files_dir, filename)
    
    # Vérifier si le fichier existe
    if os.path.exists(file_path) and os.path.isfile(file_path):
        # Déterminer le type MIME approprié
        if filename.endswith('.sh'):
            media_type = "application/x-sh"
        elif filename.endswith('.zip'):
            media_type = "application/zip"
        elif filename.endswith('.app'):
            media_type = "application/x-apple-diskimage"
        elif filename.endswith('.dmg'):
            media_type = "application/x-apple-diskimage"
        elif filename.endswith('.pkg'):
            media_type = "application/vnd.apple.installer+xml"
        else:
            media_type = "application/octet-stream"
            
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=media_type
        )
    else:
        return JSONResponse(
            status_code=404,
            content={"error": f"Le fichier {filename} n'a pas été trouvé dans le dossier {files_dir}"}
        )

@app.get("/files")
def list_files():
    """Endpoint pour lister tous les fichiers disponibles dans le dossier 'files'"""
    files_dir = "files"
    available_files = []
    
    # Vérifier si le dossier files existe
    if not os.path.exists(files_dir):
        return JSONResponse(
            status_code=404,
            content={"error": f"Le dossier {files_dir} n'existe pas"}
        )
    
    # Lister tous les fichiers dans le dossier
    try:
        for filename in os.listdir(files_dir):
            file_path = os.path.join(files_dir, filename)
            if os.path.isfile(file_path):
                available_files.append({"name": filename})
    except PermissionError:
        return JSONResponse(
            status_code=403,
            content={"error": f"Permission refusée pour accéder au dossier {files_dir}"}
        )
    
    return available_files

# Configuration du serveur pour écouter sur toutes les interfaces
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0",  # Écouter sur toutes les interfaces
        port=8000,
        reload=True  # Rechargement automatique en développement
    ) 