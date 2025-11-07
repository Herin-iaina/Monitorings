#!/usr/bin/env python3
"""Host runner pour exécuter le scanner une fois (conçu pour systemd timer / launchd).

Utilisation prévue : ce script est appelé périodiquement par systemd-timer ou launchd.
Il fait :
- change le working dir vers le dossier du projet (pour écrire les JSON/CSV au bon endroit)
- nettoie les anciens fichiers JSON si > 5
- appelle `network_scanner.main()`
"""
import os
import glob
import logging
import sys

# S'assurer que le répertoire courant est le dossier du dépôt (où se trouve network_scanner.py)
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def cleanup_json_limit(max_files=5, pattern="smartelia_machines_*.json"):
    files = glob.glob(pattern)
    if len(files) <= max_files:
        return
    files_sorted = sorted(files, key=lambda f: os.path.getmtime(f))
    while len(files_sorted) > max_files:
        to_remove = files_sorted.pop(0)
        try:
            os.remove(to_remove)
            logging.info(f"Removed old json file: {to_remove}")
        except Exception:
            logging.exception(f"Failed to remove {to_remove}")


def main():
    logging.info("Host runner started: cleaning and launching network scan")
    cleanup_json_limit(5)
    try:
        # Import local module and call main
        import network_scanner
        network_scanner.main()
    except Exception:
        logging.exception("Error while running network_scanner.main()")
        return 2
    logging.info("Host runner finished successfully")
    return 0


if __name__ == '__main__':
    sys.exit(main())
