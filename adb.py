"""Couche ADB — connexion USB/WiFi, screenshot, tap, swipe."""

import subprocess, time, io, logging, sys
import config

log = logging.getLogger("TruckBot.ADB")
ADB_TIMEOUT = 15

try:
    from PIL import Image
    import numpy as np
    import cv2
except ImportError:
    print("❌ pip3 install pillow opencv-python-headless numpy")
    sys.exit(1)


class ADB:
    def __init__(self):
        self.device = None
        self._w = None
        self._h = None

    def connect_usb(self):
        out = self._run(["adb", "devices"])
        lines = [l for l in out.splitlines() if "\tdevice" in l]
        if not lines:
            return False
        self.device = lines[0].split("\t")[0]
        log.info("✅ USB : %s", self.device)
        return True

    def connect_wifi(self, ip, port=5555):
        addr = f"{ip}:{port}"
        out  = self._run(["adb", "connect", addr])
        if "connected" in out.lower():
            self.device = addr
            log.info("✅ WiFi : %s", self.device)
            return True
        return False

    def auto_connect(self):
        log.info("🔌 Connexion USB...")
        if self.connect_usb():
            self._detect_resolution()
            return True
        if config.DEVICE and "." in str(config.DEVICE):
            if self.connect_wifi(config.DEVICE, config.WIFI_PORT):
                self._detect_resolution()
                return True
        log.error("Aucune tablette trouvée.")
        return False

    def reconnect(self):
        log.warning("🔄 Reconnexion...")
        self._run(["adb", "kill-server"])
        time.sleep(2)
        self._run(["adb", "start-server"])
        time.sleep(1)
        return self.auto_connect()

    def _detect_resolution(self):
        """Détecte la résolution réelle de la tablette."""
        out = self._adb("shell", "wm", "size")
        for part in out.split():
            if "x" in part.lower():
                try:
                    w, h = part.lower().split("x")
                    self._w, self._h = int(w), int(h)
                    # Si portrait, on inverse (le jeu tourne en paysage)
                    if self._h > self._w:
                        self._w, self._h = self._h, self._w
                    log.info("📐 Résolution : %dx%d", self._w, self._h)
                    return
                except Exception:
                    pass

    @property
    def width(self):
        return self._w or 1384

    @property
    def height(self):
        return self._h or 862

    def _run(self, cmd, timeout=ADB_TIMEOUT):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return r.stdout.strip()
        except subprocess.TimeoutExpired:
            log.warning("Timeout ADB")
            return ""
        except FileNotFoundError:
            log.error("ADB introuvable ! sudo apt install adb -y")
            raise

    def _adb(self, *args, timeout=ADB_TIMEOUT):
        cmd = ["adb", "-s", self.device] + list(args) if self.device else ["adb"] + list(args)
        return self._run(cmd, timeout=timeout)

    def screenshot(self):
        try:
            r = subprocess.run(
                ["adb", "-s", self.device, "exec-out", "screencap", "-p"],
                capture_output=True, timeout=ADB_TIMEOUT
            )
            if not r.stdout:
                return None
            img = Image.open(io.BytesIO(r.stdout)).convert("RGB")
            arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            h, w = arr.shape[:2]
            if h > w:
                arr = cv2.rotate(arr, cv2.ROTATE_90_CLOCKWISE)
                h, w = arr.shape[:2]
            # Réduit à 50% → 960x600, divise le load OCR par ~4
            arr = cv2.resize(arr, (w//2, h//2), interpolation=cv2.INTER_LINEAR)
            return arr
        except Exception as e:
            log.error("Screenshot : %s", e)
            return None

    def save_screenshot(self, path="/tmp/truck_debug.png"):
        s = self.screenshot()
        if s is not None:
            cv2.imwrite(path, s)
            log.info("📸 %s", path)
        return s

    def tap(self, x, y):
        """Tap en coordonnées du screenshot réduit → converti en natif x2."""
        real_x = int(x * 2)
        real_y = int(y * 2)
        self._adb("shell", "input", "tap", str(real_x), str(real_y))
        log.debug("👆 tap(%d,%d) → natif(%d,%d)", x, y, real_x, real_y)
        time.sleep(0.4)

    def swipe(self, x1, y1, x2, y2, ms=400):
        """Swipe en coordonnées du screenshot réduit → converti en natif x2."""
        self._adb("shell", "input", "swipe",
                  str(int(x1*2)), str(int(y1*2)),
                  str(int(x2*2)), str(int(y2*2)), str(ms))
        time.sleep(0.5)

    def back(self):
        self._adb("shell", "input", "keyevent", "4")
        time.sleep(0.4)

    def screen_on(self):
        info = self._adb("shell", "dumpsys", "power")
        if "mWakefulness=Asleep" in info or "mWakefulness=Dozing" in info:
            self._adb("shell", "input", "keyevent", "26")
            time.sleep(1)

    def launch_app(self, package=None):
        pkg = package or config.APP_PACKAGE
        self._adb("shell", "monkey", "-p", pkg,
                  "-c", "android.intent.category.LAUNCHER", "1")
        log.info("🚀 Lancement : %s", pkg)
        time.sleep(6)

    def is_app_foreground(self, package=None):
        pkg = package or config.APP_PACKAGE
        out = self._adb("shell", "dumpsys", "activity", "activities")
        return pkg in out
