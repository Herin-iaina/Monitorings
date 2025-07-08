# Préparation sudoers (à exécuter en premier)

#!/bin/bash
# Script de préparation sudoers pour automatisation SSH
# À exécuter sur chaque machine cible via ARD

echo "=== Préparation sudoers pour automatisation ==="

# Sauvegarder le sudoers original
sudo cp /etc/sudoers /etc/sudoers.backup
echo "✓ Sauvegarde sudoers créée"

# Ajouter les règles pour l'utilisateur smartelia
echo "Defaults:smartelia !requiretty" | sudo tee -a /etc/sudoers
echo "smartelia ALL=(ALL) NOPASSWD: /usr/bin/dscl, /usr/sbin/createhomedir, /bin/mkdir, /bin/chown, /bin/chmod, /usr/bin/tee, /bin/cp, /bin/echo" | sudo tee -a /etc/sudoers

echo "✓ Règles sudoers ajoutées"
echo "✓ L'utilisateur smartelia peut maintenant exécuter sudo sans mot de passe"
echo "=== Script terminé ==="


# Script 3 : Configuration SSH smartelia
#!/bin/bash
# Script de configuration SSH pour l'utilisateur smartelia
# À exécuter sur chaque machine cible via ARD

echo "=== Configuration SSH smartelia ==="

# Créer le dossier .ssh
sudo mkdir -p /Users/smartelia/.ssh

# Ajouter la clé SSH
echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOyTZgRjxH2CG6ljmbFxvPXdWl1PJF5ZhcOVVHsRADVn deployer@SERVEUR-SMARTELIA' | sudo tee /Users/smartelia/.ssh/authorized_keys > /dev/null

# Définir les permissions
sudo chown -R smartelia:staff /Users/smartelia/.ssh
sudo chmod 700 /Users/smartelia/.ssh
sudo chmod 600 /Users/smartelia/.ssh/authorized_keys

echo "✓ Configuration SSH smartelia terminée"
echo "=== Script terminé ==="


# Script 4 : Vérification (optionnel)
#!/bin/bash
# Script de vérification des configurations
# À exécuter pour vérifier que tout fonctionne

echo "=== Vérification des configurations ==="

echo "1. Vérification utilisateur deployer:"
id deployer
echo ""

echo "2. Vérification dossier deployer:"
ls -la /var/.hidden/deployer/.ssh/
echo ""

echo "3. Vérification dossier smartelia:"
ls -la /Users/smartelia/.ssh/
echo ""

echo "4. Test sudo deployer:"
sudo -u deployer sudo whoami
echo ""

echo "5. Test sudo smartelia:"
sudo -u smartelia sudo whoami
echo ""

echo "=== Vérification terminée ==="

# Ordre d'exécution dans ARD :
# Script 1 : Préparation sudoers
# Script 2 : Création deployer
# Script 3 : Configuration smartelia
# Script 4 : Vérification (optionnel)