"""
╔══════════════════════════════════════════════════════════════════╗
║   TRUCK MANAGER BOT v3                                          ║
╠══════════════════════════════════════════════════════════════════╣
║  • Panneau agrandi automatiquement                              ║
║  • Lecture complète de tous les états (tableau agrandi)         ║
║  • Envoi individuel camion par camion                           ║
║  • Timers intelligents par camion (Arrivée / Prêt dans)        ║
║  • Garé → bouton rond vert → Au Repos → Envoie                 ║
║  • En Attente → attend le timer "Prêt dans"                    ║
║  • Ne pas envoyer camion usure ≥ 50%                           ║
║  • Garage → Entretien : sélection individuelle + réparation     ║
║  • Ressources : diesel/kWh/CO2                                  ║
║  • Siège : récompense XP + entraînement dirigeants             ║
║  • Résumé complet à chaque cycle                               ║
║  • Progression Plan de Subventions                              ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys, time, logging
import config
from adb import ADB
from ocr import OCR
from timers import TimerManager

level = getattr(logging, config.LOG_LEVEL, logging.INFO)
logging.basicConfig(
    level=level,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("TruckBot")
T = config.TEXTS


class TruckBot:

    def __init__(self, adb: ADB, ocr: OCR, timers: TimerManager):
        self.adb      = adb
        self.ocr      = ocr
        self.timers   = timers
        self.cycle    = 0
        self._err     = 0
        self._agrandi = False  # panneau agrandi ?

    # ── Helpers ───────────────────────────────────────────────────

    def _s(self):
        s = self.adb.screenshot()
        if s is None:
            self._err += 1
            if self._err >= 4:
                self.adb.reconnect()
                self._err = 0
        else:
            self._err = 0
        return s

    def _tap(self, r):
        if r:
            self.adb.tap(r.cx, r.cy)
            return True
        return False

    def _retour(self):
        s = self._s()
        if s is not None:
            r = self.ocr.find(s, T["retour"])
            if r:
                self.adb.tap(r.cx, r.cy)
                time.sleep(1.0)
                return
        self.adb.back()
        time.sleep(0.8)

    def _nav_bas(self, targets):
        s = self._s()
        if s is None:
            return False
        r = self.ocr.find(s, targets)
        if r:
            self.adb.tap(r.cx, r.cy)
            time.sleep(1.5)
            return True
        return False

    # ── Panneau agrandi ───────────────────────────────────────────

    def agrandir_panneau(self):
        """Clique sur le bouton ⛶ pour agrandir le panneau."""
        s = self._s()
        if s is None:
            return False
        # Cherche le bouton d'agrandissement par coordonnées
        self.adb.tap(*config.COORDS_AGRANDIR)
        time.sleep(0.8)
        log.info("⛶ Panneau agrandi")
        self._agrandi = True
        return True

    def reduire_panneau(self):
        """Réduit le panneau (pour naviguer vers Garage/Siège)."""
        if not self._agrandi:
            return
        self.adb.tap(*config.COORDS_REDUIRE)
        time.sleep(0.5)
        self._agrandi = False

    def assurer_panneau_agrandi(self):
        """S'assure que le panneau est agrandi, le réagrandit si besoin."""
        s = self._s()
        if s is None:
            return
        # Vérifie si les colonnes du tableau agrandi sont visibles
        if not self.ocr.has(s, ["Itinéraire", "Destination", "Charge maximale"]):
            log.info("⛶ Réagrandissement du panneau...")
            self.agrandir_panneau()

    # ── Popups ────────────────────────────────────────────────────

    def dismiss_popups(self, s=None):
        """
        Ferme uniquement les vraies popups.
        Utilise une correspondance exacte pour éviter les faux positifs.
        """
        closed = 0
        for _ in range(5):
            if s is None:
                s = self._s()
            if s is None:
                break

            # Cherche le X de fermeture (exact)
            r = self.ocr.find(s, ["×", "✕"], partial=False)
            if r:
                log.info("🔔 Ferme popup (X)")
                self.adb.tap(r.cx, r.cy)
                closed += 1
                time.sleep(0.7)
                s = None
                continue

            # Cherche uniquement des boutons longs et explicites
            # PAS de correspondance partielle pour éviter faux positifs
            vrais_boutons = [
                "Fermer", "Continuer", "Non merci", "Plus tard",
                "Ignorer", "No thanks", "Later", "Continue"
            ]
            found = False
            results = self.ocr.scan(s)
            for r in results:
                txt = r.text.strip()
                if txt in vrais_boutons and len(txt) >= 5:
                    log.info("🔔 Ferme popup ('%s')", txt)
                    self.adb.tap(r.cx, r.cy)
                    closed += 1
                    time.sleep(0.7)
                    s = None
                    found = True
                    break
            if found:
                continue

            break

        return closed > 0

    def _fermer_apres_envoi(self):
        """Ferme le Résumé De Départ et la popup Boutique après un envoi."""
        for _ in range(4):
            s = self._s()
            if s is None:
                break
            if self.ocr.has(s, T["resume_depart"] + T["boutique_popup"]):
                self.dismiss_popups(s)
                time.sleep(0.6)
            else:
                break

    # ── Lecture état panneau ──────────────────────────────────────

    def _detecter_etat(self, s):
        """Détecte l'état affiché dans le panneau (Au Repos, En Route, etc.)"""
        for etat, targets in [
            ("au_repos",   T["au_repos"]),
            ("en_route",   T["en_route"]),
            ("gare",       T["gare"]),
            ("en_attente", T["en_attente"]),
        ]:
            if self.ocr.has(s, targets):
                return etat
        return None

    # ── Envoi individuel ──────────────────────────────────────────

    def _envoyer_camion_ligne(self, row_y):
        """
        Clique sur l'icône camion vert en bout de ligne pour envoyer
        un camion individuellement.
        row_y : y de la ligne dans le tableau agrandi
        """
        self.adb.tap(config.COORDS_ENVOYER_X, row_y)
        time.sleep(1.0)
        self._fermer_apres_envoi()

    def _retour_repos_camion_gare(self, row_y):
        """
        Clique sur le bouton rond vert en bout de ligne (Garé)
        pour remettre le camion Au Repos.
        """
        self.adb.tap(config.COORDS_ROND_VERT_X, row_y)
        time.sleep(1.0)

    # ── Action Au Repos ───────────────────────────────────────────

    def action_au_repos(self, rows):
        """
        Clique sur "Tout Envoyer" en mode agrandi.
        Le bouton est à position fixe x=480, y=550 en 960x600.
        """
        # Log usure élevée
        for row in rows:
            if row.get("usure") and row["usure"] >= config.USURE_SEUIL:
                log.warning("  ⚠️  %s usure %.1f%% ≥ %.0f%%",
                            row["reg"], row["usure"], config.USURE_SEUIL)

        # S'assure que le panneau est agrandi
        self.assurer_panneau_agrandi()
        time.sleep(0.5)

        # Tape sur "Tout Envoyer" par coordonnées fixes
        log.info("  🚛 Tout Envoyer → tap")
        self.adb.tap(config.COORDS_TOUT_ENVOYER[0],
                     config.COORDS_TOUT_ENVOYER[1])
        time.sleep(1.2)
        self._fermer_apres_envoi()

        # Navigue sur tous les onglets pour lire les timers
        time.sleep(1.0)
        self.action_lire_tous_etats()
        return True

    def _naviguer_onglet(self, coords, etat_attendu):
        """Clique sur une icône de la barre du bas et vérifie l'état."""
        self.adb.tap(*coords)
        time.sleep(1.0)
        s = self._s()
        if s is None:
            return False
        results = self.ocr.scan(s)
        etat = self.ocr.detect_panel_state(s, results=results)
        log.debug("  Onglet → état : %s (attendu : %s)", etat, etat_attendu)
        return etat == etat_attendu

    def action_lire_tous_etats(self):
        """
        Après Tout Envoyer : lit l'onglet En Route pour les timers.
        Retry une fois si aucun timer détecté.
        """
        self.assurer_panneau_agrandi()
        time.sleep(0.5)

        log.info("🚛 Lecture En Route...")
        self.adb.tap(*config.COORDS_TAB_EN_ROUTE)
        time.sleep(2.0)
        self.assurer_panneau_agrandi()

        s = self._s()
        rows = []
        if s is not None:
            rows = self.ocr.read_table_en_route(s)

        # Retry si aucun timer détecté
        if not rows:
            log.info("  ⚠️  Aucun timer — retry dans 3s...")
            time.sleep(3.0)
            s = self._s()
            if s is not None:
                rows = self.ocr.read_table_en_route(s)

        if rows:
            self.action_en_route(rows)
            log.info("  ✅ %d timer(s) notés", len(rows))
        else:
            log.info("  Aucun camion En Route détecté")

        # Retour Au Repos
        self.adb.tap(*config.COORDS_TAB_AU_REPOS)
        time.sleep(1.0)

    # ── Action Garé ───────────────────────────────────────────────

    def action_gare(self, rows):
        """
        Pour chaque camion Garé : clique rond vert → Au Repos.
        Ensuite ils seront envoyés au prochain cycle.
        """
        for row in rows:
            log.info("  🅿️  %s garé → retour Au Repos", row["reg"] or "?")
            self._retour_repos_camion_gare(row["row_y"])
            time.sleep(0.8)

        return len(rows) > 0

    # ── Action En Route ───────────────────────────────────────────

    def action_en_route(self, rows):
        """
        Lit les timers d'arrivée de chaque camion En Route.
        Les note dans TimerManager.
        """
        for row in rows:
            reg = row["reg"] or f"camion_{row['row_y']}"
            if row["arrivee_s"] is not None:
                self.timers.set_timer(reg, row["arrivee_s"])
                h = row["arrivee_s"] // 3600
                m = (row["arrivee_s"] % 3600) // 60
                s = row["arrivee_s"] % 60
                log.info("  ⏱️  %s → arrivée dans %02d:%02d:%02d", reg, h, m, s)

    # ── Action En Attente ─────────────────────────────────────────

    def action_en_attente(self, rows):
        """
        Lit les timers "Prêt dans" de chaque camion En Attente
        (réparation ou CT). Les note dans TimerManager.
        """
        for row in rows:
            reg = row["reg"] or f"attente_{row['row_y']}"
            if row["pret_dans_s"] is not None:
                self.timers.set_timer(f"attente_{reg}", row["pret_dans_s"])
                h = row["pret_dans_s"] // 3600
                m = (row["pret_dans_s"] % 3600) // 60
                s = row["pret_dans_s"] % 60
                log.info("  🔧 %s en attente → prêt dans %02d:%02d:%02d", reg, h, m, s)

    # ── Résumé cycle ──────────────────────────────────────────────

    def _log_resume(self, etat, rows, cash, coins, subv):
        """Affiche un résumé complet de l'état du jeu."""
        log.info("")
        log.info("┌─────────────────────────────────────┐")
        log.info("│  RÉSUMÉ CYCLE #%-3d                  │", self.cycle)
        log.info("├─────────────────────────────────────┤")
        log.info("│  💰 Cash   : $%-10.0f             │", cash or 0)
        log.info("│  🪙 Pièces : %-10s                │", str(coins or "?"))

        if subv[0] is not None:
            log.info("│  📋 Subvention : $%.0f / $%.0f (%.1f%%) │",
                     subv[0], subv[1], subv[2])

        log.info("│  📊 État panneau : %-16s    │", etat or "?")
        log.info("│  🚛 Camions : %-3d lignes             │", len(rows))

        for row in rows:
            reg_str  = row.get('reg') or "?"
            dest_str = row.get('destination') or "-"
            if row.get('arrivee_s') is not None:
                h2 = row['arrivee_s'] // 3600
                m2 = (row['arrivee_s'] % 3600) // 60
                s2 = row['arrivee_s'] % 60
                log.info("│    %-10s → %-3s  %02d:%02d:%02d            │",
                         reg_str, dest_str, h2, m2, s2)
            else:
                log.info("│    %-10s → %-3s                      │",
                         reg_str, dest_str)

        if self.timers.timers:
            log.info("│  ⏱️  Timers actifs :                 │")
            for line in self.timers.status().splitlines():
                log.info("│  %s", line)

        log.info("└─────────────────────────────────────┘")

    # ── Garage ────────────────────────────────────────────────────

    def action_garage_entretien(self):
        log.info("🔧 Vérification Garage → Entretien...")
        self.reduire_panneau()

        if not self._nav_bas(T["garage"]):
            log.warning("Garage introuvable")
            self.agrandir_panneau()
            return False

        s = self._s()
        if s is None:
            return False

        r = self.ocr.find(s, T["entretien"])
        if not r:
            log.warning("Bouton Entretien introuvable")
            self._retour()
            self.agrandir_panneau()
            return False

        self.adb.tap(r.cx, r.cy)
        time.sleep(1.2)

        s = self._s()
        if s is None:
            self._retour()
            self.agrandir_panneau()
            return False

        if not self.ocr.is_entretien_screen(s):
            log.warning("Écran Entretien non reconnu")
            self._retour()
            self.agrandir_panneau()
            return False

        rows = self.ocr.read_entretien_table(s)
        log.info("📊 %d camion(s) dans le tableau", len(rows))
        for row in rows:
            log.info("  %s : usure=%.1f%% CT=%dj", row["reg"], row["usure"], row["ct_jours"])

        a_reparer = [r for r in rows if r["usure"] >= config.USURE_SEUIL]
        a_ct      = [r for r in rows if r["ct_jours"] <= config.CT_JOURS_SEUIL]
        acted     = False

        if a_reparer:
            log.warning("⚠️  %d camion(s) à réparer", len(a_reparer))
            self._cocher_et_agir(s, a_reparer, rows,
                                 T["reparation_vrac"], T["reparer_btn"])
            acted = True

        if a_ct:
            log.warning("⚠️  %d camion(s) CT urgent", len(a_ct))
            s = self._s() or s
            self._cocher_et_agir(s, a_ct, rows,
                                 T["masse_ct"], T["envoyer_ct"])
            acted = True

        if not acted:
            log.info("✅ Flotte OK")

        self._retour()
        time.sleep(0.5)
        self._retour()
        self.agrandir_panneau()
        return acted

    def _cocher_et_agir(self, s, targets, all_rows, btn_action, btn_confirm):
        checkbox_x = config.ENTRETIEN_CHECKBOX_X
        first_y    = config.ENTRETIEN_FIRST_ROW_Y
        row_h      = config.ENTRETIEN_ROW_HEIGHT

        r_desel = self.ocr.find(s, ["Tout Désélectionner", "Tout Deselectionner"])
        if r_desel:
            self.adb.tap(r_desel.cx, r_desel.cy)
            time.sleep(0.5)

        for i, row in enumerate(all_rows):
            if row in targets:
                check_y = first_y + i * row_h
                log.info("  ☑️  Coche %s (y=%d)", row["reg"], check_y)
                self.adb.tap(checkbox_x, check_y)
                time.sleep(0.4)

        time.sleep(0.5)
        s2 = self._s()
        if s2 is None:
            return

        r_action = self.ocr.find(s2, btn_action)
        if r_action:
            self.adb.tap(r_action.cx, r_action.cy)
            time.sleep(1.0)
            s3 = self._s()
            if s3:
                r_confirm = self.ocr.find(s3, btn_confirm)
                if r_confirm:
                    self.adb.tap(r_confirm.cx, r_confirm.cy)
                    time.sleep(0.8)
                s4 = self._s()
                if s4:
                    self.dismiss_popups(s4)
            log.info("  ✅ Action lancée")

    # ── Ressources ────────────────────────────────────────────────

    def _acheter_ressource(self, coords, titre, label, seuil):
        """
        Ouvre la jauge, glisse le slider au max et clique Acheter.
        """
        self.adb.tap(*coords)
        time.sleep(1.5)
        s = self._s()
        if s is None:
            return False

        # Vérifie qu'on est bien sur un menu ressource
        # L'OCR lit "Augmenter" et "capacité" sur ce menu
        if not self.ocr.has(s, ["Augmenter", "capacité", "Acheter", "Coût"]):
            log.info("  %s : menu non trouvé", label)
            self.adb.back()
            time.sleep(0.5)
            return False

        # Glisse le slider au maximum avec draganddrop
        # x=820 fonctionne pour Diesel, kWh et CO2
        h, w = s.shape[:2]
        slider_y  = int(h * 0.717)   # natif y=860 / 1200
        slider_x1 = int(w * 0.427)   # natif x=820 / 1920
        slider_x2 = int(w * 0.625)   # natif x=1200 / 1920
        self.adb.drag(slider_x1, slider_y, slider_x2, slider_y, 3000)
        time.sleep(1.5)

        # Clique Acheter par coordonnées fixes (natif 1315x855)
        acheter_x = int(w * 0.685)   # 1315/1920
        acheter_y = int(h * 0.713)   # 855/1200
        self.adb.tap(acheter_x, acheter_y)
        time.sleep(0.8)
        s2 = self._s()
        if s2 is not None:
            self.dismiss_popups(s2)
        log.info("  ✅ %s acheté", label)
        self.adb.back()
        time.sleep(0.5)
        return True

    def action_ressources(self):
        log.info("⛽ Vérification ressources...")
        self.reduire_panneau()
        acted = False
        acted |= self._acheter_ressource(config.COORDS_DIESEL,
                     T["titre_diesel"], "Diesel", config.DIESEL_SEUIL)
        acted |= self._acheter_ressource(config.COORDS_KWH,
                     T["titre_kwh"], "kWh", config.KWH_SEUIL)
        acted |= self._acheter_ressource(config.COORDS_CO2,
                     T["titre_co2"], "CO2", config.CO2_SEUIL)
        self.agrandir_panneau()
        return acted

    # ── Siège ─────────────────────────────────────────────────────

    def action_siege(self, cash):
        log.info("🏆 Vérification Siège...")
        self.reduire_panneau()

        if not self._nav_bas(T["siege"]):
            self.agrandir_panneau()
            return False

        s = self._s()
        if s is None:
            self.agrandir_panneau()
            return False

        acted = False

        if not self.ocr.has(s, T["aucune_recompense"]):
            r = self.ocr.find(s, T["recompense_dispo"])
            if r:
                self.adb.tap(r.cx, r.cy)
                time.sleep(0.8)
                s = self._s() or s
                self.dismiss_popups(s)
                log.info("  ✅ Récompense XP collectée")
                acted = True

        if cash and cash >= config.BUDGET_ENTRAINEMENT:
            r_perso = self.ocr.find(s, T["personnel"])
            if r_perso:
                self.adb.tap(r_perso.cx, r_perso.cy)
                time.sleep(1.0)
                trained = 0
                for _ in range(4):
                    s2 = self._s()
                    if s2 is None:
                        break
                    r_train = self.ocr.find(s2, T["entrainer"])
                    if not r_train:
                        break
                    self.adb.tap(r_train.cx, r_train.cy)
                    time.sleep(0.8)
                    s3 = self._s()
                    if s3:
                        self.dismiss_popups(s3)
                    trained += 1
                if trained:
                    log.info("  ✅ %d dirigeant(s) entraîné(s)", trained)
                    acted = True
                self._retour()

        self._retour()
        self.agrandir_panneau()
        return acted

    # ── BOUCLE PRINCIPALE ──────────────────────────────────────────

    def run(self):
        log.info("▶️  Truck Manager Bot v3 — Démarrage")
        log.info("   Ctrl+C pour stopper")

        self.adb.screen_on()
        if not self.adb.is_app_foreground():
            self.adb.launch_app()

        # Agrandit le panneau au démarrage
        time.sleep(2)
        self.agrandir_panneau()

        ressources_ctr = 0

        while True:
            self.cycle += 1

            try:
                self.adb.screen_on()
                if not self.adb.is_app_foreground():
                    log.warning("App en arrière-plan → relancement")
                    self.adb.launch_app()
                    time.sleep(3)
                    self.agrandir_panneau()

                # ── Ferme popups ──────────────────────────────
                self.dismiss_popups()

                # ── Force l'agrandissement à chaque cycle ─────
                self.agrandir_panneau()
                time.sleep(0.5)
                s = self._s()

                # ── Infos générales ───────────────────────────
                cash  = self.ocr.read_cash(s)  if s is not None else None
                coins = self.ocr.read_coins(s) if s is not None else None
                subv  = self.ocr.read_subvention(s) if s is not None else (None, None, None)

                # ── Détecte l'état ────────────────────────────
                results = self.ocr.scan(s) if s is not None else []
                etat    = self.ocr.detect_panel_state(s, results=results) if s is not None else None

                # ── Lit le tableau ────────────────────────────
                rows = []
                if s is not None and etat:
                    rows = self.ocr.read_table_agrandi(s, etat)

                # ── Résumé ────────────────────────────────────
                self._log_resume(etat, rows, cash, coins, subv)

                # ── Timers expirés ────────────────────────────
                arrived = self.timers.get_arrived()
                if arrived:
                    log.info("🏁 %d timer(s) expiré(s) : %s", len(arrived), arrived)
                    for tid in arrived:
                        self.timers.clear(tid)

                # ── Actions selon état ────────────────────────
                if etat == "au_repos":
                    count = len(rows)
                    log.info("  🏠 Camions Au Repos : %d", count)
                    if count > 0:
                        self.action_au_repos(rows)
                    else:
                        # Pas de camions Au Repos → va lire En Route si pas de timers
                        if not self.timers.timers:
                            log.info("  Aucun timer actif → lecture En Route")
                            self.action_lire_tous_etats()
                        else:
                            log.info("  Aucun camion Au Repos")

                elif etat == "en_route":
                    log.info("  🚛 En Route — timers actifs")

                elif etat == "en_attente" and rows:
                    self.action_en_attente(rows)

                elif etat in ("gare", None):
                    # Gare ignoré + état inconnu → retour Au Repos
                    log.info("  ↩️  État %s → tap Au Repos", etat)
                    self.adb.tap(*config.COORDS_TAB_AU_REPOS)
                    time.sleep(1.5)

                # ── Ressources (tous les N cycles) ───────────
                ressources_ctr += 1
                if ressources_ctr >= config.RESSOURCES_CHECK_EVERY:
                    ressources_ctr = 0
                    self.action_ressources()
                    self.dismiss_popups()
                    # Réagrandit après les ressources
                    self.assurer_panneau_agrandi()

                # ── Délai intelligent ─────────────────────────
                next_arr = self.timers.next_arrival()
                if next_arr is not None and next_arr > 0:
                    delay = min(int(next_arr) + config.TIMER_BUFFER, 3600)
                    log.info("⏱️  Prochain camion dans %dm%02ds → cycle dans %dm%02ds",
                             int(next_arr)//60, int(next_arr)%60,
                             delay//60, delay%60)
                else:
                    delay = config.CYCLE_DELAY
                    log.info("⏳ Prochain cycle dans %ds...", delay)

                time.sleep(delay)

            except Exception as e:
                self._err += 1
                log.error("Erreur cycle #%d : %s", self.cycle, e, exc_info=True)
                if self._err >= 5:
                    if not self.adb.reconnect():
                        break
                    self._err = 0
                    self.agrandir_panneau()
                time.sleep(5)
                continue


if __name__ == "__main__":
    adb    = ADB()
    if not adb.auto_connect():
        print("❌ Tablette non connectée")
        sys.exit(1)

    ocr    = OCR()
    timers = TimerManager()
    bot    = TruckBot(adb, ocr, timers)

    try:
        bot.run()
    except KeyboardInterrupt:
        log.info("🛑 Bot arrêté.")
