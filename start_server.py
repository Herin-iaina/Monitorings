#!/usr/bin/env python3
"""
Script de démarrage du serveur FastAPI pour l'API de visualisation des machines SMARTELIA
"""

import uvicorn
from network_api import app

if __name__ == "__main__":
    print("🚀 Démarrage du serveur FastAPI...")
    print("📡 Le serveur sera accessible sur toutes les interfaces réseau")
    print("🌐 URL locale: http://localhost:8000")
    print("🌐 URL réseau: http://0.0.0.0:8000")
    print("📋 Endpoints disponibles:")
    print("   - / (page d'accueil)")
    print("   - /machines (liste des machines en JSON)")
    print("   - /machines/html (interface web)")
    print("   - /files (liste des fichiers disponibles)")
    print("   - /files/{filename} (téléchargement de fichiers)")
    print("   - /installers/os_downloader.sh (téléchargement du script)")
    print("   - /installers/os_installer.sh (téléchargement du script)")
    print("=" * 50)
    
    uvicorn.run(
        app,
        host="0.0.0.0",  # Écouter sur toutes les interfaces réseau
        port=8000,
        reload=True,  # Rechargement automatique en développement
        log_level="info"
    ) 