#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import shutil
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

# ---------- core renamer logic (unchanged behavior) ----------

DASH_SPLIT = re.compile(r"\s*-\s*")  # tolerant: " - ", " -", "- ", "-"

CORE_SET = {
    "Bass","Electric_Piano","Guitar","Lead","Strings","Choir","Clavi",
    "Piano","Organ","Pad","Pluck","Arp","Brass","Synth","Vibraphone",
    "Full","Flute","Bell","Glockenspiel","Horns"
}

INSTRUMENT_MAP = {
    # Bass family
    "Bassline": "Bass", "Bass Line": "Bass", "Electric Bass": "Bass",
    "Upright Bass": "Bass", "Sub Bass": "Bass", "Bass": "Bass",

    # Electric piano family → Electric_Piano
    "Rhodes": "Electric_Piano", "E. Piano": "Electric_Piano", "EP": "Electric_Piano",
    "Electric Piano": "Electric_Piano", "Rhodes Piano": "Electric_Piano",

    # straight cores
    "Piano": "Piano", "Grand Piano": "Piano",
    "Guitar": "Guitar", "Electric Guitar": "Guitar", "Acoustic Guitar": "Guitar",
    "Lead": "Lead", "Strings": "Strings", "String": "Strings",
    "Choir": "Choir", "Clavi": "Clavi", "Organ": "Organ",
    "Pad": "Pad", "Pluck": "Pluck", "Arp": "Arp", "Brass": "Brass",
    "Synth": "Synth", "Vibraphone": "Vibraphone", "Vibes": "Vibraphone",
    "Flute": "Flute", "Bell": "Bell",

    # requested normalizations
    "Horn": "Horns", "Horns": "Horns",
    "Glock": "Glockenspiel", "Glockenspiel": "Glockenspiel",

    "Full": "Full",
}

def canon_core(token: str) -> str:
    for k, v in INSTRUMENT_MAP.items():
        if token.lower() == k.lower():
            return v
    return token.title()

def normalize_instrument_phrase(phrase: str):
    """
    Generic adjective extractor:
    - LAST token is candidate core; if it maps to a known core, everything before it is adjective.
    - Electric_Piano family (Rhodes / EP / Electric Piano) → core Electric_Piano; prefix becomes adjective.
    Returns (core, adjective).
    """
    s = re.sub(r"\s+", " ", phrase).strip()

    # Electric_Piano family special handling
    m = re.search(r"(?i)\b(rhodes|e\.?\s*piano|^ep$|electric\s+piano)\b", s)
    if m:
        before = s[:m.start()].strip()
        adj = before.title() if before else ""
        return ("Electric_Piano", adj)

    tokens = s.split()
    if not tokens:
        return ("Full", "")
    if len(tokens) == 1:
        return (canon_core(tokens[0]), "")

    core_candidate = canon_core(tokens[-1])
    if core_candidate in CORE_SET:
        adj = " ".join(tokens[:-1]).title()
        return (core_candidate, adj)

    whole = canon_core(s)
    if whole in CORE_SET:
        return (whole, "")
    return (whole, "")

def parse_comp_folder(folder_name: str):
    parts = DASH_SPLIT.split(folder_name)
    comp = parts[0].strip() if parts else folder_name.strip()
    key = parts[1].strip() if len(parts) >= 2 else None
    bpm = None
    if len(parts) >= 3:
        raw_bpm = parts[2].strip()
        m = re.search(r"(\d+(?:\.\d+)?)", raw_bpm)
        bpm = f"{m.group(1)}bpm" if m else raw_bpm.replace("BPM","bpm").replace("Bpm","bpm")
    return comp, key, bpm

def guess_instrument_from_filename(filename: str, comp_name: str):
    stem = Path(filename).stem
    if stem.lower().startswith(comp_name.lower()):
        remainder = re.sub(r"^\s*-\s*", "", stem[len(comp_name):])
        instrument_raw = remainder if remainder else "Full"
    else:
        instrument_raw = stem
    instrument_raw = re.sub(r"\s+", " ", instrument_raw).strip()
    return normalize_instrument_phrase(instrument_raw)

def pack_abbrev_from_parent(parent_dir: Path) -> str:
    name = parent_dir.name
    parts = DASH_SPLIT.split(name, maxsplit=1)
    pack_raw = parts[1] if len(parts) > 1 else name
    pack_raw = re.sub(r"(?i)^pelham\s*(?:&|and)\s*junior\s*", "", pack_raw).strip()
    return pack_raw.replace(" ", "")

def process_folder(selected_path: str, on_progress=None):
    """
    on_progress: optional callback taking (phase_text, count_done, count_total)
    """
    source_dir = Path(selected_path).expanduser().resolve()
    if not source_dir.exists() or not source_dir.is_dir():
        raise RuntimeError(f"Path not found or not a directory: {source_dir}")

    parent_dir = source_dir.parent
    pack_abbrev = pack_abbrev_from_parent(parent_dir)

    dst_dir = parent_dir / f"_{source_dir.name}"
    dst_dir.mkdir(exist_ok=True)

    LABEL = "P&J"

    # count total wavs for a simple progress indicator
    subfolders = sorted([p for p in source_dir.iterdir() if p.is_dir()])
    wavs = []
    for comp_folder in subfolders:
        wavs += [p for p in comp_folder.iterdir() if p.suffix.lower() == ".wav"]
    total = len(wavs) if wavs else 1  # avoid division by zero

    done = 0
    if on_progress:
        on_progress("Preparing…", done, total)

    for comp_folder in subfolders:
        comp_name, key, bpm = parse_comp_folder(comp_folder.name)
        (dst_dir / comp_folder.name).mkdir(parents=True, exist_ok=True)

        for wav in sorted([p for p in comp_folder.iterdir() if p.suffix.lower() == ".wav"]):
            core, adj = guess_instrument_from_filename(wav.name, comp_name)

            bpm_final = bpm
            if bpm_final is None:
                m = re.search(r"(\d+(?:\.\d+)?)(?:\s*)BPM", wav.name, flags=re.IGNORECASE)
                bpm_final = f"{m.group(1)}bpm" if m else "bpm"

            key_final = key if key else ""
            descriptor = comp_name

            parts = [LABEL, pack_abbrev, bpm_final, core]
            if adj:
                parts.append(adj)
            parts.append(descriptor)
            if key_final:
                parts.append(key_final)

            # no spaces in any token
            parts = [p.replace(" ", "_") for p in parts]
            new_name = "_".join(parts) + ".wav"

            shutil.copyfile(wav, (dst_dir / comp_folder.name / new_name))

            done += 1
            if on_progress:
                on_progress("Renaming…", done, total)

# ---------- GUI ----------

class RenamoratorGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("P&JxFL File Renamorator 3000")
        self.root.resizable(False, False)

        self.selected_path = tk.StringVar(value="")
        self.status_text = tk.StringVar(value="")
        self.error_text = tk.StringVar(value="")
        self.progress_value = tk.IntVar(value=0)
        self.progress_total = 1

        outer = tk.Frame(self.root, padx=16, pady=16)
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text="P&JxFL File Renamorator 3000", font=("Helvetica", 16, "bold")).pack(anchor="w")
        tk.Label(outer, text="Select Comp Folder:", pady=10).pack(anchor="w")

        # Row: Choose Folder button + path label
        row = tk.Frame(outer)
        row.pack(fill="x", anchor="w")
        self.btn_choose = tk.Button(row, text="Choose Folder", width=18, command=self.choose_folder)
        self.btn_choose.pack(side="left")
        self.path_label = tk.Label(row, textvariable=self.selected_path, anchor="w", fg="#666666", wraplength=500, justify="left")
        self.path_label.pack(side="left", padx=10)

        # Rename button (shown after folder selected)
        self.btn_rename = tk.Button(outer, text="Rename", width=18, command=self.start_rename)
        self.btn_rename.pack(anchor="w", pady=(12, 0))
        self.btn_rename.pack_forget()  # hidden until a folder is chosen

        # Progress bar + status
        self.progress = ttk.Progressbar(outer, mode="determinate", length=300, maximum=100)
        self.progress.pack(anchor="w", pady=(12, 0))
        self.progress.pack_forget()

        self.status_label = tk.Label(outer, textvariable=self.status_text, fg="#333333")
        self.status_label.pack(anchor="w")
        self.status_label.pack_forget()

        # Error label (red, persistent at bottom)
        self.error_label = tk.Label(outer, textvariable=self.error_text, fg="red", wraplength=560, justify="left")
        self.error_label.pack(anchor="w", pady=(8, 0))

    def choose_folder(self):
        sel = filedialog.askdirectory(title="Choose Compositions/Loops Folder")
        if not sel:
            return
        self.selected_path.set(sel)
        self.error_text.set("")  # clear errors
        self.btn_rename.pack(anchor="w", pady=(12, 0))  # show rename button

    def start_rename(self):
        if not self.selected_path.get():
            messagebox.showwarning("No folder", "Please choose a folder first.")
            return

        # Reset UI state
        self.error_text.set("")
        self.status_text.set("Starting…")
        self.progress_value.set(0)
        self.progress_total = 1

        # Show progress widgets
        self.progress.pack(anchor="w", pady=(12, 0))
        self.status_label.pack(anchor="w")

        self.btn_choose.config(state="disabled")
        self.btn_rename.config(state="disabled")

        # Run in a worker thread to keep UI responsive
        threading.Thread(target=self._run_worker, daemon=True).start()

    def _on_progress(self, phase, done, total):
        self.progress_total = max(total, 1)
        pct = int((done / self.progress_total) * 100)
        self.progress["value"] = pct
        self.status_text.set(f"{phase} {done}/{total}")

    def _run_worker(self):
        try:
            process_folder(self.selected_path.get(), on_progress=self._on_progress)
        except Exception as e:
            # Update UI with error (on main thread)
            self.root.after(0, self._finish_with_error, str(e))
            return
        # Success
        self.root.after(0, self._finish_success)

    def _finish_success(self):
        self.btn_choose.config(state="normal")
        self.btn_rename.config(state="normal")
        self.status_text.set("Done!")
        self.progress["value"] = 100
        messagebox.showinfo("Done", "Renaming complete.\nOutput written to sibling folder prefixed with underscore.")

    def _finish_with_error(self, msg):
        self.btn_choose.config(state="normal")
        self.btn_rename.config(state="normal")
        self.status_text.set("Error.")
        self.error_text.set(msg)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    RenamoratorGUI().run()
