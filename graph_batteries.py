import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Lecture du fichier CSV
df = pd.read_csv('smartelia_machines_20250714_121407.csv')

# Nettoyage des colonnes utiles
cycles = []
capacites = []
hostnames = []
annees = []

for idx, row in df.iterrows():
    hostname = row['Hostname']
    annee = row['Annee'] if str(row['Annee']).isdigit() else None
    # Extraction du nombre de cycles
    try:
        cycle = int(str(row['Battery Details']).split('cycle_count: ')[1].split(',')[0])
    except:
        cycle = None
    # Extraction de la capacité max
    try:
        cap = row['Battery Details']
        if 'max_capacity:' in cap:
            cap = cap.split('max_capacity: ')[1].split(',')[0]
            cap = int(cap) if cap != 'None' else None
        else:
            cap = None
    except:
        cap = None
    hostnames.append(hostname)
    annees.append(annee)
    cycles.append(cycle)
    capacites.append(cap)

# Création d'un DataFrame propre
data = pd.DataFrame({
    'Hostname': hostnames,
    'Annee': annees,
    'Cycles': cycles,
    'Capacite': capacites
})

# 1. Graphique : Nombre de cycles par machine
plt.figure(figsize=(14,6))
data_sorted = data.sort_values('Cycles', ascending=False)
plt.bar(data_sorted['Hostname'], data_sorted['Cycles'], color='skyblue')
plt.xticks(rotation=90, fontsize=8)
plt.ylabel('Nombre de cycles')
plt.title('Nombre de cycles par machine')
plt.tight_layout()
plt.savefig('cycles_par_machine.png')
plt.close()

# 2. Graphique : Capacité maximale (%) par machine
plt.figure(figsize=(14,6))
data_sorted_cap = data.sort_values('Capacite', ascending=True)
plt.bar(data_sorted_cap['Hostname'], data_sorted_cap['Capacite'], color='orange')
plt.xticks(rotation=90, fontsize=8)
plt.ylabel('Capacité maximale (%)')
plt.title('Capacité maximale de batterie par machine')
plt.tight_layout()
plt.savefig('capacite_par_machine.png')
plt.close()

# 3. Projection dans 2 ans pour les machines 2020
machines_2020 = data[data['Annee'] == 2020].copy()
# Hypothèse : +100 cycles/an (usage modéré)
machines_2020['Cycles_2ans'] = machines_2020['Cycles'].apply(lambda x: x + 200 if pd.notnull(x) else None)
plt.figure(figsize=(14,6))
bar1 = plt.bar(machines_2020['Hostname'], machines_2020['Cycles'], label='Actuel', color='green')
bar2 = plt.bar(machines_2020['Hostname'], machines_2020['Cycles_2ans'], label='Dans 2 ans', color='red', alpha=0.5)
plt.xticks(rotation=90, fontsize=8)
plt.ylabel('Nombre de cycles')
plt.title('Projection du nombre de cycles dans 2 ans (machines 2020)')
plt.legend()
plt.tight_layout()
plt.savefig('projection_cycles_2020.png')
plt.close()

print('Graphiques générés : cycles_par_machine.png, capacite_par_machine.png, projection_cycles_2020.png') 