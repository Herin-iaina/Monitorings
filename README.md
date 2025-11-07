# Monitorings — Outils de scan et API de visualisation (SMARTELIA)

Ce dépôt contient des scripts Python pour scanner un réseau (détecter des Mac), récupérer des informations via SSH et exposer une API web pour visualiser les machines trouvées.

Principaux composants
- `network_scanner.py` : scanner réseau principal. Ping des IPs, tentative de connexion SSH (si activé) pour récupérer infos (hostname, modèle, batterie, disque, mémoire, etc.).
- `network_api.py` : API FastAPI qui sert une interface web et des endpoints JSON (fusionne les fichiers `smartelia_machines_*.json`).
- `runner.py` : script de démarrage utilisé en image Docker — démarre l'API (uvicorn) et exécute le scanner toutes les 10 minutes. Gère aussi le nettoyage des fichiers JSON.
- `Dockerfile` : image Docker minimale basée sur `python:3.11-slim` qui installe les dépendances et lance `runner.py`.
- `requirements.txt` : dépendances Python (fastapi, uvicorn, jinja2, python-dotenv, tqdm, paramiko).
- `templates/` : template Jinja2 (`machines_table.html`) pour l'interface web.
- `os_downloader.sh`, `os_installer.sh` : scripts utilitaires servis par l'API pour distribution/installation.

Comportement important
- Scheduler : `runner.py` lance `network_scanner.main()` toutes les 10 minutes (pause via `time.sleep(10 * 60)`). Pour changer la fréquence, éditez `runner.py`.
- Nettoyage des JSON : avant chaque scan, `runner.py` appelle `cleanup_json_limit(5)` qui supprime les fichiers `smartelia_machines_*.json` les plus anciens tant qu'il y en a plus de 5.

Prérequis
- Docker (pour exécuter l'image construite)
- (optionnel) `.env` contenant les variables d'authentification SSH si `USE_SSH` est activé :

  SSH_USERNAME=smartelia
  SSH_PASSWORD=VotreMotDePasseSSH

Comment construire l'image Docker
1. Placez-vous à la racine du projet (le dossier contenant `Dockerfile`).
2. Construisez l'image :

```bash
docker build -t networkscan:latest .
```

Lancer le conteneur
- Exemple minimal (expose l'API sur le port 8000) :

```bash
docker run -d \
  --name networkscan \
  --env-file .env \
  -p 8000:8000 \
  -v $(pwd):/app \
  networkscan:latest
```

Notes :
- Le volume `-v $(pwd):/app` est optionnel mais pratique en dev (les fichiers CSV/JSON apparaîtront sur l'hôte). En prod, vous pouvez omettre le montage pour une image immuable.
- Fournissez les variables SSH soit via `--env-file .env` soit via `--env SSH_USERNAME=... --env SSH_PASSWORD=...`.

Vérifications / debug
- Visualiser les logs :

```bash
docker logs -f networkscan
```

- Vérifier l'API :

  - Page d'accueil / interface HTML : http://localhost:8000/
  - Liste des machines en JSON : http://localhost:8000/machines
  - Endpoint pour télécharger `os_downloader.sh` : /installers/os_downloader.sh

Comment le scheduler et le nettoyage fonctionnent
- `runner.py` :
  - démarre uvicorn pour exposer `network_api:app` sur 0.0.0.0:8000
  - boucle : nettoie les fichiers JSON pour garder au plus 5 fichiers, lance `network_scanner.main()` puis attend 10 minutes

- Le nettoyage supprime les fichiers correspondant à `smartelia_machines_*.json` triés par date de modification (les plus anciens sont supprimés en premier).

Personnalisation et améliorations possibles
- Séparer l'API et le scheduler en deux conteneurs (avec `docker-compose`) : utile pour scalabilité et isoler la charge du scanner.
- Utiliser un scheduler robuste (cron dans un container distinct, systemd timer, ou un job queue comme Celery) au lieu de `time.sleep` pour des besoins avancés.
- Ajouter un `healthcheck` Docker pour s'assurer que l'API répond et redémarrer automatiquement si elle ne répond plus.
- Journalisation structurée (RotatingFileHandler) et sauvegarde externe des CSV/JSON si nécessaire.

Dépannage rapide
- Erreur pendant pip install : regardez l'erreur de compilation ; certains paquets (paramiko, cryptography) peuvent nécessiter `libssl-dev`, `build-essential`. Le `Dockerfile` installe déjà `libssl-dev` et `libffi-dev` ; si un paquet demande Rust, installez `rustc`/`cargo` ou utilisez une image multistage.
- Si l'API ne démarre pas, vérifiez que `network_api.py` définit `app` (FastAPI) et que `uvicorn` est installé (présent dans `requirements.txt`).
- Si aucun scan ne se lance, vérifiez les logs du conteneur ; `runner.py` écrit des messages au démarrage et avant/après chaque scan.

Sécurité
- Évitez de committer des secrets dans le dépôt. Le fichier `.env` est listé dans `.gitignore`.
- En prod, préférez des secrets fournis via un mécanisme de secret manager (Docker secrets, Kubernetes secrets, Vault, etc.).

Fichiers clés
- `network_scanner.py` — scanner réseau et collecte d'infos
- `network_api.py` — FastAPI et UI
- `runner.py` — démarrage API + scheduler
- `Dockerfile` — construction d'image
- `requirements.txt` — dépendances Python

Besoin d'aide ?
- Si vous voulez que je :
  - sépare l'API et le scheduler en deux services `docker-compose`,
  - ajoute un healthcheck et un `docker-compose.yml`,
  - modifie la fréquence du scan pour la rendre configurable via variable d'environnement,
alors dites-le et je ferai les modifications.

Executer le scanner sur l'hôte (recommandé pour le scan réseau)
---------------------------------------------------------
Si vous voulez que le scanner fasse des pings/arp sur votre réseau local, il est préférable de l'exécuter sur l'hôte (ou sur une machine Linux) plutôt que dans un conteneur Docker sur macOS — Docker Desktop sur macOS n'expose pas toujours les interfaces réseau locales comme un conteneur Linux natif.

Deux options fournies dans ce dépôt :

1) systemd (Linux)

 - Fichiers exemples : `packaging/systemd/networkscanner.service` et `packaging/systemd/networkscanner.timer`.
 - Installation (exécuter en tant que root ou avec sudo) :

```bash
# Copier les fichiers vers /etc/systemd/system
sudo cp packaging/systemd/networkscanner.service /etc/systemd/system/
sudo cp packaging/systemd/networkscanner.timer /etc/systemd/system/

# Editez `/etc/systemd/system/networkscanner.service` et remplacez `/path/to/networkscan` par le chemin absolu vers le dossier du projet
# (ex: /home/ubuntu/networkscan ou /opt/networkscan). Assurez-vous que ExecStart utilise le bon interpréteur python (/usr/bin/python3 ou /usr/bin/env python3).

# Recharger systemd, activer et démarrer le timer :
sudo systemctl daemon-reload
sudo systemctl enable --now networkscanner.timer

# Vérifier le statut
sudo systemctl status networkscanner.timer
sudo journalctl -u networkscanner.service -f
```

Le timer déclenchera le service toutes les 10 minutes. Le service exécute `host_runner.py` (qui appelle `network_scanner.main()` une fois et quitte). Les fichiers `smartelia_machines_*.json` seront écrits dans le répertoire du projet.

2) launchd (macOS)

 - Fichier exemple : `packaging/launchd/com.smartelia.networkscanner.plist`.
 - Installation basique :

```bash
# Copier le plist dans ~/Library/LaunchAgents pour un utilisateur ou /Library/LaunchDaemons pour tous les utilisateurs (requiert sudo)
cp packaging/launchd/com.smartelia.networkscanner.plist ~/Library/LaunchAgents/

# Éditez le fichier plist et remplacez `/path/to/networkscan` par le chemin absolu vers le dossier du projet

# Charger le daemon (pour l'utilisateur courant)
launchctl load ~/Library/LaunchAgents/com.smartelia.networkscanner.plist

# Vérifier les logs
tail -f /var/log/networkscanner.out.log /var/log/networkscanner.err.log
```

Notes importantes :
- Dans les deux cas, éditez les chemins (`/path/to/networkscan`) pour pointer vers le répertoire réel du dépôt sur votre hôte.
- Assurez-vous que l'utilisateur qui exécute le service a accès au répertoire (permissions d'écriture pour produire les JSON/CSV) et que Python 3 est installé.
- Sur macOS, `StartInterval` de launchd exécute périodiquement le script (ici toutes les 600s). Vous pouvez aussi préférer exécuter `host_runner.py` via cron si vous le souhaitez.

Fichiers ajoutés pour l'exécution hôte
-------------------------------------
- `host_runner.py` : script qui nettoie les anciens JSON (garde 5 max) et exécute `network_scanner.main()` une fois.
- `packaging/systemd/networkscanner.service` et `packaging/systemd/networkscanner.timer` : exemples pour Linux/systemd.
- `packaging/launchd/com.smartelia.networkscanner.plist` : exemple pour macOS/launchd.

Si vous voulez que je :
- adapte le service pour exécuter `runner.py` (API + scanner) sur l'hôte au lieu de `network_scanner.py`, ou
- crée un petit script d'installation qui met en place automatiquement les unités systemd/launchd (avec vérification des chemins),
je peux l'ajouter.

---
Fichier généré automatiquement lors de la demande d'ajout du README.
