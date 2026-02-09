#!/usr/bin/env python3
"""
Module de notification par email pour les alertes de stockage des Mac SMARTELIA
"""
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from jinja2 import Template
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration Gmail
GMAIL_USER = os.getenv("GMAIL_USER")  # Votre adresse Gmail
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")  # Mot de passe d'application Gmail
ALERT_RECIPIENTS = os.getenv("ALERT_RECIPIENTS", "").split(",")  # Liste des destinataires séparés par des virgules

# Seuils de stockage (en Go)
CRITICAL_THRESHOLD = 15  # Seuil critique pour déclencher une alerte
WARNING_THRESHOLD = 30   # Seuil d'avertissement pour le récapitulatif


def parse_disk_space(disk_free_str):
    """
    Convertit une chaîne d'espace disque (ex: '12Gi', '450Mi', '1.2Ti') en Go (float)
    Retourne None si le format n'est pas reconnu
    """
    if not disk_free_str or disk_free_str == "Unknown":
        return None
    
    # Pattern pour extraire le nombre et l'unité
    match = re.match(r'([\d.]+)\s*([KMGT]i?)', disk_free_str, re.IGNORECASE)
    if not match:
        return None
    
    value = float(match.group(1))
    unit = match.group(2).upper()
    
    # Conversion en Go
    conversions = {
        'K': value / (1024 * 1024),      # Ko -> Go
        'KI': value / (1024 * 1024),
        'M': value / 1024,                # Mo -> Go
        'MI': value / 1024,
        'G': value,                       # Go -> Go
        'GI': value,
        'T': value * 1024,                # To -> Go
        'TI': value * 1024
    }
    
    return conversions.get(unit, None)


def get_storage_class(disk_space_gb):
    """Retourne la classe CSS en fonction de l'espace disque"""
    if disk_space_gb is None:
        return ""
    if disk_space_gb < CRITICAL_THRESHOLD:
        return "storage-critical"
    elif disk_space_gb < WARNING_THRESHOLD:
        return "storage-warning"
    return ""


def prepare_email_data(machines):
    """
    Prépare les données pour le template email
    
    Args:
        machines: Liste des machines du scan réseau
    
    Returns:
        dict: Données formatées pour le template, ou None si aucune alerte
    """
    low_storage_machines = []
    full_battery_still_charging = []
    low_battery_machines = []
    trigger_machine = None
    
    for machine in machines:
        disk_free_str = machine.get('disk_free', 'Unknown')
        disk_space_gb = parse_disk_space(disk_free_str)
        
        if disk_space_gb is None:
            continue
        
        # Récupération des infos batterie
        battery_status = machine.get('battery_status', {})
        battery_percent = battery_status.get('percent', 'N/A')
        drawing_from = battery_status.get('drawing_from', '')
        
        # La machine est sur secteur si drawing_from contient "AC Power"
        is_on_ac_power = 'AC Power' in drawing_from
        
        # Formatage pour l'affichage
        battery_display = f"{battery_percent}%" if battery_percent != 'N/A' else 'N/A'
        battery_raw = battery_percent if isinstance(battery_percent, int) else None
        
        machine_data = {
            'hostname': machine.get('hostname', 'Unknown'),
            'ip': machine.get('ip', 'Unknown'),
            'disk_free': disk_free_str,
            'disk_space_gb': disk_space_gb,
            'battery_percent': battery_display,
            'battery_raw': battery_raw,
            'is_on_ac_power': is_on_ac_power,
            'drawing_from': drawing_from,
            'storage_class': get_storage_class(disk_space_gb),
            'current_user': machine.get('current_user', 'Unknown')
        }
        
        # Machine déclenchant l'alerte (première machine sous le seuil critique)
        if disk_space_gb <= CRITICAL_THRESHOLD and trigger_machine is None:
            trigger_machine = machine_data
        
        # Machines avec moins de 30 Go
        if disk_space_gb < WARNING_THRESHOLD:
            low_storage_machines.append(machine_data)
        
        # Machines à 100% de batterie mais toujours branchées sur secteur (AC Power)
        if battery_raw == 100 and is_on_ac_power:
            full_battery_still_charging.append(machine_data)
        
        # Machines avec batterie < 30%
        if battery_raw is not None and battery_raw < 30:
            low_battery_machines.append(machine_data)
    
    # Si aucune machine critique, pas d'alerte
    if trigger_machine is None:
        return None
    
    # Tri par espace disponible (croissant)
    low_storage_machines.sort(key=lambda x: x['disk_space_gb'])
    # Tri par niveau de batterie (décroissant pour full_battery)
    full_battery_still_charging.sort(key=lambda x: x['hostname'])
    # Tri par niveau de batterie (croissant pour low_battery)
    low_battery_machines.sort(key=lambda x: x['battery_raw'] if x['battery_raw'] is not None else 0)
    
    return {
        'trigger_hostname': trigger_machine['hostname'],
        'trigger_storage': trigger_machine['disk_free'],
        'low_storage_machines': low_storage_machines,
        'full_battery_still_charging': full_battery_still_charging,
        'low_battery_machines': low_battery_machines,
        'timestamp': datetime.now().strftime("%d %B %Y, %H:%M:%S UTC")
    }


def send_email_alert(email_data):
    """
    Envoie un email d'alerte via Gmail
    
    Args:
        email_data: Dictionnaire contenant les données pour le template
    
    Returns:
        bool: True si l'email a été envoyé avec succès, False sinon
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("❌ Erreur : GMAIL_USER et GMAIL_APP_PASSWORD doivent être définis dans .env")
        return False
    
    if not ALERT_RECIPIENTS or ALERT_RECIPIENTS == ['']:
        print("❌ Erreur : ALERT_RECIPIENTS doit être défini dans .env")
        return False
    
    # Charger le template HTML
    template_path = os.path.join(os.path.dirname(__file__), 'email_template.html')
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
    except FileNotFoundError:
        print(f"❌ Erreur : Template email introuvable à {template_path}")
        return False
    
    # Rendre le template avec les données
    template = Template(template_content)
    html_content = template.render(**email_data)
    
    # Créer le message email
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"⚠️ ALERTE STOCKAGE - {email_data['trigger_hostname']} critique"
    msg['From'] = GMAIL_USER
    msg['To'] = ', '.join(ALERT_RECIPIENTS)
    
    # Attacher le contenu HTML
    html_part = MIMEText(html_content, 'html', 'utf-8')
    msg.attach(html_part)
    
    # Envoyer l'email via Gmail SMTP
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        
        print(f"✅ Email d'alerte envoyé avec succès à {', '.join(ALERT_RECIPIENTS)}")
        return True
    
    except smtplib.SMTPAuthenticationError:
        print("❌ Erreur d'authentification Gmail. Vérifiez GMAIL_USER et GMAIL_APP_PASSWORD")
        return False
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi de l'email : {str(e)}")
        return False


def check_and_notify(machines):
    """
    Vérifie les machines et envoie une notification si nécessaire
    
    Args:
        machines: Liste des machines du scan réseau
    
    Returns:
        bool: True si une notification a été envoyée, False sinon
    """
    email_data = prepare_email_data(machines)
    
    if email_data is None:
        print("ℹ️  Aucune machine en alerte critique de stockage")
        return False
    
    print(f"⚠️  Alerte détectée : {email_data['trigger_hostname']} avec {email_data['trigger_storage']}")
    print(f"📊 {len(email_data['low_storage_machines'])} machine(s) avec <30 Go")
    print(f"� {len(email_data['full_battery_still_charging'])} machine(s) à 100% mais toujours branchée(s)")
    print(f"🪫 {len(email_data['low_battery_machines'])} machine(s) avec batterie <30%")
    
    return send_email_alert(email_data)


if __name__ == "__main__":
    # Test avec des données fictives
    test_machines = [
        {
            'hostname': 'MacBook-SMARTELIA-042',
            'ip': '192.168.1.42',
            'disk_free': '12Gi',
            'battery_status': {'percent': 45, 'drawing_from': 'Battery Power'},
            'current_user': 'jdupont'
        },
        {
            'hostname': 'iMac-PRO-015',
            'ip': '192.168.1.15',
            'disk_free': '28Gi',
            'battery_status': {'percent': 88, 'drawing_from': 'AC Power'},
            'current_user': 'mmartin'
        },
        {
            'hostname': 'MacMini-DEV-003',
            'ip': '192.168.1.3',
            'disk_free': '14Gi',
            'battery_status': {'percent': 100, 'drawing_from': 'AC Power'},
            'current_user': 'admin'
        },
        {
            'hostname': 'MacBook-AIR-021',
            'ip': '192.168.1.21',
            'disk_free': '2Gi',
            'battery_status': {'percent': 25, 'drawing_from': 'Battery Power'},
            'current_user': 'ldurand'
        },
        {
            'hostname': 'MacBook-PRO-055',
            'ip': '192.168.1.55',
            'disk_free': '120Gi',
            'battery_status': {'percent': 100, 'drawing_from': 'AC Power'},
            'current_user': 'smartelia'
        },
        {
            'hostname': 'MacBook-AIR-033',
            'ip': '192.168.1.33',
            'disk_free': '85Gi',
            'battery_status': {'percent': 18, 'drawing_from': 'AC Power'},
            'current_user': 'pbernard'
        }
    ]
    
    print("🧪 Test du système de notification...")
    check_and_notify(test_machines)
