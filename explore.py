"""
╔══════════════════════════════════════════════════════════════════╗
║   EXPLORE v3 — Outil de diagnostic amélioré                    ║
╚══════════════════════════════════════════════════════════════════╝

Usage :
    python3 explore.py              → rafraîchit toutes les 5s
    python3 explore.py --once       → une seule lecture
    python3 explore.py --debug      → sauvegarde image annotée
    python3 explore.py --tableau    → lit le tableau agrandi
    python3 explore.py --ressources → lit les niveaux des jauges
    python3 explore.py --full       → tout afficher
"""

import sys, time, argparse
from adb import ADB
from ocr import OCR
from timers import TimerManager
import config


def afficher_tableau(ocr, s, etat):
    rows = ocr.read_table_agrandi(s, etat)
    if not rows:
        print("  ⚠️  Aucune ligne détectée dans le tableau")
        return

    if etat == "en_route":
        timer_col = "Arrivée"
    elif etat == "en_attente":
        timer_col = "Prêt dans"
    else:
        timer_col = "Temps"

    print(f"\n  📊 Tableau '{etat}' — {len(rows)} camion(s) :")
    print(f"  {'Reg':<12} {'Usure':>7} {'CT':>5} {'Dest':>5} {timer_col:>10} {'Itin':<8}")
    print(f"  {'─'*12} {'─'*7} {'─'*5} {'─'*5} {'─'*10} {'─'*8}")
    for row in rows:
        usure  = f"{row['usure']:.1f}%"   if row['usure']   is not None else "?"
        ct     = f"{row['ct_jours']}j"    if row['ct_jours'] is not None else "?"
        dest   = row.get('destination')   or "-"
        itin   = row.get('itineraire')    or "-"
        arr    = row.get('arrivee_s')
        pret   = row.get('pret_dans_s')
        timer  = "-"
        if arr is not None:
            h,m,s2 = arr//3600, (arr%3600)//60, arr%60
            timer  = f"{h:02d}:{m:02d}:{s2:02d}"
        elif pret is not None:
            h,m,s2 = pret//3600, (pret%3600)//60, pret%60
            timer  = f"{h:02d}:{m:02d}:{s2:02d}"

        flag = ""
        if row['usure'] and row['usure'] >= config.USURE_SEUIL:
            flag = " ⚠️ USURE"
        if row['ct_jours'] and row['ct_jours'] <= config.CT_JOURS_SEUIL:
            flag += " ⚠️ CT"

        print(f"  {row['reg'] or '?':<12} {usure:>7} {ct:>5} {dest:>5} {timer:>10} {itin:<8}{flag}")


def main():
    p = argparse.ArgumentParser(description="Diagnostic Truck Manager Bot v3")
    p.add_argument("--once",       action="store_true", help="Une seule lecture")
    p.add_argument("--debug",      action="store_true", help="Sauvegarde image annotée OCR")
    p.add_argument("--tableau",    action="store_true", help="Lit le tableau agrandi")
    p.add_argument("--ressources", action="store_true", help="Lit les niveaux des jauges")
    p.add_argument("--full",       action="store_true", help="Tout afficher")
    p.add_argument("--interval",   type=float, default=5.0, help="Intervalle en secondes")
    args = p.parse_args()

    adb    = ADB()
    if not adb.auto_connect():
        print("❌ Tablette non connectée")
        sys.exit(1)

    ocr    = OCR()
    timers = TimerManager()

    print(f"\n✅ Connecté ({adb.width}x{adb.height}) → screenshots 960x600 (50%)")
    print(f"   Ctrl+C pour arrêter\n")

    while True:
        s = adb.screenshot()
        if s is None:
            print("❌ Screenshot échoué")
            time.sleep(2)
            continue

        print("\n" + "═"*65)
        print(f"  DIAGNOSTIC — Cycle")
        print("═"*65)

        # ── Cash et pièces ──────────────────────────────────────
        cash  = ocr.read_cash(s)
        coins = ocr.read_coins(s)
        subv  = ocr.read_subvention(s)
        print(f"\n  💰 Cash   : {'$'+f'{cash:,.0f}' if cash else '?'}")
        print(f"  🪙 Pièces : {coins if coins is not None else '?'}")

        # Debug zone haut-gauche si cash non détecté
        if cash is None or coins is None:
            topleft_txt = ocr.debug_topleft(s, "/tmp/truck_topleft_debug.png")
            print(f"  ⚠️  Zone haut-gauche OCR brut : {repr(topleft_txt[:100])}")
            print(f"       Image agrandie : /tmp/truck_topleft_debug.png")
        if subv[0] is not None:
            print(f"  📋 Subvention : ${subv[0]:,.0f} / ${subv[1]:,.0f} ({subv[2]:.1f}%)")

        # ── État panneau ────────────────────────────────────────
        results_scan = ocr.scan(s)
        # Debug : affiche le texte brut de la zone titre
        import pytesseract as _pt
        h_s, w_s = s.shape[:2]
        zone_t = s[int(h_s*0.04):int(h_s*0.10), 0:int(w_s*0.20)]
        proc_t, _ = ocr._pre(zone_t)
        titre_brut = _pt.image_to_string(proc_t, lang=config.OCR_LANG,
                                          config=config.OCR_CONFIG).strip()
        print(f"\n  🏷️  Zone titre brut : {repr(titre_brut[:60])}")
        etat = ocr.detect_panel_state(s, results=results_scan)
        print(f"\n  📊 État panneau : {etat or '? (non détecté)'}")

        # ── Tableau agrandi ─────────────────────────────────────
        if args.tableau or args.full:
            if etat:
                afficher_tableau(ocr, s, etat)
            else:
                print("  ⚠️  État non détecté, impossible de lire le tableau")

        # ── Mots OCR bruts ──────────────────────────────────────
        if args.full:
            results = ocr.scan(s)
            print(f"\n  🔍 Mots OCR ({len(results)} détectés) :")
            for r in sorted(results, key=lambda r: r.cy):
                bar = "█" * (r.conf // 10)
                print(f"    [{r.conf:3d}%] {bar:<10} {r.text!r:35} @({r.cx:4d},{r.cy:4d})")

        # ── Correspondances textes config ───────────────────────
        results = ocr.scan(s)
        words = {r.text.lower() for r in results}
        hits = {}
        for grp, tgts in config.TEXTS.items():
            found = [t for t in tgts
                     if any(t.lower() in w or w in t.lower() for w in words)]
            if found:
                hits[grp] = found
        if hits:
            print(f"\n  ✅ Textes reconnus ({len(hits)}) :")
            for grp, found in hits.items():
                print(f"    {grp:<25} → {found}")

        # ── Ressources ──────────────────────────────────────────
        if args.ressources or args.full:
            print(f"\n  ⛽ Jauges (clic aux coordonnées) :")
            for label, coords in [
                ("Diesel", config.COORDS_DIESEL),
                ("kWh",    config.COORDS_KWH),
                ("CO2",    config.COORDS_CO2),
            ]:
                print(f"    {label} → tap({coords[0]}, {coords[1]})")

        # ── Timers ──────────────────────────────────────────────
        if timers.timers:
            print(f"\n  ⏱️  Timers actifs :")
            for line in timers.status().splitlines():
                print(f"  {line}")
        else:
            print(f"\n  ⏱️  Aucun timer actif")

        # ── Garage entretien ────────────────────────────────────
        if ocr.is_entretien_screen(s):
            rows = ocr.read_entretien_table(s)
            if rows:
                print(f"\n  🔧 Tableau Entretien ({len(rows)} camions) :")
                for row in rows:
                    flag = " ⚠️ RÉPARER" if row['usure'] >= config.USURE_SEUIL else ""
                    flag += " ⚠️ CT" if row['ct_jours'] <= config.CT_JOURS_SEUIL else ""
                    print(f"    {row['reg']:<10} usure={row['usure']:5.1f}% "
                          f"CT={row['ct_jours']}j  y={row['row_y']}{flag}")

        # ── Debug image annotée ─────────────────────────────────
        if args.debug or args.full:
            results_all = ocr.scan(s)
            path = ocr.annotate(s, results_all)
            print(f"\n  🖼️  Image annotée : {path}")
            print(f"       scp pi@<IP_PI>:{path} .")

        print("═"*65)

        if args.once:
            break
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n🛑 Arrêté.")
            break


if __name__ == "__main__":
    main()
