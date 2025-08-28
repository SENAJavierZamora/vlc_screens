#!/usr/bin/env python3
"""
Multi‑screen video launcher in Python (Windows & Linux)

Este script abre videos en monitores específicos en pantalla completa.

Dependencias (instalar primero):
  pip install python-vlc screeninfo

Controles
  ESC – cierra todos los reproductores y termina el script.
"""

import os
import sys
import time
import threading
from dataclasses import dataclass

from screeninfo import get_monitors
import vlc  # python-vlc
import tkinter as tk

@dataclass
class Assignment:
    path: str
    screen: int

# === CONFIGURACIÓN AQUÍ ===

ASSIGNMENTS = [
    Assignment(path="", screen=1),
    Assignment(path="", screen=2),

]


class EmbeddedVLC:
    def __init__(self, root: tk.Tk, mon, media_path: str):
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes('-topmost', True)
        self.top.geometry(f"{mon.width}x{mon.height}+{mon.x}+{mon.y}")

        self.frame = tk.Frame(self.top, bg='black')
        self.frame.pack(fill='both', expand=True)

        self.instance = vlc.Instance('--no-xlib') if sys.platform.startswith('linux') else vlc.Instance()
        self.player = self.instance.media_player_new()
        media = self.instance.media_new_path(os.path.abspath(media_path))
        self.player.set_media(media)

        self.top.update_idletasks()
        wid = self.frame.winfo_id()
        if sys.platform.startswith('linux'):
            self.player.set_xwindow(wid)
        elif sys.platform == 'win32':
            self.player.set_hwnd(wid)
        elif sys.platform == 'darwin':
            raise RuntimeError("Modo embebido no soportado en macOS. Usa mpv o VLC externo.")

        self.top.focus_set()

    def play(self):
        self.player.play()
        time.sleep(0.1)
        self.player.set_fullscreen(True)

    def stop(self):
        try:
            self.player.stop()
        except Exception:
            pass
        try:
            self.top.destroy()
        except Exception:
            pass

def list_monitors():
    try:
        mons = get_monitors()
        if not mons:
            print("[!] No se detectaron monitores.")
            sys.exit(2)
        return mons
    except Exception as e:
        print(f"[!] Error al obtener monitores: {e}")
        sys.exit(1)

def embed_and_play(assignments: list[Assignment]):
    mons = list_monitors()
    def monitor_for(idx: int):
        if idx < 1 or idx > len(mons):
            raise IndexError(f"Pantalla {idx} fuera de rango. Solo hay {len(mons)} monitor(es).")
        return mons[idx - 1]

    root = tk.Tk()
    root.withdraw()

    players: list[EmbeddedVLC] = []
    try:
        for a in assignments:
            if not os.path.isfile(a.path):
                print(f"[!] Archivo no encontrado: {a.path}")
                continue
            mon = monitor_for(a.screen)
            p = EmbeddedVLC(root, mon, a.path)
            players.append(p)

        threads = []
        for p in players:
            t = threading.Thread(target=p.play, daemon=True)
            t.start()
            threads.append(t)
    except Exception as e:
        print(f"[!] Error al iniciar reproductores: {e}")
        for p in players:
            p.stop()
        sys.exit(1)

    def on_escape(event=None):
        for pl in players:
            pl.stop()
        root.quit()

    root.bind_all('<Escape>', on_escape)

    try:
        root.mainloop()
    finally:
        for p in players:
            p.stop()

def main():
    embed_and_play(ASSIGNMENTS)

if __name__ == '__main__':
    main()
