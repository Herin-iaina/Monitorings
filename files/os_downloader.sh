#!/bin/bash

# Configuration
SERVER_URL="http://172.17.18.194:8000"
TEMP_DIR="/var/tmp"
LOG_FILE="/var/tmp/macos_installer_client.log"
INSTALLER_SCRIPT="os_installer.sh"

# Fonction de logging
log() {
    local level=$1
    shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $*" | tee -a "$LOG_FILE"
}

# Vérification des prérequis
check_prerequisites() {
    # Vérifier si le dossier de destination est accessible en écriture
    if [ ! -w "$TEMP_DIR" ]; then
        log "ERROR" "Le dossier $TEMP_DIR n'est pas accessible en écriture"
        return 1
    fi

    # Vérifier l'espace disque disponible (20 GB minimum)
    local required_space=$((20 * 1024 * 1024))  # 20 GB en KB
    local available_space=$(df -k "$TEMP_DIR" | awk 'NR==2 {print $4}')
    
    if [ "$available_space" -lt "$required_space" ]; then
        log "ERROR" "Espace insuffisant: $((available_space/1024/1024))GB disponible, 20GB requis"
        return 1
    fi

    # Vérifier si unzip est installé
    if ! command -v unzip &> /dev/null; then
        log "ERROR" "unzip n'est pas installé"
        return 1
    fi

    return 0
}

# Vérifier les conditions pour l'installation
check_installation_conditions() {
    log "INFO" "Vérification des conditions d'installation..."
    
    # Vérifier si le script d'installation existe
    if [ ! -f "$INSTALLER_SCRIPT" ]; then
        log "ERROR" "Le script d'installation $INSTALLER_SCRIPT n'existe pas"
        return 1
    fi
    
    # Vérifier si le script d'installation est exécutable
    if [ ! -x "$INSTALLER_SCRIPT" ]; then
        log "INFO" "Rendre le script d'installation exécutable..."
        chmod +x "$INSTALLER_SCRIPT"
        if [ $? -ne 0 ]; then
            log "ERROR" "Impossible de rendre le script d'installation exécutable"
            return 1
        fi
    fi
    
    # Vérifier si un installateur macOS a été téléchargé
    local installer_found=false
    for item in "$TEMP_DIR"/*; do
        if [[ "$item" == *"Install macOS"*".app" ]]; then
            log "INFO" "Installateur macOS trouvé: $(basename "$item")"
            installer_found=true
            break
        fi
    done
    
    if [ "$installer_found" = false ]; then
        log "ERROR" "Aucun installateur macOS trouvé dans $TEMP_DIR"
        return 1
    fi
    
    # Vérifier l'espace disque pour l'installation (20 GB minimum)
    local required_space=$((20 * 1024 * 1024))  # 20 GB en KB
    local available_space=$(df -k / | awk 'NR==2 {print $4}')
    
    if [ "$available_space" -lt "$required_space" ]; then
        log "ERROR" "Espace disque insuffisant pour l'installation: $((available_space/1024/1024))GB disponible, 20GB requis"
        return 1
    fi
    
    log "INFO" "Toutes les conditions d'installation sont remplies"
    return 0
}

# Exécuter le script d'installation
run_installer() {
    log "INFO" "Lancement du script d'installation..."
    
    # Vérifier si on est root ou si on peut utiliser sudo
    if [ "$(id -u)" = "0" ]; then
        log "INFO" "Exécution en tant que root"
        ./"$INSTALLER_SCRIPT"
    elif command -v sudo &> /dev/null; then
        log "INFO" "Exécution avec sudo"
        sudo ./"$INSTALLER_SCRIPT"
    else
        log "ERROR" "Impossible d'exécuter le script d'installation: ni root ni sudo disponible"
        return 1
    fi
    
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        log "INFO" "Script d'installation exécuté avec succès"
        return 0
    else
        log "ERROR" "Script d'installation a échoué avec le code de sortie: $exit_code"
        return 1
    fi
}

# Téléchargement et décompression d'un fichier
download_file() {
    local filename=$1
    # URL encode the filename for the URL
    local encoded_filename=$(echo "$filename" | sed 's/ /%20/g')
    local url="${SERVER_URL}/files/${encoded_filename}"
    local destination="${TEMP_DIR}/${filename}"
    
    log "INFO" "Téléchargement de $filename..."
    
    # Supprimer l'ancien fichier/dossier s'il existe
    if [ -e "$destination" ]; then
        rm -rf "$destination"
        log "INFO" "Ancien fichier/dossier supprimé: $destination"
    fi
    
    # Créer le dossier parent si nécessaire
    local parent_dir=$(dirname "$destination")
    mkdir -p "$parent_dir"
    
    # Télécharger le fichier avec curl
    if curl -L -o "$destination" "$url" 2>>"$LOG_FILE"; then
        log "INFO" "Fichier téléchargé avec succès: $filename"
        
        # Si c'est un fichier zip, le décompresser
        if [[ "$filename" == *.zip ]]; then
            log "INFO" "Décompression de $filename..."
            local extract_dir="${TEMP_DIR}/$(basename "$filename" .zip)"
            
            # Supprimer le dossier de destination s'il existe
            if [ -d "$extract_dir" ]; then
                rm -rf "$extract_dir"
            fi
            
            # Décompresser le fichier
            if unzip -q "$destination" -d "$TEMP_DIR"; then
                log "INFO" "Fichier décompressé avec succès dans $extract_dir"
                # Supprimer le fichier zip après décompression
                rm -f "$destination"
                log "INFO" "Fichier zip supprimé: $filename"
            else
                log "ERROR" "Erreur lors de la décompression de $filename"
                return 1
            fi
        fi
        return 0
    else
        log "ERROR" "Erreur lors du téléchargement de $filename"
        return 1
    fi
}

# Téléchargement de tous les fichiers
download_all_files() {
    # Obtenir la liste des fichiers
    local files_json
    files_json=$(curl -s "${SERVER_URL}/files")
    
    if [ $? -ne 0 ]; then
        log "ERROR" "Erreur lors de la récupération de la liste des fichiers"
        return 1
    fi
    
    # Extraire les noms de fichiers du JSON en préservant les espaces
    local files
    files=$(echo "$files_json" | grep -o '"name":"[^"]*"' | sed 's/"name":"//g' | sed 's/"//g')
    
    if [ -z "$files" ]; then
        log "WARNING" "Aucun fichier trouvé sur le serveur"
        return 1
    fi
    
    log "INFO" "Téléchargement des fichiers..."
    
    # Télécharger chaque fichier
    local success=true
    while IFS= read -r filename; do
        if [ -n "$filename" ]; then
            if ! download_file "$filename"; then
                success=false
                break
            fi
        fi
    done <<< "$files"
    
    if $success; then
        log "INFO" "Tous les fichiers ont été téléchargés avec succès"
        return 0
    else
        return 1
    fi
}

# Fonction principale
main() {
    log "INFO" "Démarrage du client de téléchargement"
    
    # Vérifier les prérequis
    if ! check_prerequisites; then
        log "ERROR" "Les prérequis ne sont pas satisfaits"
        exit 1
    fi
    
    # Créer le dossier temporaire si nécessaire
    mkdir -p "$TEMP_DIR"
    
    # Télécharger tous les fichiers
    if ! download_all_files; then
        log "ERROR" "Échec du téléchargement des fichiers"
        exit 1
    fi
    
    log "INFO" "Téléchargement terminé avec succès"
    
    # Vérifier les conditions d'installation
    if check_installation_conditions; then
        log "INFO" "Conditions d'installation remplies, lancement de l'installation..."
        if run_installer; then
            log "INFO" "Processus d'installation terminé avec succès"
        else
            log "ERROR" "Échec du processus d'installation"
            exit 1
        fi
    else
        log "WARNING" "Conditions d'installation non remplies, installation annulée"
        log "INFO" "Les fichiers ont été téléchargés mais l'installation n'a pas été lancée"
    fi
}

# Exécuter le script principal
main 