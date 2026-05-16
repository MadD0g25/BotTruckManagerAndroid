# ════════════════════════════════════════════
#  CONFIG — Truck Manager Bot v3
# ════════════════════════════════════════════

DEVICE      = None        # None = USB | "192.168.1.X" = WiFi
WIFI_PORT   = 5555
APP_PACKAGE = "com.trophygames.truckmanager"

# ── Timing ──────────────────────────────────
CYCLE_DELAY            = 30   # délai max entre cycles (réduit si timer proche)
GARAGE_CHECK_EVERY     = 4
RESSOURCES_CHECK_EVERY = 3
SIEGE_CHECK_EVERY      = 10
TIMER_BUFFER           = 10   # secondes de marge après expiration d'un timer

# ── Seuils ──────────────────────────────────
USURE_SEUIL            = 50.0  # % → ne pas envoyer, aller au garage
CT_JOURS_SEUIL         = 5     # jours → envoyer au CT
DIESEL_SEUIL           = 50    # % capacité
KWH_SEUIL              = 50
CO2_SEUIL              = 50
BUDGET_ENTRAINEMENT    = 50000

# ── Résolution tablette ──────────────────────
# Lenovo Tab M10 3rd Gen TB328FU — 1920x1200 natif
# Screenshots réduits à 50% → 960x600 pour économiser CPU Pi 3
SCREEN_W = 960
SCREEN_H = 600

# ── Coordonnées fixes (basées sur 960x600 = natif 1920x1200 ÷ 2) ─
COORDS_AGRANDIR        = (174, 41)   # natif 347x82  ✅
COORDS_REDUIRE         = (928, 41)   # natif 1855x82 ✅
COORDS_TOUT_ENVOYER    = (480, 550)  # natif 960x1100 ✅
COORDS_DIESEL          = (800, 12)   # natif 1600x25 ✅
COORDS_KWH             = (850, 12)   # natif 1700x25 ✅
COORDS_CO2             = (875, 12)   # natif 1750x25 ✅
COORDS_ROND_VERT_X     = 895
COORDS_ENVOYER_X       = 895
TABLE_FIRST_ROW_Y      = 78
TABLE_ROW_HEIGHT       = 18
ENTRETIEN_CHECKBOX_X   = 752
ENTRETIEN_FIRST_ROW_Y  = 252
ENTRETIEN_ROW_HEIGHT   = 18

# ── Onglets mode AGRANDI (natif ÷ 2) ────────────────────────────
# Confirmées par test adb shell input tap en mode agrandi
COORDS_TAB_EN_ROUTE   = (85,  592)   # natif 170x1184 ✅
COORDS_TAB_AU_REPOS   = (250, 592)   # natif 500x1184 ✅
COORDS_TAB_GARE       = (490, 592)   # natif 980x1184 ✅
COORDS_TAB_EN_ATTENTE = (700, 592)   # natif 1400x1184 ✅

# ── OCR ─────────────────────────────────────
OCR_LANG     = "fra+eng"
OCR_MIN_CONF = 55
OCR_CONFIG   = "--psm 6 --oem 3"

# ── Logs ────────────────────────────────────
LOG_FILE  = "truck_bot.log"
LOG_LEVEL = "INFO"

# ── Textes ──────────────────────────────────
TEXTS = {
    # États panneau principal
    "au_repos":          ["Au Repos"],
    "en_route":          ["En Route", "En route"],
    "gare":              ["Garé", "Gare"],
    "en_attente":        ["En Attente", "En attente"],

    # Navigation
    "garage":            ["Garage"],
    "siege":             ["Siège", "Siege"],
    "retour":            ["Retour", "Return"],

    # Fermeture popups
    "fermer_x":          ["×", "✕"],
    "ok":                ["OK", "Ok", "Fermer", "Close"],
    "confirmer":         ["Confirmer", "Confirm", "Oui", "Yes"],
    "non_merci":         ["Non merci", "No thanks", "Plus tard", "Later", "Ignorer"],
    "continuer":         ["Continuer", "Continue"],

    # Popups après envoi
    "resume_depart":     ["Résumé De Départ", "Camions Partis", "Cargaison À Bord"],
    "boutique_popup":    ["Offre De Démarrage", "Paquets", "4,99", "1,99", "5,99", "11,99"],

    # Tout envoyer
    "tout_envoyer":      ["Tout Envoyer", "Tout envoyer", "Send All"],

    # Colonnes tableau agrandi
    "col_arrivee":       ["Arrivée", "Arrivee", "Arrival"],
    "col_pret_dans":     ["Prêt dans", "Pret dans", "Ready in"],

    # Garage entretien
    "entretien":         ["Entretien"],
    "reparation_vrac":   ["Réparation en vrac", "Reparation en vrac"],
    "masse_ct":          ["Masse CT"],
    "reparer_btn":       ["Réparer", "Reparer", "Repair"],
    "envoyer_ct":        ["Envoyer au CT"],

    # Ressources
    "acheter":           ["Acheter", "Buy"],
    "titre_diesel":      ["Capacité de diesel", "Capacite de diesel"],
    "titre_kwh":         ["kWh", "Verrouillage de Prix"],
    "titre_co2":         ["quotas de CO2", "CO2"],

    # Siège
    "aucune_recompense": ["Aucune Récompense", "Aucune recompense"],
    "recompense_dispo":  ["Réclamer", "Reclamer", "Claim"],
    "personnel":         ["Personnel"],
    "entrainer":         ["Entraîne", "Entraine", "Train"],

    # Plan de subventions
    "subvention":        ["Plan De Subventions", "Plan de Subventions"],
}
