#!/usr/bin/env python3
import socket
import subprocess
import platform
import concurrent.futures
from datetime import datetime
from tqdm import tqdm
import paramiko
import re
import time
import csv
import os
import glob
import json
from dotenv import load_dotenv

# Configuration SSH
USE_SSH = True  # Mettre à False pour désactiver SSH

# Configuration des applications macOS
APPLICATIONS_TO_CHECK = [
    "MonApplication.app",
    "AutreApplication.app",
    # Ajoutez ici les noms des applications à vérifier
]

# Chemins des applications sur macOS
APPLICATIONS_PATH = "Applications"  # Chemin relatif
FILES_PATH = "/Users/smartelia/files"  # Chemin sur le serveur

macbook_pro_models = {
    "Mac16,6": ("14 pouces", 2024),
    "Mac16,8": ("14 pouces", 2024),
    "Mac16,7": ("16 pouces", 2024),
    "Mac16,5": ("16 pouces", 2024),
    "Mac15,3": ("14 pouces", 2023),
    "Mac15,6": ("14 pouces", 2023),
    "Mac16,1": ("14 pouces", 2024),
    "Mac16,6": ("14 pouces", 2024),
    "Mac16,8": ("14 pouces", 2024),
    "Mac16,7": ("16 pouces", 2024),
    "Mac16,5": ("16 pouces", 2024),
    "Mac15,3": ("14 pouces", 2023),
    "Mac15,6": ("14 pouces", 2023),
    "Mac15,8": ("14 pouces", 2023),
    "Mac15,10":("14 pouces", 2023),
    "Mac15,7": ("16 pouces", 2023),
    "Mac15,9": ("16 pouces", 2023),
    "Mac15,11":("16 pouces", 2023),
    "Mac14,5": ("14 pouces", 2023),
    "Mac14,9": ("14 pouces", 2023),
    "Mac14,6": ("16 pouces", 2023),
    "Mac14,10":("16 pouces", 2023),
    "Mac14,7": ("13 pouces", 2022),
    "MacBookPro18,3":("14 pouces", 2021),
    "MacBookPro18,4":("14 pouces", 2021),
    "MacBookPro18,1":("16 pouces", 2021),
    "MacBookPro18,2":("16 pouces", 2021),
    "MacBookPro17,1":("13 pouces", 2020),
    "MacBookPro16,3":("13 pouces", 2020),
    "MacBookPro16,2":("13 pouces", 2020),
    "MacBookPro16,1":("16 pouces", 2019),
    "MacBookPro16,4":("16 pouces", 2019),
    "MacBookPro12,1": ("13 pouces", 2015),
    "MacBookPro14,2": ("13 pouces", 2017),
}

load_dotenv()
SSH_USERNAME = os.getenv("SSH_USERNAME")
SSH_PASSWORD = os.getenv("SSH_PASSWORD")

def ping(ip):
    """Ping an IP address and return True if it responds"""
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    timeout = '-W' if platform.system().lower() != 'windows' else '-w'
    timeout_value = '1' if platform.system().lower() != 'windows' else '1000'
    command = ['ping', param, '1', timeout, timeout_value, ip]
    return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0

def get_mac_address(ip):
    """Get MAC address using arp command"""
    try:
        # Exécuter la commande arp
        if platform.system().lower() == 'windows':
            output = subprocess.check_output(f'arp -a {ip}', shell=True).decode()
        else:
            output = subprocess.check_output(f'arp -n {ip}', shell=True).decode()
        
        # Extraire l'adresse MAC
        mac_pattern = r'([0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2})'
        match = re.search(mac_pattern, output)
        if match:
            return match.group(1)
    except:
        pass
    return "Unknown"

def exec_sudo_command(ssh, command, sudo_password):
    """
    Exécute une commande sudo avec timeout pour éviter les blocages
    """
    full_command = f"sudo -S {command}"
    stdin, stdout, stderr = ssh.exec_command(full_command, timeout=30)  # 30 secondes de timeout
    stdin.write(sudo_password + '\n')
    stdin.flush()
    
    # Attendre avec timeout
    try:
        exit_status = stdout.channel.recv_exit_status()
    except:
        # Si timeout, on force la fermeture
        stdout.channel.close()
        return -1, "", "Timeout after 30 seconds"
    
    out = stdout.read().decode()
    err = stderr.read().decode()
    return exit_status, out, err

def check_sudoers_configured(ssh, username):
    """Vérifie si les règles sudoers sont déjà configurées dans /etc/sudoers ou /etc/sudoers.d/*"""
    try:
        # Chercher dans /etc/sudoers
        stdin, stdout, stderr = ssh.exec_command(f'grep "{username}" /etc/sudoers', timeout=10)
        output_main = stdout.read().decode().strip()
        print(f"[DEBUG] Contenu sudoers (/etc/sudoers) pour {username}: {output_main}")
        has_user_main = username in output_main
        has_nopasswd_main = "NOPASSWD" in output_main
        has_requiretty_main = "!requiretty" in output_main

        # Chercher dans tous les fichiers /etc/sudoers.d/*
        stdin, stdout, stderr = ssh.exec_command('ls /etc/sudoers.d', timeout=10)
        files = stdout.read().decode().strip().split('\n')
        found_user = has_user_main
        found_nopasswd = has_nopasswd_main
        found_requiretty = has_requiretty_main

        for f in files:
            if not f:
                continue
            path = f"/etc/sudoers.d/{f}"
            stdin, stdout, stderr = ssh.exec_command(f'grep "{username}" {path}', timeout=10)
            output = stdout.read().decode().strip()
            print(f"[DEBUG] Contenu sudoers ({path}) pour {username}: {output}")
            if username in output:
                found_user = True
            if "NOPASSWD" in output:
                found_nopasswd = True
            if "!requiretty" in output:
                found_requiretty = True

        print(f"[DEBUG] Détection globale: user={found_user}, nopasswd={found_nopasswd}, requiretty={found_requiretty}")
        
        # Si la configuration n'est pas trouvée, essayer de la configurer automatiquement
        if not (found_user and found_nopasswd):
            print(f"[INFO] Configuration sudoers manquante pour {username}, tentative de configuration automatique...")
            if configure_sudoers_automatically(ssh, username):
                print(f"[SUCCESS] Configuration sudoers automatique réussie pour {username}")
                return True
            else:
                print(f"[WARNING] Échec de la configuration automatique sudoers pour {username}")
                return False
        
        return found_user and found_nopasswd
    except Exception as e:
        print(f"[DEBUG] Erreur lors de la vérification sudoers: {e}")
        return False

def configure_sudoers_automatically(ssh, username):
    """Configure automatiquement les règles sudoers pour l'utilisateur"""
    try:
        print(f"[INFO] Configuration automatique sudoers pour {username}...")
        
        # Sauvegarder le sudoers original
        stdin, stdout, stderr = ssh.exec_command('sudo cp /etc/sudoers /etc/sudoers.backup', timeout=30)
        if stdout.channel.recv_exit_status() != 0:
            print(f"[WARNING] Impossible de sauvegarder /etc/sudoers")
        
        # Ajouter les règles pour l'utilisateur
        commands = [
            f'echo "Defaults:{username} !requiretty" | sudo tee -a /etc/sudoers',
            f'echo "{username} ALL=(ALL) NOPASSWD: /usr/bin/dscl, /usr/sbin/createhomedir, /bin/mkdir, /bin/chown, /bin/chmod, /usr/bin/tee, /bin/cp, /bin/echo" | sudo tee -a /etc/sudoers'
        ]
        
        for cmd in commands:
            stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
            if stdout.channel.recv_exit_status() != 0:
                print(f"[ERROR] Échec de la commande: {cmd}")
                print(f"STDOUT: {stdout.read().decode().strip()}")
                print(f"STDERR: {stderr.read().decode().strip()}")
                return False
        
        print(f"[SUCCESS] Règles sudoers ajoutées pour {username}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Erreur lors de la configuration automatique sudoers: {e}")
        return False

def create_deployer_user(ssh, sudo_password, username):
    """
    Crée l'utilisateur deployer (sudoers déjà configuré via ARD)
    """
    print(f"[INFO] Vérification de la configuration sudoers...")
    if not check_sudoers_configured(ssh, username):
        print(f"[WARNING] Sudoers non configuré pour {username}, arrêt de la configuration deployer")
        return False
    
    print(f"[INFO] Sudoers configuré, création de l'utilisateur deployer...")
    
    ssh_key = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOyTZgRjxH2CG6ljmbFxvPXdWl1PJF5ZhcOVVHsRADVn deployer@SERVEUR-SMARTELIA'
    commands = [
        'dscl . -create /Users/deployer',
        'dscl . -create /Users/deployer UserShell /bin/zsh',
        'dscl . -create /Users/deployer RealName "Deployer Smartelia"',
        'dscl . -create /Users/deployer UniqueID 599',
        'dscl . -create /Users/deployer PrimaryGroupID 20',
        'dscl . -create /Users/deployer NFSHomeDirectory /var/.hidden/deployer',
        'dscl . -passwd /Users/deployer ""',
        'dscl . -create /Users/deployer Password "*"',
        'dscl . -create /Users/deployer IsHidden 1',
        'createhomedir -c -u deployer',
        'mkdir -p /var/.hidden/deployer/.ssh',
        f'echo "{ssh_key}" | sudo tee -a /var/.hidden/deployer/.ssh/authorized_keys > /dev/null',
        'chown -R deployer:staff /var/.hidden/deployer/.ssh',
        'chmod 700 /var/.hidden/deployer/.ssh',
        'chmod 600 /var/.hidden/deployer/.ssh/authorized_keys',
        'echo "deployer ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/deployer',
        'chmod 440 /etc/sudoers.d/deployer'
    ]

    success = True
    for cmd in commands:
        status, out, err = exec_sudo_command(ssh, cmd, sudo_password)
        if status != 0:
            print(f"[DEBUG] Erreur sur la commande : {cmd}\nSTDOUT:\n{out}\nSTDERR:\n{err}")
            if "Timeout" in err or status == -1:
                print(f"[ERROR] Arrêt de la configuration deployer sur cette machine")
                success = False
                break

    if success:
        print("[INFO] Utilisateur deployer créé/configuré avec clé SSH et sudoers.")
    return success

def try_ssh_connection(ip, username, password):
    """Try to connect via SSH and get hostname, model info, and macOS version"""
    try:
        print(f"[DEBUG] Tentative de connexion SSH à {ip} avec l'utilisateur {username}")
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Augmenter le timeout de connexion
        ssh.connect(ip, username=username, password=password, timeout=30)
        
        print(f"[DEBUG] Connexion SSH réussie à {ip}")

        # Vérifier si sudoers est configuré
        sudoers_configured = check_sudoers_configured(ssh, username)
        if not sudoers_configured:
            print(f"[WARNING] Sudoers non configuré sur {ip}, continuation en mode dégradé (sans configuration deployer)")
        
        # Création/configuration de l'utilisateur deployer seulement si sudoers est configuré
        if sudoers_configured:
            deployer_success = create_deployer_user(ssh, password, username)
            if not deployer_success:
                print(f"[WARNING] Échec de la configuration deployer sur {ip}, on continue avec smartelia")
        else:
            print(f"[INFO] Configuration deployer ignorée sur {ip} (sudoers non configuré)")

        # Création/configuration de l'utilisateur deployer
        deployer_success = create_deployer_user(ssh, password, username)
        if not deployer_success:
            print(f"[WARNING] Échec de la configuration deployer sur {ip}, on continue avec smartelia")
        
        # Configuration SSH pour l'utilisateur smartelia (désactivée)
        print(f"[INFO] Configuration SSH automatique désactivée sur {ip}")
        
        # Exécuter la commande hostname
        stdin, stdout, stderr = ssh.exec_command('hostname', timeout=10)
        hostname = stdout.read().decode().strip()

        # Récupérer le Model Name et Model Identifier
        stdin, stdout, stderr = ssh.exec_command('system_profiler SPHardwareDataType | grep "Model Name\\|Model Identifier"', timeout=30)
        model_info = stdout.read().decode().replace('\n', ' ').strip()

        # Détecter l'architecture (Intel/ARM)
        stdin, stdout, stderr = ssh.exec_command('uname -m', timeout=10)
        architecture = stdout.read().decode().strip()
        if architecture == 'arm64':
            arch_type = "Apple Silicon (ARM)"
        elif architecture == 'x86_64':
            arch_type = "Intel"
        else:
            arch_type = "Unknown"

        # Récupérer la version de macOS
        stdin, stdout, stderr = ssh.exec_command('sw_vers -productVersion', timeout=10)
        macos_version = stdout.read().decode().strip()
        
        # Espace de stockage
        stdin, stdout, stderr = ssh.exec_command('df -h / | awk \'NR==2 {print $4}\'', timeout=10)
        disk_free = stdout.read().decode().strip()

        # RAM
        stdin, stdout, stderr = ssh.exec_command('top -l 1 | grep PhysMem | awk \'{print $2" used, "$6" free"}\'', timeout=10)
        ram_info = stdout.read().decode().strip()

        # Applications ouvertes
        stdin, stdout, stderr = ssh.exec_command('osascript -e \'tell application "System Events" to get name of every process where background only is false\'', timeout=10)
        open_apps = stdout.read().decode().strip()

        # Batterie (pmset)
        stdin, stdout, stderr = ssh.exec_command('pmset -g batt', timeout=10)
        battery_status_raw = stdout.read().decode().strip()
        # Parsing battery_status
        percent = None
        power_plugged = None
        time_left = None
        drawing_from = None
        percent_match = re.search(r'(\d+)%', battery_status_raw)
        if percent_match:
            percent = int(percent_match.group(1))
        power_plugged = 'AC Power' in battery_status_raw or 'chargé' in battery_status_raw or 'charging' in battery_status_raw
        time_left_match = re.search(r'(\d+:\d+) remaining', battery_status_raw)
        if time_left_match:
            time_left = time_left_match.group(1)
        else:
            time_left = None
        # Extraire la source d'alimentation (Now drawing from ...)
        drawing_from_match = re.search(r"Now drawing from '([^']+)'", battery_status_raw)
        if drawing_from_match:
            drawing_from = drawing_from_match.group(1)
        battery_status = {
            'percent': percent,
            'power_plugged': power_plugged,
            'time_left': time_left,
            'drawing_from': drawing_from
        }

        # Capacités et cycles (system_profiler)
        stdin, stdout, stderr = ssh.exec_command('system_profiler SPPowerDataType', timeout=30)
        battery_profiler = stdout.read().decode()
        cycle_count = None
        full_charge_capacity = None
        condition = None
        for line in battery_profiler.splitlines():
            if 'Cycle Count' in line:
                try:
                    cycle_count = int(line.split(':')[-1].strip())
                except:
                    pass
            if 'Full Charge Capacity' in line:
                try:
                    full_charge_capacity = int(line.split(':')[-1].strip().replace('mAh','').strip())
                except:
                    pass
            if 'Condition' in line:
                condition = line.split(':')[-1].strip()
        battery_details = {
            'cycle_count': cycle_count,
            'full_charge_capacity': full_charge_capacity,
            'condition': condition
        }
        
        # Utilisateur actuel connecté
        stdin, stdout, stderr = ssh.exec_command('stat -f%Su /dev/console', timeout=10)
        current_user = stdout.read().decode().strip()
        
        ssh.close()
        return {
            'hostname': hostname if hostname else "Unknown",
            'model_info': model_info if model_info else "Unknown",
            'architecture': arch_type,
            'macos_version': macos_version if macos_version else "Unknown",
            'disk_free': disk_free,
            'ram_info': ram_info,
            'open_apps': open_apps,
            'battery_status': battery_status,
            'battery_details': battery_details,
            'current_user': current_user if current_user else "Unknown"
        }
    except paramiko.AuthenticationException as e:
        print(f"[ERROR] Erreur d'authentification SSH sur {ip}: {e}")
        print(f"[DEBUG] Vérifiez les credentials dans le fichier .env")
        return {
            'hostname': "Unknown",
            'model_info': "Unknown",
            'architecture': "Unknown",
            'macos_version': "Unknown",
            'disk_free': "Unknown",
            'ram_info': "Unknown",
            'open_apps': "Unknown",
            'battery_status': {},
            'battery_details': {},
            'current_user': "Unknown"
        }
    except paramiko.SSHException as e:
        print(f"[ERROR] Erreur SSH sur {ip}: {e}")
        return {
            'hostname': "Unknown",
            'model_info': "Unknown",
            'architecture': "Unknown",
            'macos_version': "Unknown",
            'disk_free': "Unknown",
            'ram_info': "Unknown",
            'open_apps': "Unknown",
            'battery_status': {},
            'battery_details': {},
            'current_user': "Unknown"
        }
    except socket.timeout as e:
        print(f"[ERROR] Timeout de connexion SSH sur {ip}: {e}")
        return {
            'hostname': "Unknown",
            'model_info': "Unknown",
            'architecture': "Unknown",
            'macos_version': "Unknown",
            'disk_free': "Unknown",
            'ram_info': "Unknown",
            'open_apps': "Unknown",
            'battery_status': {},
            'battery_details': {},
            'current_user': "Unknown"
        }
    except Exception as e:
        print(f"[ERROR] Erreur inattendue SSH sur {ip}: {e}")
        return {
            'hostname': "Unknown",
            'model_info': "Unknown",
            'architecture': "Unknown",
            'macos_version': "Unknown",
            'disk_free': "Unknown",
            'ram_info': "Unknown",
            'open_apps': "Unknown",
            'battery_status': {},
            'battery_details': {},
            'current_user': "Unknown"
        }

def extract_model_identifier(model_info):
    match = re.search(r'(Mac(?:BookPro)?[0-9,]+|Mac[0-9,]+)', model_info)
    if match:
        return match.group(1)
    return "Unknown"

def scan_ip(ip, ssh_credentials=None):
    """Scan a single IP address"""
    try:
        if ping(ip):
            mac = get_mac_address(ip)
            hostname = "Unknown"
            model_info = "Unknown"
            macos_version = "Unknown"
            model_identifier = "Unknown"
            taille = "Unknown"
            annee = "Unknown"
            current_user = "Unknown"
            
            # Si SSH est activé, essayer la connexion SSH
            if USE_SSH and ssh_credentials:
                # print(f"Trying to connect to {ssh_credentials['username']} with password {ssh_credentials['password']}")
                ssh_result = try_ssh_connection(ip, ssh_credentials['username'], ssh_credentials['password'])
                if isinstance(ssh_result, dict):
                    hostname = ssh_result.get('hostname', 'Unknown')
                    model_info = ssh_result.get('model_info', 'Unknown')
                    macos_version = ssh_result.get('macos_version', 'Unknown')
                    model_identifier = extract_model_identifier(model_info)
                    taille, annee = macbook_pro_models.get(model_identifier, ("Unknown", "Unknown"))
                    current_user = ssh_result.get('current_user', 'Unknown')
                else:
                    hostname = ssh_result
            
            return {
                'ip': ip,
                'mac': mac if mac else "Unknown",
                'hostname': hostname if hostname else "Unknown",
                'model_info': model_info if model_info else "Unknown",
                'architecture': ssh_result.get('architecture', 'Unknown'),
                'macos_version': macos_version if macos_version else "Unknown",
                'model_identifier': model_identifier,
                'taille': taille,
                'annee': annee,
                'disk_free': ssh_result.get('disk_free', 'Unknown'),
                'ram_info': ssh_result.get('ram_info', 'Unknown'),
                'open_apps': ssh_result.get('open_apps', 'Unknown'),
                'battery_status': ssh_result.get('battery_status', 'Unknown'),
                'battery_details': ssh_result.get('battery_details', 'Unknown'),
                'current_user': current_user
            }
    except:
        pass
    return None

def save_to_csv(results, filename):
    """Save results to CSV file and also as JSON file"""
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'IP Address', 'MAC Address', 'Hostname', 'Model Info', 'Architecture', 'macOS Version',
                'Model Identifier', 'Taille', 'Annee', 'Disk Free', 'RAM Info', 'Open Apps',
                'Battery Status', 'Battery Details', 'Current User'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for result in results:
                if result:  # Vérifier que le résultat n'est pas None
                    # Pour le CSV, convertir les dicts batterie en string lisible
                    battery_status_str = ''
                    if isinstance(result.get('battery_status'), dict):
                        battery_status_str = ', '.join(f'{k}: {v}' for k, v in result['battery_status'].items())
                    else:
                        battery_status_str = str(result.get('battery_status', 'Unknown'))
                    battery_details_str = ''
                    if isinstance(result.get('battery_details'), dict):
                        battery_details_str = ', '.join(f'{k}: {v}' for k, v in result['battery_details'].items())
                    else:
                        battery_details_str = str(result.get('battery_details', 'Unknown'))
                    writer.writerow({
                        'IP Address': result.get('ip', 'Unknown'),
                        'MAC Address': result.get('mac', 'Unknown'),
                        'Hostname': result.get('hostname', 'Unknown'),
                        'Model Info': result.get('model_info', 'Unknown'),
                        'Architecture': result.get('architecture', 'Unknown'),
                        'macOS Version': result.get('macos_version', 'Unknown'),
                        'Model Identifier': result.get('model_identifier', 'Unknown'),
                        'Taille': result.get('taille', 'Unknown'),
                        'Annee': result.get('annee', 'Unknown'),
                        'Disk Free': result.get('disk_free', 'Unknown'),
                        'RAM Info': result.get('ram_info', 'Unknown'),
                        'Open Apps': result.get('open_apps', 'Unknown'),
                        'Battery Status': battery_status_str,
                        'Battery Details': battery_details_str,
                        'Current User': result.get('current_user', 'Unknown')
                    })
        # Génération du fichier JSON
        json_filename = filename.replace('.csv', '.json')
        with open(json_filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(results, jsonfile, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde du fichier CSV/JSON: {str(e)}")

def is_smartelia_machine(hostname):
    """Vérifie si le nom d'hôte contient 'SMARTELIA' (insensible à la casse)"""
    return hostname and "SMARTELIA" in hostname.upper()

def cleanup_old_csv():
    """Supprime tous les anciens fichiers CSV"""
    try:
        for csv_file in glob.glob("smartelia_machines_*.csv"):
            os.remove(csv_file)
    except:
        pass

def main():
    print("Démarrage du scan réseau...")
    print("Scan des plages d'IP : 172.17.17.0/24 à 172.17.20.0/24")

    # Vérification des credentials SSH
    if not SSH_USERNAME or not SSH_PASSWORD:
        print("[ERROR] Credentials SSH manquants dans le fichier .env")
        print("[DEBUG] Vérifiez que SSH_USERNAME et SSH_PASSWORD sont définis")
        return
    
    print(f"[DEBUG] Utilisateur SSH: {SSH_USERNAME}")
    print(f"[DEBUG] Mot de passe SSH: {'*' * len(SSH_PASSWORD) if SSH_PASSWORD else 'Non défini'}")

    # Nettoyer les anciens fichiers CSV
    cleanup_old_csv()

    # Configuration SSH
    ssh_credentials = None
    if USE_SSH:
        ssh_credentials = {
            'username': SSH_USERNAME,
            'password': SSH_PASSWORD
        }
        # for user, password in ssh_credentials.items():
        #     print(f"Trying to connect to {user} with password {password}")

    # Liste des IPs à scanner
    ips_to_scan = []
    for x in range(18, 19):  # 17 à 20
        for y in range(75, 76):  # 1 à 255
            ips_to_scan.append(f"172.17.{x}.{y}")

    # Utiliser ThreadPoolExecutor pour scanner en parallèle avec plus de workers
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        # Créer une barre de progression
        with tqdm(total=len(ips_to_scan), desc="Scanning", unit="IP") as pbar:
            # Scanner les IPs et mettre à jour la barre de progression
            futures = {executor.submit(scan_ip, ip, ssh_credentials): ip for ip in ips_to_scan}
            for future in concurrent.futures.as_completed(futures):
                pbar.update(1)
                try:
                    result = future.result()
                    if result and is_smartelia_machine(result.get('hostname', '')):
                        results.append(result)
                except:
                    pass

    # Sauvegarder les résultats dans un fichier CSV
    if results:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"smartelia_machines_{timestamp}.csv"
        save_to_csv(results, filename)
        print(f"\nNombre de machines SMARTELIA trouvées : {len(results)}")
    else:
        print("\nAucune machine SMARTELIA trouvée")

def merge_latest_machine_data():
    """Fusionne tous les fichiers smartelia_machines_*.json et conserve la donnée la plus récente pour chaque machine."""
    import glob
    import re
    from collections import defaultdict
    
    json_files = glob.glob("smartelia_machines_*.json")
    # Associer chaque fichier à son timestamp
    file_date_pattern = re.compile(r"smartelia_machines_(\d{8}_\d{6})\\.json")
    file_dates = {}
    for f in json_files:
        m = re.search(r"smartelia_machines_(\d{8}_\d{6})\\.json", f)
        if m:
            file_dates[f] = m.group(1)
    # Trier les fichiers par date croissante
    sorted_files = sorted(file_dates.items(), key=lambda x: x[1])
    # Pour chaque hostname, garder la donnée la plus récente
    latest_data = {}
    for f, date in sorted_files:
        try:
            with open(f, 'r', encoding='utf-8') as jf:
                machines = json.load(jf)
                for machine in machines:
                    hostname = machine.get('hostname')
                    if not hostname:
                        continue
                    # On écrase si plus récent
                    latest_data[hostname] = machine
        except Exception as e:
            print(f"Erreur lors de la lecture de {f}: {e}")
    # Sauvegarder le résultat
    with open('smartelia_machines_latest.json', 'w', encoding='utf-8') as out:
        json.dump(list(latest_data.values()), out, ensure_ascii=False, indent=4)
    print(f"Fusion terminée : {len(latest_data)} machines uniques dans smartelia_machines_latest.json")

if __name__ == "__main__":
    main() 