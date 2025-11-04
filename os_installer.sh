#!/bin/bash

# Script d'installation automatique de macOS
# Compatible avec les Mac Intel et Apple Silicon
# Conçu pour être exécuté via Apple Remote Desktop
# IMPORTANT: Exécutez ce script via "Send UNIX command" dans ARD 
# en tant qu'utilisateur "root" pour éviter les problèmes de sudo

# Configuration des variables d'administrateur
ADMIN_USER="smartelia"  # Remplacer par le nom d'utilisateur admin souhaité
ADMIN_PASS="WeAr24DM!n"  # Remplacer par le mot de passe admin souhaité

# Configuration du journal
LOG_FILE="/var/tmp/macos_auto_install.log"

# Couleurs pour une meilleure lisibilité dans les logs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Fonction de journalisation
log() {
    # Créer le fichier de log avec les bonnes permissions si nécessaire
    if [ ! -f "$LOG_FILE" ]; then
        touch "$LOG_FILE" 2>/dev/null || sudo touch "$LOG_FILE"
        sudo chmod 666 "$LOG_FILE" 2>/dev/null
    fi
    
    # Vérifier si on peut écrire dans le fichier
    if [ ! -w "$LOG_FILE" ]; then
        sudo chmod 666 "$LOG_FILE" 2>/dev/null
    fi
    
    # Écrire dans le log
    echo -e "$(date '+%Y-%m-%d %H:%M:%S') - $1" | sudo tee -a "$LOG_FILE" > /dev/null
}

# Fonction pour afficher un message d'erreur et quitter
error_exit() {
    log "${RED}ERREUR: $1${NC}"
    exit 1
}

# Trouver automatiquement l'installateur macOS le plus récent
find_installer() {
    local search_dirs=("/Applications" "/Users/Shared" "/var/tmp")
    local installer_pattern="Install macOS*.app"
    local newest_installer=""
    local newest_date=0
    
    log "${BLUE}Recherche de l'installateur macOS...${NC}" >&2
    
    # Fonction pour vérifier les permissions d'un dossier
    check_dir_permissions() {
        local dir="$1"
        if [ ! -d "$dir" ]; then
            log "${YELLOW}Dossier inexistant: $dir${NC}" >&2
            return 1
        fi
        if [ ! -r "$dir" ]; then
            log "${YELLOW}Pas de permission de lecture sur: $dir${NC}" >&2
            return 1
        fi
        return 0
    }
    
    # Recherche dans les dossiers système
    for dir in "${search_dirs[@]}"; do
        if check_dir_permissions "$dir"; then
            log "${BLUE}Recherche dans $dir${NC}" >&2
            while IFS= read -r installer; do
                if [ -d "$installer" ] && [ -x "$installer/Contents/Resources/startosinstall" ]; then
                    local mod_date=$(sudo stat -f "%m" "$installer" 2>/dev/null)
                    if [ $? -eq 0 ] && [ $mod_date -gt $newest_date ]; then
                        newest_date=$mod_date
                        newest_installer="$installer"
                    fi
                fi
            done < <(sudo find "$dir" -maxdepth 1 -name "$installer_pattern" -type d 2>/dev/null)
        fi
    done
    
    # Recherche dans les dossiers de téléchargement des utilisateurs connectés
    for user_home in /Users/*; do
        if check_dir_permissions "$user_home"; then
            local downloads_dirs=("$user_home/Downloads" "$user_home/Téléchargements" "$user_home/Desktop" "$user_home/script")
            for dl_dir in "${downloads_dirs[@]}"; do
                if check_dir_permissions "$dl_dir"; then
                    log "${BLUE}Recherche dans $dl_dir${NC}" >&2
                    while IFS= read -r installer; do
                        if [ -d "$installer" ] && [ -x "$installer/Contents/Resources/startosinstall" ]; then
                            local mod_date=$(sudo stat -f "%m" "$installer" 2>/dev/null)
                            if [ $? -eq 0 ] && [ $mod_date -gt $newest_date ]; then
                                newest_date=$mod_date
                                newest_installer="$installer"
                            fi
                        fi
                    done < <(sudo find "$dl_dir" -maxdepth 1 -name "$installer_pattern" -type d 2>/dev/null)
                fi
            done
        fi
    done
    
    # Vérifier si l'installateur est dans le dossier temporaire
    local temp_dir="/var/tmp"
    if check_dir_permissions "$temp_dir"; then
        log "${BLUE}Recherche dans $temp_dir${NC}" >&2
        while IFS= read -r installer; do
            if [ -d "$installer" ] && [ -x "$installer/Contents/Resources/startosinstall" ]; then
                local mod_date=$(sudo stat -f "%m" "$installer" 2>/dev/null)
                if [ $? -eq 0 ] && [ $mod_date -gt $newest_date ]; then
                    newest_date=$mod_date
                    newest_installer="$installer"
                fi
            fi
        done < <(sudo find "$temp_dir" -maxdepth 1 -name "$installer_pattern" -type d 2>/dev/null)
    fi
    
    # Vérifier si l'installateur est dans le dossier de l'utilisateur courant
    local current_user_home="$HOME"
    if [ -n "$current_user_home" ] && check_dir_permissions "$current_user_home"; then
        local user_downloads=("$current_user_home/Downloads" "$current_user_home/Téléchargements")
        for dl_dir in "${user_downloads[@]}"; do
            if check_dir_permissions "$dl_dir"; then
                log "${BLUE}Recherche dans $dl_dir${NC}" >&2
                while IFS= read -r installer; do
                    if [ -d "$installer" ] && [ -x "$installer/Contents/Resources/startosinstall" ]; then
                        local mod_date=$(stat -f "%m" "$installer" 2>/dev/null)
                        if [ $? -eq 0 ] && [ $mod_date -gt $newest_date ]; then
                            newest_date=$mod_date
                            newest_installer="$installer"
                        fi
                    fi
                done < <(find "$dl_dir" -maxdepth 1 -name "$installer_pattern" -type d 2>/dev/null)
            fi
        done
    fi
    
    if [ -n "$newest_installer" ]; then
        log "${GREEN}Installateur trouvé: $newest_installer${NC}" >&2
        echo "$newest_installer"
        return 0
    else
        log "${RED}Aucun installateur macOS valide trouvé${NC}" >&2
        return 1
    fi
}

# Vérifier l'espace disque disponible
check_disk_space() {
    local free_space=$(df -h / | awk 'NR==2 {print $4}')
    local free_space_bytes=$(df / | awk 'NR==2 {print $4}')
    
    # Besoin d'au moins 20 GB d'espace libre
    if [ $free_space_bytes -lt 20000000 ]; then
        log "${RED}Espace disque insuffisant: $free_space disponible, 20 GB requis${NC}"
        return 1
    fi
    
    log "${GREEN}Espace disque disponible: $free_space${NC}"
    return 0
}

# Détecter l'architecture du Mac
detect_architecture() {
    local arch=$(uname -m)
    if [ "$arch" = "arm64" ]; then
        log "${BLUE}Architecture détectée: Apple Silicon (ARM)${NC}"
        echo "apple_silicon"
    elif [ "$arch" = "x86_64" ]; then
        log "${BLUE}Architecture détectée: Intel${NC}"
        echo "intel"
    else
        log "${RED}Architecture non reconnue: $arch${NC}"
        echo "unknown"
    fi
}

# Vérifier la compatibilité avec l'installateur macOS
check_compatibility() {
    # Vérification de la version désactivée temporairement pour debug
    return 0
}

# Fonction pour afficher une boîte de dialogue à l'utilisateur
show_user_dialog() {
    local message="$1"
    local title="$2"
    local user=$(stat -f "%Su" /dev/console 2>/dev/null)
    
    if [ -z "$user" ]; then
        log "${YELLOW}Aucun utilisateur connecté détecté${NC}"
        return 1
    fi
    
    local uid=$(id -u "$user" 2>/dev/null)
    if [ -z "$uid" ]; then
        log "${YELLOW}Impossible de déterminer l'UID de l'utilisateur $user${NC}"
        return 1
    fi

    log "${BLUE}Affichage d'une boîte de dialogue dans la session de l'utilisateur: $user (UID: $uid)${NC}"

    launchctl asuser "$uid" sudo -u "$user" osascript <<EOF
tell application "System Events"
    activate
    display dialog "$message" with title "$title" 
end tell
EOF

    if [ $? -ne 0 ]; then
        log "${YELLOW}Impossible d'afficher la boîte de dialogue pour l'utilisateur $user${NC}"
        return 1
    fi
}

# Exécuter l'installation
run_installation() {
    local installer="$1"
    log "DEBUG: Argument reçu par run_installation: $installer"
    local installer_bin="$installer/Contents/Resources/startosinstall"
    log "DEBUG: Chemin calculé pour startosinstall: $installer_bin"

    if [ ! -x "$installer_bin" ]; then
        error_exit "Le programme d'installation est introuvable ou non exécutable: $installer_bin"
    fi

    log "${GREEN}Démarrage de l'installation de macOS depuis: $installer${NC}"
    log "${YELLOW}L'ordinateur redémarrera automatiquement après l'installation${NC}"

    # Afficher une notification à l'utilisateur connecté
    show_user_dialog "Installation de macOS en cours...\nMerci de ne pas éteindre ou fermer cet ordinateur." "Déploiement automatique"

    # Vérifier si le fichier de log existe, sinon le créer
    if [ ! -f "$LOG_FILE" ]; then
        touch "$LOG_FILE" || error_exit "Impossible de créer le fichier de log: $LOG_FILE"
    fi

    "$installer_bin" \
        --agreetolicense \
        --nointeraction \
        --forcequitapps \
        --volume / \
        --rebootdelay 300 \
        --user "$ADMIN_USER" \
        --stdinpass <<< "$ADMIN_PASS"

    return $?
}

# Fonction principale
main() {
    # Créer et configurer le fichier de log au démarrage
    touch "$LOG_FILE" 2>/dev/null || sudo touch "$LOG_FILE"
    sudo chmod 666 "$LOG_FILE" 2>/dev/null
    
    log "${BLUE}=== Démarrage du script d'installation automatique macOS ===${NC}"
    log "${BLUE}Exécuté en tant que: $(whoami)${NC}"
    
    # Vérifier si root
    if [ "$(id -u)" != "0" ]; then
        log "${RED}ATTENTION: Ce script n'est pas exécuté en tant que root${NC}"
        log "${RED}L'installation pourrait échouer. Utilisez 'root' dans ARD${NC}"
    fi
    
    # Vérifier l'espace disque
    check_disk_space || error_exit "Espace disque insuffisant pour l'installation"
    
    # Détecter l'architecture
    arch=$(detect_architecture)
    log "Résultat de la détection d'architecture: $arch${NC}"
    
    # Trouver l'installateur
    installer=$(find_installer)
    log "DEBUG: Résultat brut de find_installer : $installer"
    if [ $? -ne 0 ] || [ ! -d "$installer" ]; then
        error_exit "Aucun installateur macOS valide trouvé"
    fi
    log "Installateur trouvé: $installer"
    
    # Vérifier que le chemin est bien un .app
    if [[ ! "$installer" =~ \.app$ ]]; then
        error_exit "La variable installer ne contient pas un chemin .app valide: $installer"
    fi
    
    # Vérifier la compatibilité
    check_compatibility "$installer" "$arch"
    
    # Lancer l'installation sans demander de confirmation
    log "${GREEN}Lancement de l'installation automatique depuis: $installer${NC}"
    run_installation "$installer"
    
    log "${GREEN}Installation lancée avec succès${NC}"
}

# Exécuter le script principal
main