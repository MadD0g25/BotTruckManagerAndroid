"""Couche OCR v3 — lecture complète des tableaux agrandis."""

import logging, re, cv2, numpy as np
import config

try:
    import pytesseract
except ImportError:
    print("❌ pip3 install pytesseract && sudo apt install tesseract-ocr tesseract-ocr-fra -y")
    raise

log = logging.getLogger("TruckBot.OCR")


class R:
    def __init__(self, text, x, y, w, h, conf):
        self.text = text.strip()
        self.x, self.y, self.w, self.h, self.conf = x, y, w, h, conf
        self.cx, self.cy = x + w // 2, y + h // 2

    def __repr__(self):
        return f"R({self.text!r} {self.conf}% @{self.cx},{self.cy})"


class OCR:
    def __init__(self):
        try:
            pytesseract.get_tesseract_version()
            log.info("✅ Tesseract OK")
        except Exception:
            log.error("sudo apt install tesseract-ocr tesseract-ocr-fra -y")
            raise

    def _pre(self, img):
        """Prétraitement standard x2 — nécessaire pour bonne qualité OCR."""
        h, w = img.shape[:2]
        big  = cv2.resize(img, (w*2, h*2), interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
        thr  = cv2.adaptiveThreshold(gray, 255,
                   cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10)
        return thr, 2.0

    def scan(self, img):
        proc, sc = self._pre(img)
        data = pytesseract.image_to_data(proc,
            lang=config.OCR_LANG, config=config.OCR_CONFIG,
            output_type=pytesseract.Output.DICT)
        out = []
        for i in range(len(data["text"])):
            t = data["text"][i].strip()
            c = int(data["conf"][i])
            if not t or c < config.OCR_MIN_CONF:
                continue
            out.append(R(t,
                int(data["left"][i]/sc), int(data["top"][i]/sc),
                int(data["width"][i]/sc), int(data["height"][i]/sc), c))
        return out

    def find(self, img, targets, partial=True, results=None):
        if results is None:
            results = self.scan(img)
        for r in results:
            for tgt in targets:
                tl, rl = tgt.lower(), r.text.lower()
                if (tl in rl or rl in tl) if partial else tl == rl:
                    return r
        return None

    def find_all(self, img, targets, partial=True, results=None):
        if results is None:
            results = self.scan(img)
        found = []
        for r in results:
            for tgt in targets:
                tl, rl = tgt.lower(), r.text.lower()
                if not ((tl in rl or rl in tl) if partial else tl == rl):
                    continue
                if not any(abs(r.cx-f.cx) < 60 and abs(r.cy-f.cy) < 60 for f in found):
                    found.append(r)
                break
        return found

    def has(self, img, targets, partial=True, results=None):
        return self.find(img, targets, partial, results=results) is not None

    def full_text(self, img):
        proc, _ = self._pre(img)
        return pytesseract.image_to_string(proc,
            lang=config.OCR_LANG, config=config.OCR_CONFIG)

    # ── Lecture zones spécifiques ─────────────────────────────────

    def _pre_light(self, img):
        """Prétraitement pour texte blanc sur fond sombre — x2."""
        h, w = img.shape[:2]
        big  = cv2.resize(img, (w*2, h*2), interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
        inv  = cv2.bitwise_not(gray)
        _, thresh = cv2.threshold(inv, 100, 255, cv2.THRESH_BINARY)
        return thresh, 2.0

    def debug_topleft(self, img, path="/tmp/truck_topleft_debug.png"):
        """Sauvegarde la zone haut-gauche agrandie pour debug."""
        h, w = img.shape[:2]
        zone = img[0:int(h*0.06), 0:int(w*0.25)]
        big  = cv2.resize(zone, (zone.shape[1]*4, zone.shape[0]*4))
        cv2.imwrite(path, big)
        proc, _ = self._pre_light(zone)
        txt = pytesseract.image_to_string(proc,
            lang=config.OCR_LANG, config=config.OCR_CONFIG)
        return txt.strip()

    def read_cash(self, img):
        """
        Lit le cash ($XXX,XXX) en haut à gauche.
        Prend le plus grand montant trouvé pour éviter les faux positifs.
        """
        h, w = img.shape[:2]
        zone = img[0:int(h*0.06), 0:int(w*0.25)]
        proc, _ = self._pre_light(zone)
        txt = pytesseract.image_to_string(proc,
            lang=config.OCR_LANG, config=config.OCR_CONFIG)
        # Cherche tous les montants avec $
        matches = re.findall(r'\$([\d,]+)', txt)
        best = None
        for m in matches:
            try:
                val = float(m.replace(",", ""))
                if 100 < val < 100_000_000:
                    if best is None or val > best:
                        best = val
            except ValueError:
                pass
        return best

    def read_coins(self, img):
        """
        Lit les pièces dorées.
        Le texte brut donne '@ng Mr $189,608' — le 119 est mal lu.
        On cherche le cash d'abord, puis on cherche un nombre différent.
        """
        h, w = img.shape[:2]
        zone = img[0:int(h*0.06), 0:int(w*0.25)]
        proc, _ = self._pre_light(zone)
        txt = pytesseract.image_to_string(proc,
            lang=config.OCR_LANG, config=config.OCR_CONFIG)

        # Trouve d'abord le cash pour l'exclure
        cash_val = None
        m = re.search(r'\$([\d,]+)', txt)
        if m:
            try:
                cash_val = int(m.group(1).replace(",", ""))
            except ValueError:
                pass

        # Cherche tous les nombres
        all_nums = re.findall(r'\b(\d+)\b', txt.replace(",", ""))
        for n in all_nums:
            val = int(n)
            # Exclut le cash et ses parties, garde les petits nombres
            if cash_val and (val == cash_val or str(val) in str(cash_val)):
                continue
            if 1 <= val <= 9999:
                return val
        return None

    def detect_panel_state(self, img, results=None):
        """
        Détecte l'état via une zone dédiée au titre du panneau.
        Le titre est toujours dans la barre noire en haut à gauche.
        On scanne cette zone avec un seuil très bas.
        """
        import re as re2

        h, w = img.shape[:2]

        # Zone titre : barre noire tout en haut à gauche
        # En mode réduit  : x=0..270, y=50..90
        # En mode agrandi : x=0..270, y=50..90 (même position)
        zone_titre = img[int(h*0.04):int(h*0.10), 0:int(w*0.20)]

        # Scan avec seuil très bas
        proc, sc = self._pre(zone_titre)
        data = pytesseract.image_to_data(proc,
            lang=config.OCR_LANG, config=config.OCR_CONFIG,
            output_type=pytesseract.Output.DICT)

        titre_tokens = []
        for i in range(len(data["text"])):
            t = data["text"][i].strip()
            c = int(data["conf"][i])
            if t and c >= 20:
                titre_tokens.append(t.lower())

        titre = " ".join(titre_tokens)
        log.debug("Titre zone: %r", titre)

        if "repos" in titre:
            return "au_repos"
        if "route" in titre:
            return "en_route"
        if "gare" in titre or "garé" in titre:
            return "gare"
        if "attente" in titre:
            return "en_attente"

        # Fallback sur les résultats généraux
        if results is None:
            results = self.scan(img)

        if self.find(img, ["Au Repos"], results=results):
            return "au_repos"
        if self.find(img, ["Tout Envoyer", "Send All"], results=results):
            return "au_repos"
        if self.find(img, ["En Attente"], results=results):
            return "en_attente"
        if self.find(img, ["Garé"], results=results):
            return "gare"
        if self.find(img, ["En Route"], results=results):
            return "en_route"
        if self.find(img, ["Prêt dans", "Pret dans"], results=results):
            return "en_attente"
        if self.find(img, ["Progrès", "Terminé"], results=results):
            return "en_route"
        if (self.find(img, ["Emplacement"], results=results) and
                self.find(img, ["Statut"], results=results)):
            return "gare"

        # Timer visible = En Route
        for r in (results or []):
            if re2.match(r'^\d{1,3}:\d{2}:\d{2}$', r.text):
                return "en_route"

        return None

    def _pre_table(self, img):
        """
        Prétraitement pour le tableau du jeu.
        Screenshot déjà à 50% (960x600), donc on agrandit x2
        pour que Tesseract ait assez de résolution.
        Texte clair sur fond sombre → on inverse.
        """
        h, w = img.shape[:2]
        big  = cv2.resize(img, (w*2, h*2), interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
        inv  = cv2.bitwise_not(gray)
        _, thr = cv2.threshold(inv, 0, 255,
                               cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return thr, 2.0

    def read_subvention(self, img):
        """
        Lit la progression du Plan de Subventions.
        Ex: "$268,633/$1,250,000" → retourne (actuel, objectif, pct)
        """
        h, w = img.shape[:2]
        zone = img[0:int(h*0.08), int(w*0.30):int(w*0.75)]
        txt = self.full_text(zone)
        m = re.search(r'\$([\d,]+)\s*/\s*\$([\d,]+)', txt)
        if m:
            try:
                cur = float(m.group(1).replace(",", ""))
                obj = float(m.group(2).replace(",", ""))
                pct = (cur / obj * 100) if obj > 0 else 0
                return cur, obj, pct
            except ValueError:
                pass
        return None, None, None

    def parse_timer(self, text):
        """
        Convertit un timer "HH:MM:SS" en secondes.
        Retourne int ou None.
        """
        m = re.search(r'(\d{1,3}):(\d{2}):(\d{2})', text)
        if m:
            return int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3))
        return None

    # ── Lecture tableau agrandi ───────────────────────────────────

    def read_table_agrandi(self, img, etat):
        """
        Lit le tableau agrandi en parsant le texte brut ligne par ligne.
        Utilise image_to_string (plus robuste que image_to_data pour tableaux).
        """
        import re as re2

        h, w = img.shape[:2]
        y1 = int(h * 0.08)
        y2 = int(h * 0.47)
        zone = img[y1:y2, 0:int(w*0.95)]
        zone_h = y2 - y1

        proc, sc = self._pre_table(zone)
        txt = pytesseract.image_to_string(
            proc, lang=config.OCR_LANG,
            config="--psm 4 --oem 3")  # psm 4 = colonne de texte, mieux pour 1 ligne

        log.debug("read_table texte brut: %s", repr(txt[:300]))

        rows = []
        data_lines = []
        for line in txt.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            # Ignore en-têtes
            if re2.search(r'\bType\b|\bReg\b|\bUsure\b|\bItinéraire\b|\bItineraire\b',
                          line, re2.I):
                continue
            # Ligne valide = contient un % ou des jours
            if (re2.search(r'\d+[.,]\d+\s*%', line) or
                    re2.search(r'\d+\s*[jJ)\]]\b', line)):
                data_lines.append(line)

        log.debug("read_table: %d lignes données", len(data_lines))

        for idx, line in enumerate(data_lines):
            # Position Y dans l'image originale
            row_y = y1 + int(zone_h * (idx + 1.5) / max(len(data_lines), 1))

            row = {"row_y": row_y, "reg": None, "usure": None,
                   "ct_jours": None, "arrivee_s": None,
                   "pret_dans_s": None, "destination": None,
                   "itineraire": None}

            # Immatriculation — très assoupli car l'OCR fait beaucoup de confusions
            # On prend le premier token qui ressemble à une immat (min 5 chars alpanum)
            for token in re2.findall(r'\b([A-Z0-9]{5,8})\b', line.upper()):
                # Doit avoir au moins 2 lettres et 3 chiffres (dans n'importe quel ordre)
                if (re2.search(r'[A-Z]', token) and
                        re2.search(r'\d{3,}', token) and
                        len(token) >= 5):
                    row["reg"] = token
                    break
            if not row["reg"]:
                row["reg"] = f"CAM_{idx+1}"

            # Usure % — avec ou sans décimale
            # "3.1%" → 3.1, "300%" → 30.0 (OCR mange le point)
            m = re2.search(r'(\d{1,2})[.,](\d+)\s*%', line)
            if m:
                try:
                    val = float(f"{m.group(1)}.{m.group(2)}")
                    if 0 <= val <= 100:
                        row["usure"] = val
                except ValueError:
                    pass
            if row["usure"] is None:
                m = re2.search(r'\b(\d{1,3})\s*%', line)
                if m:
                    try:
                        val = int(m.group(1))
                        if val > 100:
                            val = val / 10.0  # "300%" → 30.0%
                        if 0 <= val <= 100:
                            row["usure"] = val
                    except ValueError:
                        pass
            if row["usure"] is None:
                # Sans décimale : "31%" = 3.1%, "22%" = 2.2%, "103%" = 10.3%
                # Heuristique : si >= 10 et <= 999 et se termine par % → divise par 10
                m = re2.search(r'\b(\d{2,3})\s*%', line)
                if m:
                    try:
                        raw = int(m.group(1))
                        if 10 <= raw <= 999:
                            val = raw / 10.0
                            if val <= 100:
                                row["usure"] = val
                    except ValueError:
                        pass

            # CT jours — l'OCR lit "j" comme ")", "]", "}" parfois
            m = re2.search(r'(\d{1,3})\s*[jJ)\]}\|]', line)
            if m:
                try:
                    val = int(m.group(1))
                    if 0 < val <= 365:
                        row["ct_jours"] = val
                except ValueError:
                    pass

            # Timer
            m = re2.search(r'(\d{1,3}):(\d{2}):(\d{2})', line)
            if m:
                secs = (int(m.group(1))*3600 +
                        int(m.group(2))*60 +
                        int(m.group(3)))
                if etat == "en_route":
                    row["arrivee_s"] = secs
                elif etat == "en_attente":
                    row["pret_dans_s"] = secs

            # Destination
            known = {"RAS","HAG","KEH","BAD","SAA","OFF","MUL","KAR",
                     "LYO","PAR","MAR","NAN","BOR","TOU","LIL","NIC",
                     "GRE","MON","REN","DIJ","MET","SXB"}
            for word in re2.findall(r'\b([A-Z]{3})\b', line.upper()):
                if word in known:
                    row["destination"] = word
                    break

            # Itinéraire
            if re2.search(r'\bLocal\b', line, re2.I):
                row["itineraire"] = "Local"
            elif re2.search(r'\bLigne\b', line, re2.I):
                row["itineraire"] = "Ligne"

            rows.append(row)
            log.info("  [%d] %s usure=%s CT=%s dest=%s y=%d",
                     idx+1, row["reg"], row["usure"],
                     row["ct_jours"], row["destination"], row_y)

        return rows

    def read_table_en_route(self, img):
        """
        Lecture dédiée du tableau En Route.
        Cherche uniquement les timers HH:MM:SS et les immatriculations.
        """
        import re as re2
        h, w = img.shape[:2]
        y1 = int(h * 0.08)
        y2 = int(h * 0.47)
        zone = img[y1:y2, 0:int(w*0.95)]
        zone_h = y2 - y1
        proc, sc = self._pre_table(zone)
        txt = pytesseract.image_to_string(
            proc, lang=config.OCR_LANG, config="--psm 6 --oem 3")
        log.debug("read_en_route brut: %s", repr(txt[:300]))
        rows = []
        data_lines = []
        for line in txt.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            if re2.search(r'\bType\b|\bReg\b|\bArrivée\b|\bProgrès\b', line, re2.I):
                continue
            if re2.search(r'\d{1,3}:\d{2}:\d{2}', line):
                data_lines.append(line)
        for idx, line in enumerate(data_lines):
            row_y = y1 + int(zone_h * (idx + 1.5) / max(len(data_lines), 1))
            m = re2.search(r'(\d{1,3}):(\d{2}):(\d{2})', line)
            if not m:
                continue
            secs = int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3))
            reg = None
            for token in re2.findall(r'\b([A-Z0-9]{5,8})\b', line.upper()):
                if re2.search(r'[A-Z]', token) and re2.search(r'\d{3,}', token):
                    reg = token
                    break
            if not reg:
                reg = f"CAM_{idx+1}"
            known = {"RAS","HAG","KEH","BAD","SAA","OFF","MUL","KAR",
                     "NEU","LYO","PAR","MAR","NAN","BOR","TOU","LIL"}
            dest = None
            for word in re2.findall(r'\b([A-Z]{3})\b', line.upper()):
                if word in known:
                    dest = word
                    break
            rows.append({
                "row_y": row_y, "reg": reg, "arrivee_s": secs,
                "destination": dest, "usure": None, "ct_jours": None,
                "pret_dans_s": None, "itineraire": None,
            })
            h2, m2, s2 = secs//3600, (secs%3600)//60, secs%60
            log.info("  [%d] %s → %s arrivée dans %02d:%02d:%02d",
                     idx+1, reg, dest or "?", h2, m2, s2)
        return rows

    def read_count_au_repos(self, img):
        """
        Détecte s'il y a des camions Au Repos disponibles.
        Si "Aucun véhicule n'est prêt" visible → retourne 0
        Sinon → retourne 1 (il y a des camions à envoyer)
        """
        results = self.scan(img)
        texts = " ".join(r.text.lower() for r in results)
        if "aucun" in texts and "prêt" in texts or "pret" in texts:
            return 0
        if "aucun véhicule" in texts or "aucun vehicule" in texts:
            return 0
        # Cherche aussi le bouton "Tout Envoyer"
        if self.find(img, ["Tout Envoyer", "Send All"], results=results):
            return 1
        return None
        """
        Lecture dédiée du tableau En Route.
        Cherche uniquement les timers HH:MM:SS et les immatriculations.
        """
        import re as re2

        h, w = img.shape[:2]
        y1 = int(h * 0.08)
        y2 = int(h * 0.47)
        zone = img[y1:y2, 0:int(w*0.95)]
        zone_h = y2 - y1

        proc, sc = self._pre_table(zone)
        txt = pytesseract.image_to_string(
            proc, lang=config.OCR_LANG, config="--psm 6 --oem 3")

        log.debug("read_en_route brut: %s", repr(txt[:300]))

        rows = []
        data_lines = []
        for line in txt.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            if re2.search(r'\bType\b|\bReg\b|\bArrivée\b|\bProgrès\b', line, re2.I):
                continue
            if re2.search(r'\d{1,3}:\d{2}:\d{2}', line):
                data_lines.append(line)

        for idx, line in enumerate(data_lines):
            row_y = y1 + int(zone_h * (idx + 1.5) / max(len(data_lines), 1))

            m = re2.search(r'(\d{1,3}):(\d{2}):(\d{2})', line)
            if not m:
                continue
            secs = int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3))

            reg = None
            for token in re2.findall(r'\b([A-Z0-9]{5,8})\b', line.upper()):
                if re2.search(r'[A-Z]', token) and re2.search(r'\d{3,}', token):
                    reg = token
                    break
            if not reg:
                reg = f"CAM_{idx+1}"

            known = {"RAS","HAG","KEH","BAD","SAA","OFF","MUL","KAR",
                     "NEU","LYO","PAR","MAR","NAN","BOR","TOU","LIL"}
            dest = None
            for word in re2.findall(r'\b([A-Z]{3})\b', line.upper()):
                if word in known:
                    dest = word
                    break

            rows.append({
                "row_y": row_y, "reg": reg, "arrivee_s": secs,
                "destination": dest, "usure": None, "ct_jours": None,
                "pret_dans_s": None, "itineraire": None,
            })
            h2, m2, s2 = secs//3600, (secs%3600)//60, secs%60
            log.info("  [%d] %s → %s arrivée dans %02d:%02d:%02d",
                     idx+1, reg, dest or "?", h2, m2, s2)

        return rows

    def is_entretien_screen(self, img):
        txt = self.full_text(img)
        keywords = ["Usure", "Sélectionner", "Réparation", "Masse CT", "Garantie"]
        hits = sum(1 for k in keywords if k.lower() in txt.lower())
        return hits >= 2

    def read_entretien_table(self, img):
        if not self.is_entretien_screen(img):
            return []
        results = self.scan(img)
        lines = {}
        for r in results:
            key = round(r.cy / 20) * 20
            lines.setdefault(key, []).append(r)

        rows = []
        for y_key in sorted(lines.keys()):
            items = lines[y_key]
            texts = " ".join(r.text for r in items)

            m_usure = re.search(r'(\d{1,3})[.,]?(\d*)\s*%', texts)
            if not m_usure:
                continue
            try:
                u = m_usure.group(1)
                if m_usure.group(2):
                    u += "." + m_usure.group(2)
                usure = float(u)
            except ValueError:
                continue

            if usure > 100:
                continue  # faux positif

            m_ct = re.search(r'(\d+)\s*d', texts)
            ct_jours = int(m_ct.group(1)) if m_ct else 999

            reg = None
            for r in items:
                if re.match(r'^[A-Z]{2,4}\d{3,4}$', r.text.upper()):
                    reg = r.text.upper()
                    break

            rows.append({"reg": reg or "?", "usure": usure,
                         "ct_jours": ct_jours, "row_y": y_key})
        return rows

    # ── Lecture ressources ────────────────────────────────────────

    def read_resource_level(self, img):
        txt = self.full_text(img)
        m = re.search(r'([\d,]+)\s*(?:l|kWh|kg)\s*[\n\r\s]+([\d,]+)', txt)
        if m:
            try:
                cur = float(m.group(1).replace(",", ""))
                mx  = float(m.group(2).replace(",", ""))
                pct = (cur / mx * 100) if mx > 0 else 100
                return cur, mx, pct
            except ValueError:
                pass
        return None, None, None

    def annotate(self, img, results=None, path="/tmp/truck_ocr_debug.png"):
        if results is None:
            results = self.scan(img)
        out = img.copy()
        for r in results:
            col = (0, 200, 0) if r.conf >= 70 else (0, 140, 255)
            cv2.rectangle(out, (r.x, r.y), (r.x+r.w, r.y+r.h), col, 1)
            cv2.putText(out, f"{r.text}({r.conf})", (r.x, max(r.y-3, 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, col, 1)
        cv2.imwrite(path, out)
        log.info("🖼️  Debug : %s", path)
        return path
