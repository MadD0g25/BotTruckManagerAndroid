"""
Gestion des timers d'itinéraires.
Le bot note l'heure d'arrivée de chaque camion et sait
exactement quand revenir pour les relancer.
"""

import json, os, time, logging
from datetime import datetime

log = logging.getLogger("TruckBot.Timers")
TIMER_FILE = "timers.json"


class TimerManager:
    def __init__(self):
        self.timers = self._load()

    def _load(self):
        if os.path.exists(TIMER_FILE):
            try:
                with open(TIMER_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self):
        try:
            with open(TIMER_FILE, "w") as f:
                json.dump(self.timers, f, indent=2)
        except Exception as e:
            log.warning("Impossible de sauvegarder timers : %s", e)

    def set_timer(self, truck_id, seconds_remaining):
        """
        Enregistre l'heure d'arrivée prévue d'un camion.
        truck_id : immatriculation ou index (ex: "MFL7223")
        seconds_remaining : secondes avant arrivée lues sur l'écran
        """
        arrival = time.time() + seconds_remaining
        self.timers[truck_id] = {
            "arrival":  arrival,
            "arrival_human": datetime.fromtimestamp(arrival).strftime("%H:%M:%S"),
            "set_at":   time.time(),
        }
        self._save()
        log.info("⏱️  Timer %s : arrivée dans %ds (%s)",
                 truck_id,
                 seconds_remaining,
                 self.timers[truck_id]["arrival_human"])

    def get_arrived(self):
        """
        Retourne la liste des truck_id dont le timer est expiré.
        """
        now     = time.time()
        arrived = [tid for tid, t in self.timers.items() if t["arrival"] <= now]
        return arrived

    def clear(self, truck_id):
        """Supprime le timer d'un camion (après relance)."""
        if truck_id in self.timers:
            del self.timers[truck_id]
            self._save()

    def clear_all(self):
        self.timers = {}
        self._save()

    def next_arrival(self):
        """
        Retourne le nombre de secondes avant la prochaine arrivée.
        Utile pour adapter le CYCLE_DELAY dynamiquement.
        """
        now = time.time()
        futures = [t["arrival"] - now
                   for t in self.timers.values()
                   if t["arrival"] > now]
        return min(futures) if futures else None

    def status(self):
        """Affiche l'état de tous les timers (pour les logs)."""
        now = time.time()
        lines = []
        for tid, t in self.timers.items():
            remaining = t["arrival"] - now
            if remaining > 0:
                h = int(remaining // 3600)
                m = int((remaining % 3600) // 60)
                s = int(remaining % 60)
                lines.append(f"  {tid}: arrivée dans {h:02d}:{m:02d}:{s:02d}")
            else:
                lines.append(f"  {tid}: ARRIVÉ ✅")
        return "\n".join(lines) if lines else "  Aucun timer actif"
