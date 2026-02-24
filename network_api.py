from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse,RedirectResponse
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
import threading
import concurrent.futures
import network_scanner

load_dotenv()

AUTH_PIN = os.getenv("AUTH_PIN", "1234")
SECRET_KEY = os.getenv("SECRET_KEY", "changez-cette-cle-secrete")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
templates = Jinja2Templates(directory="templates")


def is_authenticated(request: Request) -> bool:
    return request.session.get("authenticated") is True


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


# Scan state management
scan_state = {"status": "idle", "started_at": None, "machines_found": 0, "error": None}
scan_lock = threading.Lock()

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

# SSH Configuration from environment
from dotenv import load_dotenv
load_dotenv()
SSH_USERNAME = os.getenv("SSH_USERNAME")
SSH_PASSWORD = os.getenv("SSH_PASSWORD")
import paramiko

def execute_ssh_command(ip, command):
    """Exécute une commande SSH sur une machine distante."""
    ssh = None
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=SSH_USERNAME, password=SSH_PASSWORD, timeout=5)
        stdin, stdout, stderr = ssh.exec_command(command, timeout=20)
        # Injection du mot de passe pour sudo -S
        if SSH_PASSWORD:
             stdin.write(SSH_PASSWORD + '\n')
             stdin.flush()
        
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        return {"success": True, "output": output, "error": error}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if ssh:
            try:
                ssh.close()
            except:
                pass

from pydantic import BaseModel

class ActionRequest(BaseModel):
    ips: List[str]

@app.post("/actions/chrome-cleanup")
def chrome_cleanup(request: ActionRequest):
    """Ferme Chrome et nettoie les caches/cookies/historique pour l'utilisateur actuellement connecté."""
    # Requiert Full Disk Access pour sshd sur les machines cibles :
    # Préférences Système > Confidentialité > Accès complet au disque > ajouter /usr/sbin/sshd
    import base64
    script = """#!/bin/bash
GUI_USER=$(stat -f%Su /dev/console)
echo "Utilisateur cible : $GUI_USER"
if [ -z "$GUI_USER" ] || [ "$GUI_USER" = "root" ]; then
    echo "ERREUR: Aucun utilisateur GUI detecte"
    exit 1
fi

CHROME_DIR="/Users/$GUI_USER/Library/Application Support/Google/Chrome"
CACHE_DIR="/Users/$GUI_USER/Library/Caches/Google/Chrome"

# Fermer TOUS les processus Chrome (main + helpers GPU/Renderer)
pkill -f "Google Chrome" 2>/dev/null
sleep 2
pkill -9 -f "Google Chrome" 2>/dev/null
sleep 1

# Verifier que Chrome est bien arrete
if pgrep -f "Google Chrome" > /dev/null 2>&1; then
    echo "ATTENTION: Des processus Chrome sont encore actifs"
    pgrep -fl "Google Chrome"
fi

# Supprimer le cache
if [ -d "$CACHE_DIR" ]; then
    rm -rf "$CACHE_DIR" && echo "Cache supprime: $CACHE_DIR" || echo "ECHEC suppression cache: $CACHE_DIR"
else
    echo "Cache introuvable: $CACHE_DIR"
fi

# Supprimer cookies et historique
for f in Cookies Cookies-journal History History-journal; do
    find "$CHROME_DIR" -maxdepth 3 -name "$f" -delete -print 2>&1
done

echo "Nettoyage termine pour $GUI_USER"
"""
    encoded = base64.b64encode(script.encode()).decode()
    command = f"echo {encoded} | base64 -D > /tmp/_chrome_cleanup.sh && sudo -S bash /tmp/_chrome_cleanup.sh; rm -f /tmp/_chrome_cleanup.sh"
    results = {}
    for ip in request.ips:
        results[ip] = execute_ssh_command(ip, command)
    return results

@app.post("/actions/restart")
def restart_machine(request: ActionRequest):
    """Redémarre la machine via sudo shutdown -r now."""
    command = "sudo -S shutdown -r now"
    results = {}
    for ip in request.ips:
        results[ip] = execute_ssh_command(ip, command)
    return results

@app.post("/actions/shutdown")
def shutdown_machine(request: ActionRequest):
    """Éteint la machine via sudo shutdown -h now."""
    command = "sudo -S shutdown -h now"
    results = {}
    for ip in request.ips:
        results[ip] = execute_ssh_command(ip, command)
    return results

def _send_notification(ips: List[str]):
    """Helper interne pour envoyer l'alerte AppleScript à une liste d'IPs."""
    script = """#!/bin/bash
GUI_USER=$(stat -f%Su /dev/console)
if [ -z "$GUI_USER" ] || [ "$GUI_USER" = "root" ]; then
    echo "ERREUR: Aucun utilisateur GUI detecte"
    exit 1
fi

USER_ID=$(id -u "$GUI_USER")
echo "Envoi de la notification 'Opération Clean Desk' a $GUI_USER (UID: $USER_ID)..."

# Utilisation de launchctl asuser pour s'assurer que l'alerte s'affiche dans la session de l'utilisateur
launchctl asuser "$USER_ID" sudo -u "$GUI_USER" osascript <<EOF
display alert "Opération Clean Desk !" message "Mac, chargeur, adaptateurs. ✅
Écran Mac : Chiffon SEC uniquement ! 🚨

Un bureau propre, c'est un esprit frais pour finir la semaine ! 🚀" as critical buttons {"Fermer"} default button "Fermer"
EOF
"""
    import base64
    encoded = base64.b64encode(script.encode()).decode()
    command = f"echo {encoded} | base64 -D > /tmp/_warn_cleanup.sh && sudo -S bash /tmp/_warn_cleanup.sh; rm -f /tmp/_warn_cleanup.sh"
    print(f"[*] Envoi de notification à {len(ips)} machines en parallèle...")
    results = {}
    
    def _single_notify(ip):
        return ip, execute_ssh_command(ip, command)

    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        future_to_ip = {executor.submit(_single_notify, ip): ip for ip in ips}
        for future in concurrent.futures.as_completed(future_to_ip):
            ip, res = future.result()
            results[ip] = res
            
    return results

@app.post("/actions/warn-cleanup")
def warn_cleanup(request: ActionRequest):
    """Envoie une notification AppleScript pour avertir l'utilisateur de nettoyer son Mac."""
    return _send_notification(request.ips)

def run_weekly_scheduler():
    """Thread de fond pour envoyer les notifications automatiquement selon le planning .env"""
    import time
    from dotenv import load_dotenv
    load_dotenv()
    
    target_day = os.getenv("CLEANUP_SCHEDULE_DAY", "friday").lower()
    target_time = os.getenv("CLEANUP_SCHEDULE_TIME", "16:00")
    
    last_run_date = None
    
    print(f"[*] Planificateur activé : {target_day} à {target_time}")
    
    while True:
        now = datetime.now()
        current_day = now.strftime("%A").lower()
        current_time = now.strftime("%H:%M")
        current_date = now.strftime("%Y-%m-%d")
        
        if current_day == target_day and current_time == target_time:
            if last_run_date != current_date:
                print(f"[!] Lancement de la notification hebdomadaire automatique ({current_date})...")
                try:
                    # Récupérer toutes les IPs connues
                    data = load_and_merge_json_files()
                    ips = list(set([entry.get('ip') for entry in data if entry.get('ip')]))
                    if ips:
                        results = _send_notification(ips)
                        last_run_date = current_date
                        success_count = sum(1 for r in results.values() if r.get('success'))
                        error_count = len(ips) - success_count
                        print(f"[*] Notification terminée : {success_count} OK, {error_count} Échecs.")
                        
                        # Log des erreurs s'il y en a
                        for ip, res in results.items():
                            if not res.get('success') or res.get('error'):
                                print(f"  [!] {ip}: {res}")
                    else:
                        print("[?] Aucune machine trouvée pour la notification automatique.")
                except Exception as e:
                    print(f"[!] Erreur programmation scheduler : {e}")
        
        # Attendre 30 secondes avant la prochaine vérification
        time.sleep(30)

# Lancement du scheduler dans un thread séparé
threading.Thread(target=run_weekly_scheduler, daemon=True).start()

def _cleanup_json(max_files=5):
    """Supprime les fichiers JSON les plus anciens si leur nombre dépasse la limite."""
    files = glob.glob("smartelia_machines_*.json")
    if len(files) <= max_files:
        return
    files_sorted = sorted(files, key=lambda f: os.path.getmtime(f))
    while len(files_sorted) > max_files:
        to_remove = files_sorted.pop(0)
        try:
            os.remove(to_remove)
        except Exception:
            pass

def _run_scan():
    """Exécute le scan réseau en arrière-plan et met à jour scan_state."""
    global scan_state
    try:
        scan_state["status"] = "running"
        scan_state["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        scan_state["machines_found"] = 0
        scan_state["error"] = None
        _cleanup_json()
        network_scanner.main()
        # Compter les machines du dernier fichier JSON généré
        files = sorted(glob.glob("smartelia_machines_*.json"), key=os.path.getmtime)
        if files:
            with open(files[-1], 'r', encoding='utf-8') as f:
                data = json.load(f)
                scan_state["machines_found"] = len(data)
        scan_state["status"] = "completed"
    except Exception as e:
        scan_state["status"] = "error"
        scan_state["error"] = str(e)

@app.post("/actions/scan")
def start_scan():
    """Lance un scan réseau en arrière-plan."""
    with scan_lock:
        if scan_state["status"] == "running":
            return {"status": "already_running", "started_at": scan_state["started_at"]}
        scan_state["status"] = "running"
    thread = threading.Thread(target=_run_scan, daemon=True)
    thread.start()
    return {"status": "started"}

@app.get("/actions/scan/status")
def get_scan_status():
    """Retourne l'état actuel du scan."""
    return scan_state

def deploy_to_machine(ip, local_path, filename):
    """Copie un fichier via SFTP puis l'installe automatiquement selon son type."""
    ssh = None
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=SSH_USERNAME, password=SSH_PASSWORD, timeout=10)

        # 1. Copie SFTP vers /tmp/
        remote_path = f"/tmp/{filename}"
        sftp = ssh.open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()

        # 2. Detecter le type et construire la commande d'installation
        lower = filename.lower()
        if lower.endswith('.pkg'):
            install_cmd = f'sudo -S installer -pkg "{remote_path}" -target / 2>&1; rm -f "{remote_path}"'
        elif lower.endswith('.dmg'):
            install_cmd = (
                f'MOUNT_DIR=$(hdiutil attach "{remote_path}" -nobrowse -noverify 2>&1 | tail -1 | cut -f3); '
                f'if [ -n "$MOUNT_DIR" ]; then '
                f'  PKG=$(find "$MOUNT_DIR" -maxdepth 2 -name "*.pkg" | head -1); '
                f'  if [ -n "$PKG" ]; then '
                f'    sudo -S installer -pkg "$PKG" -target / 2>&1; '
                f'  else '
                f'    APP=$(find "$MOUNT_DIR" -maxdepth 2 -name "*.app" | head -1); '
                f'    if [ -n "$APP" ]; then '
                f'      APP_NAME=$(basename "$APP"); '
                f'      pkill -f "$APP_NAME" 2>/dev/null; sleep 1; '
                f'      sudo -S rsync -a "$APP" /Applications/ 2>&1; '
                f'      sudo -S xattr -rd com.apple.quarantine "/Applications/$APP_NAME" 2>/dev/null; '
                f'    else '
                f'      echo "Aucun .pkg ou .app trouve dans le DMG"; '
                f'    fi; '
                f'  fi; '
                f'  hdiutil detach "$MOUNT_DIR" -quiet 2>&1; '
                f'fi; '
                f'rm -f "{remote_path}"'
            )
        elif lower.endswith('.zip'):
            install_cmd = (
                f'unzip -o "{remote_path}" -d /tmp/_deploy_unzip 2>&1; '
                f'APP=$(find /tmp/_deploy_unzip -maxdepth 2 -name "*.app" | head -1); '
                f'if [ -n "$APP" ]; then '
                f'  APP_NAME=$(basename "$APP"); '
                f'  pkill -f "$APP_NAME" 2>/dev/null; sleep 1; '
                f'  sudo -S rsync -a "$APP" /Applications/ 2>&1; '
                f'  sudo -S xattr -rd com.apple.quarantine "/Applications/$APP_NAME" 2>/dev/null; '
                f'else '
                f'  echo "Aucun .app trouve dans le ZIP"; '
                f'fi; '
                f'rm -rf /tmp/_deploy_unzip "{remote_path}"'
            )
        elif lower.endswith('.mobileconfig'):
            install_cmd = f'sudo -S profiles install -path "{remote_path}" 2>&1; rm -f "{remote_path}"'
        elif lower.endswith('.sh'):
            install_cmd = f'sudo -S bash "{remote_path}" 2>&1; rm -f "{remote_path}"'
        else:
            install_cmd = f'echo "Type de fichier non supporte: {filename}"; rm -f "{remote_path}"'

        # 3. Executer la commande d'installation
        stdin, stdout, stderr = ssh.exec_command(install_cmd, timeout=120)
        if SSH_PASSWORD:
            stdin.write(SSH_PASSWORD + '\n')
            stdin.flush()
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        return {"success": True, "output": output, "error": error}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}
    finally:
        if ssh:
            try:
                ssh.close()
            except:
                pass

@app.post("/actions/deploy")
async def deploy_file(file: UploadFile = File(...), ips: str = Form(...)):
    """Upload un fichier et le deploie sur les machines cibles."""
    import shutil
    import tempfile

    # Parser la liste d'IPs
    try:
        ip_list = json.loads(ips)
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Format IPs invalide"})

    if not ip_list:
        return JSONResponse(status_code=400, content={"error": "Aucune IP cible"})

    # Sauvegarder le fichier temporairement sur le serveur
    os.makedirs("uploads", exist_ok=True)
    local_path = os.path.join("uploads", file.filename)
    try:
        with open(local_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Deployer sur chaque machine
        results = {}
        for ip in ip_list:
            results[ip] = deploy_to_machine(ip, local_path, file.filename)
    finally:
        # Nettoyer le fichier local
        if os.path.exists(local_path):
            os.remove(local_path)

    return results

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
        'battery_status', 'battery_details', 'current_user', 'uptime', 'date_recuperation',
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
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        reload=True
    )