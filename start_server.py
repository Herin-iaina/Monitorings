#!/usr/bin/env python3
"""
Script de démarrage du serveur FastAPI pour l'API de visualisation des machines SMARTELIA
"""

import uvicorn
import os
from dotenv import load_dotenv
from network_api import app

load_dotenv()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print("Démarrage du serveur FastAPI...")
    print("Le serveur sera accessible sur toutes les interfaces réseau")
    print(f"URL locale: http://localhost:{port}")
    print(f"URL réseau: http://0.0.0.0:{port}")
    print("=" * 50)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )