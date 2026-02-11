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
import json
import logging
from dotenv import load_dotenv
import email_notifier

# Configuration Logging
logging.basicConfig(
    filename='network_scanner.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Configuration SSH
USE_SSH = True  # Mettre à False pour désactiver SSH

macbook_pro_models = {
    "Mac16,8": ("14 pouces", 2024),
    "Mac16,7": ("16 pouces", 2024),
    "Mac16,6": ("14 pouces", 2024),
    "Mac16,5": ("16 pouces", 2024),
    "Mac16,1": ("14 pouces", 2024),

    "Mac15,11": ("16 pouces", 2023),
    "Mac15,10": ("14 pouces", 2023),
    "Mac15,9":  ("16 pouces", 2023),
    "Mac15,8":  ("14 pouces", 2023),
    "Mac15,7":  ("16 pouces", 2023),
    "Mac15,6":  ("14 pouces", 2023),
    "Mac15,3":  ("14 pouces", 2023),
    "Mac14,10":("16 pouces", 2023),
    "Mac14,9": ("14 pouces", 2023),
    "Mac14,6": ("16 pouces", 2023),
    "Mac14,5": ("14 pouces", 2023),

    "Mac14,7": ("13 pouces", 2022),

    "MacBookPro18,4":("14 pouces", 2021),
    "MacBookPro18,3":("14 pouces", 2021),
    "MacBookPro18,2":("16 pouces", 2021),
    "MacBookPro18,1":("16 pouces", 2021),

    "MacBookPro17,1":("13 pouces", 2020),
    "MacBookPro16,3":("13 pouces", 2020),
    "MacBookPro16,2":("13 pouces", 2020),

    "MacBookPro16,4":("16 pouces", 2019),
    "MacBookPro16,1":("16 pouces", 2019),

    "MacBookPro15,2":("13 pouces", 2018),
    "MacBookPro15,1":("15 pouces", 2018),

    "MacBookPro14,3":("15 pouces", 2017),
    "MacBookPro14,2":("13 pouces", 2017),
    "MacBookPro14,1":("13 pouces", 2017),

    "MacBookPro13,3":("15 pouces", 2016),
    "MacBookPro13,2":("13 pouces", 2016),
    "MacBookPro13,1":("13 pouces", 2016),

    "MacBookPro12,1":("13 pouces", 2015),
    "MacBookPro11,3":("15 pouces", 2015),
    "MacBookPro11,2":("15 pouces", 2015),
    "MacBookPro11,1":("13 pouces", 2015),
}


load_dotenv()
SSH_USERNAME = os.getenv("SSH_USERNAME")
SSH_PASSWORD = os.getenv("SSH_PASSWORD")

def ping(ip):
    """Ping une adresse IP et retourne True si elle répond"""
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    timeout = '-W' if platform.system().lower() != 'windows' else '-w'
    timeout_value = '1' if platform.system().lower() != 'windows' else '1000'
    command = ['ping', param, '1', timeout, timeout_value, ip]
    return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0

def get_mac_address(ip):
    """Récupère l'adresse MAC via la commande arp"""
    try:
        if platform.system().lower() == 'windows':
            output = subprocess.check_output(f'arp -a {ip}', shell=True).decode()
        else:
            output = subprocess.check_output(f'arp -n {ip}', shell=True).decode()
        mac_pattern = r'([0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2})'
        match = re.search(mac_pattern, output)
        if match:
            return match.group(1)
    except:
        pass
    return "Unknown"

def try_ssh_connection(ip, username, password):
    """Tente une connexion SSH et récupère les infos d'état de la machine avec timeouts et gestion des erreurs"""
    ssh = None
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Ajout de timeouts explicites pour la connexion
        ssh.connect(ip, username=username, password=password, timeout=5, banner_timeout=5, auth_timeout=5)

        def exec_with_timeout(command, timeout=10):
            try:
                stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
                stdout.channel.settimeout(timeout)
                # Ensure we read with a timeout
                return stdout.read().decode().strip()
            except Exception:
                return ""

        hostname = exec_with_timeout('hostname')
        
        model_info = exec_with_timeout('system_profiler SPHardwareDataType | grep "Model Name\\|Model Identifier"').replace('\n', ' ').strip()
        
        macos_version = exec_with_timeout('sw_vers -productVersion')
        
        disk_free = exec_with_timeout('df -h / | awk \'NR==2 {print $4}\'')

        ram_info = exec_with_timeout('top -l 1 | grep PhysMem | awk \'{print $2" used, "$6" free"}\'')

        open_apps = exec_with_timeout('osascript -e \'tell application "System Events" to get name of every process where background only is false\'')

        battery_status_raw = exec_with_timeout('pmset -g batt')
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
        drawing_from_match = re.search(r"Now drawing from '([^']+)'", battery_status_raw)
        if drawing_from_match:
            drawing_from = drawing_from_match.group(1)
        battery_status = {
            'percent': percent,
            'power_plugged': power_plugged,
            'time_left': time_left,
            'drawing_from': drawing_from
        }

        battery_profiler = exec_with_timeout('system_profiler SPPowerDataType')
        cycle_count = None
        max_capacity = None
        condition = None
        for line in battery_profiler.splitlines():
            if 'Cycle Count' in line:
                try:
                    cycle_count = int(line.split(':')[-1].strip())
                except:
                    pass
            if 'Condition' in line:
                condition = line.split(':')[-1].strip()
        
        # Récupérer la capacité maximale avec la commande demandée
        max_capacity_str = exec_with_timeout("system_profiler SPPowerDataType | awk -F': ' '/Maximum Capacity/ {gsub(/[^0-9]/, \"\", $2); print $2}'")
        try:
            max_capacity = int(max_capacity_str) if max_capacity_str else None
        except:
            max_capacity = None
        battery_details = {
            'cycle_count': cycle_count,
            'max_capacity': max_capacity,
            'condition': condition
        }
        
        current_user = exec_with_timeout('stat -f%Su /dev/console')
        
        return {
            'hostname': hostname if hostname else "Unknown",
            'model_info': model_info if model_info else "Unknown",
            'macos_version': macos_version if macos_version else "Unknown",
            'disk_free': disk_free if disk_free else "Unknown",
            'ram_info': ram_info if ram_info else "Unknown",
            'open_apps': open_apps if open_apps else "Unknown",
            'battery_status': battery_status,
            'battery_details': battery_details,
            'current_user': current_user if current_user else "Unknown"
        }
    except Exception as e:
        logging.error(f"Connection failed for {ip}: {e}")
        return {
            'hostname': "Unknown",
            'model_info': "Unknown",
            'macos_version': "Unknown",
            'disk_free': "Unknown",
            'ram_info': "Unknown",
            'open_apps': "Unknown",
            'battery_status': {},
            'battery_details': {},
            'current_user': "Unknown"
        }
    finally:
        if ssh:
            ssh.close()

def extract_model_identifier(model_info):
    match = re.search(r'(Mac(?:BookPro)?[0-9,]+|Mac[0-9,]+)', model_info)
    if match:
        return match.group(1)
    return "Unknown"

def scan_ip(ip, ssh_credentials=None):
    """Scan une adresse IP et retourne les infos d'état"""
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
            ssh_result = {}
            if USE_SSH and ssh_credentials:
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
                'macos_version': macos_version if macos_version else "Unknown",
                'model_identifier': model_identifier,
                'taille': taille,
                'annee': annee,
                'disk_free': ssh_result.get('disk_free', 'Unknown'),
                'ram_info': ssh_result.get('ram_info', 'Unknown'),
                'open_apps': ssh_result.get('open_apps', 'Unknown'),
                'battery_status': ssh_result.get('battery_status', {}),
                'battery_details': ssh_result.get('battery_details', {}),
                'current_user': current_user
            }
    except:
        pass
    return None

def save_to_csv(results, filename):
    """Sauvegarde les résultats dans un fichier CSV et JSON"""
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'IP Address', 'MAC Address', 'Hostname', 'Model Info', 'macOS Version',
                'Model Identifier', 'Taille', 'Annee', 'Disk Free', 'RAM Info', 'Open Apps',
                'Battery Status', 'Battery Details', 'Current User'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for result in results:
                if result:
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
        import glob
        for csv_file in glob.glob("smartelia_machines_*.csv"):
            os.remove(csv_file)
    except:
        pass

def merge_latest_machine_data():
    """Fusionne tous les fichiers smartelia_machines_*.json et conserve la donnée la plus récente pour chaque machine."""
    import glob
    import re
    json_files = glob.glob("smartelia_machines_*.json")
    file_dates = {}
    for f in json_files:
        m = re.search(r"smartelia_machines_(\d{8}_\d{6})\.json", f)
        if m:
            file_dates[f] = m.group(1)
    sorted_files = sorted(file_dates.items(), key=lambda x: x[1])
    latest_data = {}
    for f, date in sorted_files:
        try:
            with open(f, 'r', encoding='utf-8') as jf:
                machines = json.load(jf)
                for machine in machines:
                    hostname = machine.get('hostname')
                    if not hostname:
                        continue
                    latest_data[hostname] = machine
        except Exception as e:
            print(f"Erreur lors de la lecture de {f}: {e}")
    with open('smartelia_machines_latest.json', 'w', encoding='utf-8') as out:
        json.dump(list(latest_data.values()), out, ensure_ascii=False, indent=4)
    print(f"Fusion terminée : {len(latest_data)} machines uniques dans smartelia_machines_latest.json")

def main():
    print("Démarrage du scan réseau...")
    print("Scan des plages d'IP : 172.17.17.0/24 à 172.17.20.0/24")

    cleanup_old_csv()

    ssh_credentials = None
    if USE_SSH:
        ssh_credentials = {
            'username': SSH_USERNAME,
            'password': SSH_PASSWORD
        }

    ips_to_scan = []
    for x in range(17, 21):
        for y in range(1, 256):
            ips_to_scan.append(f"172.17.{x}.{y}")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        with tqdm(total=len(ips_to_scan), desc="Scanning", unit="IP") as pbar:
            futures = {executor.submit(scan_ip, ip, ssh_credentials): ip for ip in ips_to_scan}
            try:
                for future in concurrent.futures.as_completed(futures, timeout=600): # 10 minutes max scan time
                    pbar.update(1)
                    try:
                        result = future.result()
                        if result and is_smartelia_machine(result.get('hostname', '')):
                            results.append(result)
                    except:
                        pass
            except concurrent.futures.TimeoutError:
                print("\nScan global timeout reached. Stopping remaining tasks.")
                executor.shutdown(wait=False, cancel_futures=True)

    if results:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"smartelia_machines_{timestamp}.csv"
        save_to_csv(results, filename)
        print(f"\nNombre de machines SMARTELIA trouvées : {len(results)}")
        
        # Vérifier et envoyer des notifications d'alerte
        print("\n🔔 Vérification des alertes...")
        email_notifier.check_and_notify(results)
    else:
        print("\nAucune machine SMARTELIA trouvée")

if __name__ == "__main__":
    main() 