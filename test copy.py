#!/usr/bin/env python3
import socket
import threading
import ipaddress
import subprocess
import platform
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
    """Tente d'obtenir le nom d'hôte d'une IP"""
    try:
        hostname = socket.gethostbyaddr(str(ip))[0]
        return hostname
    except Exception:
        return "Inconnu"

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
            hostname = get_hostname(ip_str)
            
            # Test des ports
            open_ports = []
            for port in scan_ports:
                if scan_port(ip_str, port):
                    open_ports.append(port)
            
            host_info = {
                'ip': ip_str,
                'hostname': hostname,
                'open_ports': open_ports,
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
                print(f"✓ {result['ip']} ({result['hostname']}) - Ports ouverts: {result['open_ports']}")
    
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
        print(f"   Statut: {host['status']}")
        if host['open_ports']:
            print(f"   Ports ouverts: {', '.join(map(str, host['open_ports']))}")
        else:
            print("   Aucun port ouvert détecté")

# Exemple d'utilisation
if __name__ == "__main__":
    print("🔍 Scanner de réseau local")
    print("=" * 30)
    
    # Option 1: Scan automatique du réseau local
    hosts = scan_network("172.17.19.0/22")
    
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
                    f.write(f"Ports ouverts: {host['open_ports']}\n")
                    f.write("-" * 20 + "\n")
            print(f"\n💾 Résultats sauvegardés dans 'network_scan_results.txt'")
        except Exception as e:
            print(f"Erreur lors de la sauvegarde: {e}")