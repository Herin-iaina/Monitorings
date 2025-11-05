#!/usr/bin/env python3
"""Runner simple pour Docker :
- démarre l'API FastAPI (uvicorn) en sous-processus
- exécute network_scanner.main() toutes les 10 minutes
- nettoie les anciens fichiers JSON si leur nombre dépasse la limite
"""
import glob
import os
import subprocess
import time
import logging
from datetime import datetime

import network_scanner

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def cleanup_json_limit(max_files=5, pattern="smartelia_machines_*.json"):
    files = glob.glob(pattern)
    if len(files) <= max_files:
        return
    # trier par date de modification (ancien -> récent)
    files_sorted = sorted(files, key=lambda f: os.path.getmtime(f))
    while len(files_sorted) > max_files:
        to_remove = files_sorted.pop(0)
        try:
            os.remove(to_remove)
            logging.info(f"Removed old json file: {to_remove}")
        except Exception as e:
            logging.exception(f"Failed to remove {to_remove}: {e}")


def start_api():
    cmd = ["uvicorn", "network_api:app", "--host", "0.0.0.0", "--port", "8000"]
    proc = subprocess.Popen(cmd)
    logging.info(f"Started uvicorn (pid={proc.pid})")
    return proc


def main_loop():
    api_proc = start_api()
    try:
        while True:
            logging.info("Starting scheduled network scan")
            # Nettoyage avant scan pour s'assurer de garder la taille
            cleanup_json_limit(5)
            try:
                # Appeler la fonction main du scanner (cela peut prendre du temps)
                network_scanner.main()
            except Exception:
                logging.exception("Error while running network_scanner.main()")

            logging.info("Scan finished. Sleeping 10 minutes")
            time.sleep(10 * 60)
    finally:
        try:
            api_proc.terminate()
            logging.info("Terminated uvicorn process")
        except Exception:
            pass


if __name__ == "__main__":
    main_loop()
