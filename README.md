# 🚛 Truck Manager Bot

Bot Python automatisant le jeu mobile **Truck Manager** (Trophy Games) via ADB depuis un Raspberry Pi 3 headless.

## Fonctionnalités

- ✅ Détecte les camions **Au Repos** et clique "Tout Envoyer" automatiquement
- ✅ Lit les timers **En Route** et dort intelligemment jusqu'à la prochaine arrivée
- ✅ Gère les camions **Garés** (retour Au Repos) EN DEVELOPPEMENT
- ✅ Gère les camions **En Attente** (réparation/CT) EN DEVELOPPEMENT
- ✅ Vérifie les ressources (Diesel, kWh, CO2) et achète si nécessaire EN DEVELOPPEMENT
- ✅ Ferme les popups automatiquement
- ✅ OCR via Tesseract pour lire le tableau de bord

## Matériel testé

| Composant | Modèle |
|-----------|--------|
| Serveur bot | Raspberry Pi 3 Model B (headless) |
| Tablette | Lenovo Tab M10 3rd Gen TB328FU |
| Résolution native | 1920x1200 |
| Connexion | USB (ADB) |

## Prérequis

### Sur le Raspberry Pi

```bash
sudo apt update
sudo apt install -y python3-pip adb tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng
pip3 install opencv-python-headless numpy pillow pytesseract
```

### Sur la tablette Android

1. Activer le **Mode développeur** : Paramètres → À propos → taper 7 fois sur "Numéro de build"
2. Activer le **Débogage USB** : Paramètres → Options développeur → Débogage USB
3. Connecter la tablette au Pi via USB
4. Accepter l'autorisation ADB sur la tablette

## Installation


# Vérifier la connexion ADB
adb devices
```

## Configuration

Modifier `config.py` selon votre matériel :

```python
DEVICE       = None    # None = USB auto | "192.168.1.X" = WiFi
USURE_SEUIL  = 50.0   # % usure max avant avertissement
DIESEL_SEUIL = 50     # % → achète si niveau < seuil
KWH_SEUIL    = 50
CO2_SEUIL    = 50
```

### ⚠️ Coordonnées tactiles

Les coordonnées sont **spécifiques à la résolution 1920x1200** (Lenovo TB328FU).
Les screenshots sont réduits à 50% (960x600) pour économiser le CPU du Pi 3.
Les taps ADB sont automatiquement multipliés par 2.

Pour recalibrer sur une autre tablette :
```bash
adb shell input tap X Y   # teste la position, ajuste dans config.py
```

**Coordonnées confirmées (mode agrandi) :**

| Élément | 960x600 | Natif 1920x1200 |
|---------|---------|----------------|
| ⛶ Agrandir | (174, 41) | (347, 82) |
| ⛶ Réduire | (928, 41) | (1855, 82) |
| ✅ Tout Envoyer | (480, 550) | (960, 1100) |
| 🚛 En Route | (85, 592) | (170, 1184) |
| 🏠 Au Repos | (250, 592) | (500, 1184) |
| 🅿️ Garé | (490, 592) | (980, 1184) |
| ⏱️ En Attente | (700, 592) | (1400, 1184) |
| ⛽ Diesel | (800, 12) | (1600, 25) |
| ⚡ kWh | (850, 12) | (1700, 25) |
| 🌿 CO2 | (875, 12) | (1750, 25) |

## Lancement

```bash
# Bot principal
python3 truck_bot.py

# Diagnostic (sans actions)
python3 explore.py --once

# Diagnostic avec tableau
python3 explore.py --once --tableau

# Logs en temps réel
tail -f truck_bot.log
```

## Structure

```
truck-manager-bot/
├── truck_bot.py   # Bot principal
├── ocr.py         # OCR Tesseract
├── adb.py         # Connexion ADB, screenshots, taps
├── config.py      # Coordonnées, seuils, textes
├── timers.py      # Gestion timers d'arrivée
├── explore.py     # Outil de diagnostic
└── README.md
```

## Logique

```
Démarrage → Agrandir panneau → Lire état
├─ Au Repos → Camions dispo ? → Tout Envoyer → Lire timers En Route
├─ En Route → Lire timers
├─ Garé     → Bouton rond vert → Au Repos
└─ En Attente → Lire timers "Prêt dans"
→ Dormir jusqu'au prochain timer → Recommencer
```

## Performances sur Raspberry Pi 3

- Load CPU : ~2-4 (OCR Tesseract)
- Temps par cycle : 45-90 secondes
- Screenshots réduits à 50% pour limiter la charge

## Dépannage

```bash
# ADB non détecté
adb kill-server && adb start-server && adb devices

# Vérifier Tesseract
tesseract --list-langs   # doit afficher fra et eng

# Tester un tap
adb shell input tap 347 82   # doit agrandir le panneau
```

## Licence

MIT
