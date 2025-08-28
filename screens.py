#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-screen video/playlist launcher in Python (Windows & Linux)

Este script abre *listas de reproducción* o videos en monitores específicos en pantalla completa.
Soporta archivos .m3u/.m3u8/.xspf, directorios con videos o un solo archivo de video.

Dependencias (instalar primero):
  pip install python-vlc screeninfo

Controles:
  ESC – cierra todos los reproductores y termina el script.
"""

import os
import sys
import time
import threading
import pathlib
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, unquote
from dataclasses import dataclass
from typing import List

from screeninfo import get_monitors
import vlc  # python-vlc
import tkinter as tk

@dataclass
class Assignment:
    path: str   # puede ser archivo de video, playlist (.m3u/.m3u8/.xspf) o directorio
    screen: int # pantalla destino (1-based)

# === CONFIGURACIÓN AQUÍ ===
# Ejemplos:
# - Archivo de playlist XSPF: "pantalla1.xspf"
# - Archivo de playlist M3U:  "lista.m3u8"
# - Directorio con videos:    "C:/videos/loop1"
# - Archivo de video:         "intro.mp4"
ASSIGNMENTS = [
    Assignment(path="pantalla1.xspf", screen=1),
    Assignment(path="Screen Recording 2025-06-13 095615.mp4", screen=2),

]

# Extensiones soportadas
VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.m4v', '.webm'}
PLAYLIST_EXTS = {'.m3u', '.m3u8', '.xspf'}

# Reproducción en bucle (playlist loop)
LOOP_PLAYLIST = True
SHUFFLE_PLAYLIST = False  # si se quiere aleatorio, activar esto

def is_video_file(p: pathlib.Path) -> bool:
    return p.suffix.lower() in VIDEO_EXTS

def is_playlist_file(p: pathlib.Path) -> bool:
    return p.suffix.lower() in PLAYLIST_EXTS

def parse_m3u(m3u_path: pathlib.Path) -> List[str]:
    items = []
    try:
        with m3u_path.open('r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # Rutas relativas respecto al archivo .m3u
                candidate = (m3u_path.parent / line).resolve() if not os.path.isabs(line) else pathlib.Path(line)
                items.append(str(candidate))
    except Exception as e:
        print(f"[!] Error al leer M3U '{m3u_path}': {e}")
    return items

def parse_xspf(xspf_path: pathlib.Path) -> List[str]:
    items = []
    try:
        tree = ET.parse(str(xspf_path))
        root = tree.getroot()
        # Namespace XSPF
        ns = {'x': 'http://xspf.org/ns/0/'}
        for loc in root.findall('.//x:track/x:location', ns):
            url = loc.text or ''
            # Normalmente viene como file:///C:/ruta%20con%20espacios.mp4
            parsed = urlparse(url)
            if parsed.scheme in ('file', ''):
                path = unquote(parsed.path)
                # En Windows, urlparse de file:///C:/... deja path como /C:/..., normalizamos:
                if os.name == 'nt' and path.startswith('/'):
                    path = path[1:]
                candidate = pathlib.Path(path)
                if not candidate.is_absolute():
                    candidate = (xspf_path.parent / candidate).resolve()
                items.append(str(candidate))
            else:
                # Si es http(s), VLC puede reproducir streams; los dejamos tal cual
                items.append(url)
    except Exception as e:
        print(f"[!] Error al leer XSPF '{xspf_path}': {e}")
    return items

def scan_directory(dir_path: pathlib.Path) -> List[str]:
    try:
        files = sorted([p for p in dir_path.iterdir() if p.is_file() and is_video_file(p)])
        return [str(p.resolve()) for p in files]
    except Exception as e:
        print(f"[!] Error al escanear directorio '{dir_path}': {e}")
        return []

def resolve_playlist_sources(source_path: str) -> List[str]:
    """
    Devuelve una lista de rutas (o URLs) reproducibles por VLC.
    Acepta: archivo de video, playlist .m3u/.m3u8/.xspf o directorio.
    """
    p = pathlib.Path(source_path).expanduser()
    if not p.exists():
        print(f"[!] Fuente no encontrada: {p}")
        return []

    if p.is_dir():
        items = scan_directory(p)
        if not items:
            print(f"[!] No se encontraron videos en '{p}'.")
        return items

    if p.is_file():
        if is_playlist_file(p):
            if p.suffix.lower() in ('.m3u', '.m3u8'):
                items = parse_m3u(p)
            else:
                items = parse_xspf(p)
            if not items:
                print(f"[!] La playlist '{p}' está vacía o no fue posible leerla.")
            return items
        elif is_video_file(p):
            return [str(p.resolve())]
        else:
            print(f"[!] Extensión no soportada: {p.suffix}")
            return []

    print(f"[!] Ruta inválida: {p}")
    return []

class EmbeddedVLC:
    def __init__(self, root: tk.Tk, mon, source_path: str):
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes('-topmost', True)
        self.top.geometry(f"{mon.width}x{mon.height}+{mon.x}+{mon.y}")

        self.frame = tk.Frame(self.top, bg='black')
        self.frame.pack(fill='both', expand=True)

        # En Linux, evitar conflictos con Xlib
        self.instance = vlc.Instance('--no-xlib') if sys.platform.startswith('linux') else vlc.Instance()

        # Preparar lista de medios
        items = resolve_playlist_sources(source_path)
        if not items:
            raise RuntimeError(f"No hay elementos reproducibles para: {source_path}")

        self.media_list = self.instance.media_list_new(items)

        # Crear player embebido + list player
        self.player = self.instance.media_player_new()
        self.list_player = self.instance.media_list_player_new()
        self.list_player.set_media_list(self.media_list)
        self.list_player.set_media_player(self.player)

        # Loop / shuffle
        if SHUFFLE_PLAYLIST:
            self.list_player.set_playback_mode(vlc.PlaybackMode.random)
        elif LOOP_PLAYLIST:
            self.list_player.set_playback_mode(vlc.PlaybackMode.loop)
        else:
            self.list_player.set_playback_mode(vlc.PlaybackMode.default)

        # Vincular ventana
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
        # Iniciar reproducción de la lista
        self.list_player.play()
        time.sleep(0.2)
        # Forzar fullscreen (algunos WMs necesitan un pequeño delay)
        try:
            self.player.set_fullscreen(True)
        except Exception:
            pass

    def stop(self):
        try:
            self.list_player.stop()
        except Exception:
            pass
        try:
            self.player.release()
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

def embed_and_play(assignments: List[Assignment]):
    mons = list_monitors()
    def monitor_for(idx: int):
        if idx < 1 or idx > len(mons):
            raise IndexError(f"Pantalla {idx} fuera de rango. Solo hay {len(mons)} monitor(es).")
        return mons[idx - 1]

    root = tk.Tk()
    root.withdraw()

    players: List[EmbeddedVLC] = []
    try:
        for a in assignments:
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
