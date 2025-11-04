#!/usr/bin/env python3
import socket
import threading
import ipaddress
import subprocess
import platform
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_local_ip():
    """Obtient l'adresse IP locale de la machine"""
    try:
        # Connexion vers une adresse externe pour déterminer l'IP locale
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"

def ping_host(ip):
    """Teste si une adresse IP répond au ping"""
    param = "-n" if platform.system().lower() == "windows" else "-c"
    
    try:
        result = subprocess.run(
            ["ping", param, "1", str(ip)], 
            capture_output=True, 
            text=True, 
            timeout=3
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False

def scan_port(ip, port):
    """Teste si un port spécifique est ouvert sur une IP"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((str(ip), port))
        sock.close()
        return result == 0
    except Exception:
        return False

def get_hostname(ip):
    """Tente d'obtenir le nom d'hôte d'une IP avec plusieurs méthodes"""
    ip_str = str(ip)
    
    # Méthode 1: Résolution DNS inverse
    try:
        hostname = socket.gethostbyaddr(ip_str)[0]
        if hostname and hostname != ip_str:
            return hostname
    except Exception:
        pass
    
    # Méthode 2: Utilisation de nslookup/dig
    try:
        if platform.system().lower() == "windows":
            result = subprocess.run(
                ["nslookup", ip_str], 
                capture_output=True, 
                text=True, 
                timeout=3
            )
            if result.returncode == 0:
                # Recherche du nom dans la sortie nslookup
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'Name:' in line:
                        name = line.split('Name:')[1].strip()
                        if name:
                            return name
        else:
            # Linux/macOS - utilise dig ou host
            result = subprocess.run(
                ["dig", "-x", ip_str, "+short"], 
                capture_output=True, 
                text=True, 
                timeout=3
            )
            if result.returncode == 0 and result.stdout.strip():
                hostname = result.stdout.strip().rstrip('.')
                if hostname:
                    return hostname
    except Exception:
        pass
    
    # Méthode 3: Utilisation de nbtscan (Windows) ou avahi-resolve (Linux)
    try:
        if platform.system().lower() == "windows":
            result = subprocess.run(
                ["nbtstat", "-A", ip_str], 
                capture_output=True, 
                text=True, 
                timeout=3
            )
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if '<00>' in line and 'UNIQUE' in line:
                        parts = line.split()
                        if parts:
                            return parts[0].strip()
        else:
            # Tentative avec avahi-resolve sur Linux
            result = subprocess.run(
                ["avahi-resolve", "-a", ip_str], 
                capture_output=True, 
                text=True, 
                timeout=3
            )
            if result.returncode == 0 and result.stdout.strip():
                hostname = result.stdout.strip().split('\t')[1] if '\t' in result.stdout else None
                if hostname:
                    return hostname
    except Exception:
        pass
    
    # Méthode 4: Scan NetBIOS (pour Windows)
    try:
        if platform.system().lower() == "windows":
            result = subprocess.run(
                ["ping", "-a", "-n", "1", ip_str], 
                capture_output=True, 
                text=True, 
                timeout=3
            )
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'Pinging' in line and '[' in line:
                        # Extrait le nom d'hôte de "Pinging hostname [IP]"
                        match = re.search(r'Pinging\s+(\S+)\s+\[', line)
                        if match:
                            hostname = match.group(1)
                            if hostname != ip_str:
                                return hostname
    except Exception:
        pass
    
    return "Nom inconnu"

def get_device_info(ip):
    """Tente d'obtenir des informations supplémentaires sur le périphérique"""
    info = {}
    ip_str = str(ip)
    
    # Tentative d'identification du système via les ports ouverts
    common_ports = {
        22: "SSH (Linux/Unix/macOS)",
        23: "Telnet",
        25: "SMTP",
        53: "DNS",
        80: "HTTP",
        135: "RPC (Windows)",
        139: "NetBIOS (Windows)",
        443: "HTTPS",
        445: "SMB (Windows)",
        993: "IMAPS",
        995: "POP3S",
        3389: "RDP (Windows)",
        5353: "mDNS (Apple/Avahi)"
    }
    
    # Test rapide de quelques ports caractéristiques
    test_ports = [22, 135, 139, 445, 3389, 5353]
    open_ports = []
    
    for port in test_ports:
        if scan_port(ip_str, port):
            open_ports.append(port)
    
    # Déduction du type de système
    if 135 in open_ports or 139 in open_ports or 445 in open_ports:
        info['os_guess'] = "Windows"
    elif 22 in open_ports:
        info['os_guess'] = "Linux/Unix/macOS"
    elif 5353 in open_ports:
        info['os_guess'] = "Apple/mDNS"
    else:
        info['os_guess'] = "Inconnu"
    
    return info

def scan_network(network_range=None, max_threads=50, scan_ports=None):
    """
    Scanne le réseau local pour détecter les machines connectées
    
    Args:
        network_range: Plage réseau à scanner (ex: '192.168.1.0/24')
        max_threads: Nombre maximum de threads simultanés
        scan_ports: Liste des ports à tester (ex: [22, 80, 443])
    
    Returns:
        Liste des machines détectées avec leurs informations
    """
    
    if network_range is None:
        # Détermine automatiquement la plage réseau
        local_ip = get_local_ip()
        # Assume un réseau /24 (255.255.255.0)
        network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
    else:
        network = ipaddress.IPv4Network(network_range, strict=False)
    
    if scan_ports is None:
        scan_ports = [22, 80, 443, 21, 23, 25, 53, 110, 993, 995]  # Ports communs
    
    print(f"Scan du réseau : {network}")
    print(f"Nombre d'adresses à tester : {network.num_addresses}")
    print("-" * 50)
    
    active_hosts = []
    
    # Fonction pour scanner une IP
    def scan_ip(ip):
        ip_str = str(ip)
        
        # Test de ping
        if ping_host(ip_str):
            print(f"⏳ Analyse de {ip_str}...")
            
            hostname = get_hostname(ip_str)
            device_info = get_device_info(ip_str)
            
            # Test des ports
            open_ports = []
            for port in scan_ports:
                if scan_port(ip_str, port):
                    open_ports.append(port)
            
            host_info = {
                'ip': ip_str,
                'hostname': hostname,
                'open_ports': open_ports,
                'os_guess': device_info.get('os_guess', 'Inconnu'),
                'status': 'Actif'
            }
            
            return host_info
        
        return None
    
    # Scan avec threads
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        # Soumet toutes les tâches
        future_to_ip = {executor.submit(scan_ip, ip): ip for ip in network.hosts()}
        
        # Collecte les résultats
        for future in as_completed(future_to_ip):
            result = future.result()
            if result:
                active_hosts.append(result)
                ports_str = ', '.join(map(str, result['open_ports'])) if result['open_ports'] else 'Aucun'
                print(f"✅ {result['ip']} | {result['hostname']} | {result['os_guess']} | Ports: {ports_str}")
    
    return active_hosts

def display_results(hosts):
    """Affiche les résultats du scan de manière formatée"""
    if not hosts:
        print("Aucune machine détectée sur le réseau.")
        return
    
    print("\n" + "="*70)
    print(f"RÉSULTATS DU SCAN - {len(hosts)} machine(s) détectée(s)")
    print("="*70)
    
    for host in hosts:
        print(f"\n🖥️  IP: {host['ip']}")
        print(f"   Nom d'hôte: {host['hostname']}")
        print(f"   Système probable: {host['os_guess']}")
        print(f"   Statut: {host['status']}")
        if host['open_ports']:
            ports_detail = []
            for port in host['open_ports']:
                service = {
                    22: "SSH", 80: "HTTP", 443: "HTTPS", 
                    135: "RPC", 139: "NetBIOS", 445: "SMB",
                    3389: "RDP", 5353: "mDNS"
                }.get(port, "Inconnu")
                ports_detail.append(f"{port} ({service})")
            print(f"   Ports ouverts: {', '.join(ports_detail)}")
        else:
            print("   Aucun port ouvert détecté")

# Exemple d'utilisation
if __name__ == "__main__":
    print("🔍 Scanner de réseau local")
    print("=" * 30)
    
    # Option 1: Scan automatique du réseau local
    hosts = scan_network("172.17.19.1/22")
    
    # Option 2: Scan d'une plage spécifique
    # hosts = scan_network("192.168.1.0/24")
    
    # Option 3: Scan avec ports personnalisés
    # hosts = scan_network(scan_ports=[22, 80, 443, 8080])
    
    # Affichage des résultats
    display_results(hosts)
    
    # Sauvegarde optionnelle dans un fichier
    if hosts:
        try:
            with open("network_scan_results.txt", "w", encoding="utf-8") as f:
                f.write("Résultats du scan réseau\n")
                f.write("=" * 30 + "\n\n")
                for host in hosts:
                    f.write(f"IP: {host['ip']}\n")
                    f.write(f"Hostname: {host['hostname']}\n")
                    f.write(f"Système probable: {host['os_guess']}\n")
                    f.write(f"Ports ouverts: {host['open_ports']}\n")
                    f.write("-" * 20 + "\n")
            print(f"\n💾 Résultats sauvegardés dans 'network_scan_results.txt'")
        except Exception as e:
            print(f"Erreur lors de la sauvegarde: {e}")