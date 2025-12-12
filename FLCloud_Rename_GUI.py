#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import shutil
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

# ---------- core renamer logic ----------

DASH_SPLIT = re.compile(r"\s*-\s*")  # tolerant of missing/extra spaces

CORE_SET = {
    # Core instruments (canonical)
    "Bass", "Electric Bass", "Synth Bass", "Upright Bass",
    "Guitar", "Acoustic Guitar", "Electric Guitar",
    "Electric_Piano",
    "Lead", "Strings", "Choir", "Clavi",
    "Piano", "Organ", "Pad", "Pluck", "Arp", "Brass", "Synth", "Vibraphone",
    "Full", "Flute",
    "Bells", "Mallets", "Kalimba", "Vocals",
    "Glockenspiel", "Horns", "Keys",
}

INSTRUMENT_MAP = {
    # Bass family (canonical core chosen via priority + adjective specialization)
    "Bassline": "Bass", "Bass Line": "Bass", "Sub Bass": "Bass", "Bass": "Bass",
    "Electric Bass": "Bass", "Upright Bass": "Bass", "Synth Bass": "Bass",

    # Electric piano family → Electric_Piano
    "Rhodes": "Electric_Piano", "Rhodes Piano": "Electric_Piano",
    "E. Piano": "Electric_Piano", "EP": "Electric_Piano",
    "Electric Piano": "Electric_Piano",

    # Guitar family (canonical core chosen via priority + adjective specialization)
    "Guitar": "Guitar",
    "Electric Guitar": "Guitar",
    "Acoustic Guitar": "Guitar",

    # Straight cores
    "Lead": "Lead",
    "Strings": "Strings", "String": "Strings",
    "Choir": "Choir",
    "Clavi": "Clavi",
    "Piano": "Piano", "Grand Piano": "Piano",
    "Organ": "Organ",
    "Pad": "Pad",
    "Pluck": "Pluck",
    "Arp": "Arp",
    "Brass": "Brass",
    "Synth": "Synth",
    "Vibraphone": "Vibraphone", "Vibes": "Vibraphone",
    "Flute": "Flute",

    # New cores
    "Bell": "Bells", "Bells": "Bells",
    "Mallets": "Mallets",
    "Kalimba": "Kalimba",
    "Vocals": "Vocals", "Vox": "Vocals", "Vocal": "Vocals",
    "Keys": "Keys",

    # Requested normalizations
    "Horn": "Horns", "Horns": "Horns",
    "Glock": "Glockenspiel", "Glockenspiel": "Glockenspiel",

    "Full": "Full",
}

# Priority: lower number = higher priority
# Bass highest, then Guitar, everything else defaults to 2.
CORE_PRIORITY = {
    "Bass": 0,
    "Guitar": 1,
}


def canon_core(token: str) -> str:
    for k, v in INSTRUMENT_MAP.items():
        if token.lower() == k.lower():
            return v
    return token.title()


def _specialize_bass_guitar_core(core: str, adj: str):
    """Upgrade Bass/Guitar core names based on certain adjective words.

    Rules:
      Bass:
        - If adj contains 'Synth'   -> core 'Synth Bass'
        - If adj contains 'Upright' -> core 'Upright Bass'
        - If adj contains 'Electric' OR 'Guitar' -> core 'Electric Bass'
        - Otherwise core 'Bass'
        - Consumed words are removed from the adjective, other words remain.

      Guitar:
        - If adj contains 'Acoustic' OR 'Nylon' -> core 'Acoustic Guitar'
        - If adj contains 'Electric'            -> core 'Electric Guitar'
        - Otherwise core 'Guitar'
        - Consumed words are removed from the adjective, other words remain.
    """
    if not adj:
        return core, adj

    words = [w for w in adj.split() if w]
    low = [w.lower() for w in words]

    def remove_words(to_remove):
        rem = {w.lower() for w in to_remove}
        kept = [w for w in words if w.lower() not in rem]
        return " ".join(kept).title() if kept else ""

    if core == "Bass":
        if "synth" in low:
            return "Synth Bass", remove_words(["Synth"])
        if "upright" in low:
            return "Upright Bass", remove_words(["Upright"])
        if "electric" in low or "guitar" in low:
            return "Electric Bass", remove_words(["Electric", "Guitar"])
        return "Bass", adj

    if core == "Guitar":
        if "acoustic" in low or "nylon" in low:
            return "Acoustic Guitar", remove_words(["Acoustic", "Nylon"])
        if "electric" in low:
            return "Electric Guitar", remove_words(["Electric"])
        return "Guitar", adj

    return core, adj


def _is_bass_core(core: str) -> bool:
    return core in {"Bass", "Electric Bass", "Synth Bass", "Upright Bass"}


def normalize_instrument_phrase(phrase: str):
    """
    Extract instrument core + adjective.

    With priority rules:
      - Bass > Guitar > everything else (default).
      - On ties, pick the RIGHTMOST of the highest-priority cores.
      - All other tokens become the adjective.
    """
    s = re.sub(r"\s+", " ", phrase).strip()

    # Electric_Piano family handled specially
    m = re.search(r"(?i)\b(rhodes|e\.?\s*piano|^ep$|electric\s+piano)\b", s)
    if m:
        before = s[:m.start()].strip()
        adj = before.title() if before else ""
        return "Electric_Piano", adj

    tokens = s.split()
    if not tokens:
        return "Full", ""
    if len(tokens) == 1:
        return canon_core(tokens[0]), ""

    canon_tokens = [canon_core(t) for t in tokens]
    core_positions = [(i, c) for i, c in enumerate(canon_tokens) if c in CORE_SET]

    # If we found at least one core token, use priority logic
    if core_positions:
        chosen_idx = None
        chosen_core = None
        best_priority = None

        for i, c in core_positions:
            pr = CORE_PRIORITY.get(c, 2)  # default lowest priority = 2
            if best_priority is None or pr < best_priority:
                best_priority = pr
                chosen_idx = i
                chosen_core = c
            elif pr == best_priority and i > chosen_idx:
                # tie in priority -> pick rightmost
                chosen_idx = i
                chosen_core = c

        # Build adjective from everything except the chosen core token
        adj_tokens = tokens[:chosen_idx] + tokens[chosen_idx + 1:]
        adj = " ".join(adj_tokens).title() if adj_tokens else ""
        chosen_core, adj = _specialize_bass_guitar_core(chosen_core, adj)
        return chosen_core, adj

    # No core tokens found -> fallback behavior
    whole = canon_core(s)
    if whole in CORE_SET:
        return whole, ""
    return whole, ""


# ---------- key normalization ----------

FLAT_TO_SHARP = {
    "Ab": "G#",
    "Bb": "A#",
    "Db": "C#",
    "Eb": "D#",
    "Gb": "F#",
}


def normalize_key(key_raw: str) -> str:
    if not key_raw:
        return key_raw

    s = key_raw.strip()
    m = re.match(r'^([A-Ga-g])([#bB]?)(?:\s*(maj|MAJ|Maj|min|MIN|m))?$', s)
    if not m:
        return s

    root = m.group(1).upper()
    accidental = m.group(2) or ""
    qual_token = m.group(3)

    is_minor = False
    if qual_token:
        q = qual_token.lower()
        if q in ("m", "min"):
            is_minor = True
        elif q == "maj":
            is_minor = False
    else:
        is_minor = False  # default to major

    if accidental.lower() == "b":
        flat_name = root + "b"
        sharp_name = FLAT_TO_SHARP.get(flat_name)
        if sharp_name:
            root = sharp_name[0]
            accidental = "#"
        else:
            accidental = ""

    root_str = root + (accidental if accidental == "#" else "")
    suffix = "min" if is_minor else "maj"
    return root_str + suffix


def parse_comp_folder(folder_name: str):
    """
    Extract comp_name, key, bpm from a composition folder name.

    - Take the part before the first ' - ' as the "raw_comp".
    - If raw_comp has 3+ tokens, treat everything from the 3rd token onward
      as the descriptor and use THAT as comp_name.
    - If raw_comp has 1–2 tokens, use raw_comp as comp_name.
    """
    parts = DASH_SPLIT.split(folder_name)
    raw_comp = parts[0].strip() if parts else folder_name.strip()

    tokens = raw_comp.split()
    if len(tokens) >= 3:
        comp = " ".join(tokens[2:]).strip()
        if not comp:  # just in case
            comp = raw_comp
    else:
        comp = raw_comp

    key = parts[1].strip() if len(parts) >= 2 else None
    bpm = None
    if len(parts) >= 3:
        raw_bpm = parts[2].strip()
        m = re.search(r"(\d+(?:\.\d+)?)", raw_bpm)
        if m:
            bpm = f"{m.group(1)}bpm"
        else:
            bpm = raw_bpm.replace("BPM", "bpm").replace("Bpm", "bpm")
    return comp, key, bpm


def guess_instrument_from_filename(filename: str, comp_name: str):
    """
    Treat everything AFTER the first ' - ' as the instrument phrase.
    If there is no ' - ' at all, treat this as the Full/Multi loop.
    """
    stem = Path(filename).stem.strip()

    parts = DASH_SPLIT.split(stem, maxsplit=1)
    if len(parts) == 1:
        instrument_raw = "Full"
    else:
        instrument_raw = parts[1].strip()
        if not instrument_raw:
            instrument_raw = "Full"

    instrument_raw = re.sub(r"\s+", " ", instrument_raw).strip()
    return normalize_instrument_phrase(instrument_raw)


def pack_abbrev_from_parent(parent_dir: Path) -> str:
    name = parent_dir.name
    parts = DASH_SPLIT.split(name, maxsplit=1)
    pack_raw = parts[1] if len(parts) > 1 else name
    pack_raw = re.sub(r"(?i)^pelham\s*(?:&|and)\s*junior\s*", "", pack_raw).strip()
    return pack_raw.replace(" ", "")


def process_folder(selected_path: str, on_progress=None, pack_prefix: str | None = None):
    """
    on_progress: optional callback taking (phase_text, count_done, count_total)
    pack_prefix: optional override (3–8 letters, will be uppercased).
    """
    source_dir = Path(selected_path).expanduser().resolve()
    if not source_dir.exists() or not source_dir.is_dir():
        raise RuntimeError(f"Path not found or not a directory: {source_dir}")

    parent_dir = source_dir.parent
    pack_abbrev = pack_abbrev_from_parent(parent_dir)

    if pack_prefix and pack_prefix.strip():
        pack_abbrev = pack_prefix.strip().upper()

    # Output always goes into sibling folder called "Samples"
    dst_dir = parent_dir / "Samples"
    dst_dir.mkdir(exist_ok=True)

    LABEL = "P&J"

    subfolders = sorted([p for p in source_dir.iterdir() if p.is_dir()])
    wavs = [p for f in subfolders for p in f.iterdir() if p.suffix.lower() == ".wav"]
    total = len(wavs) if wavs else 1
    done = 0
    if on_progress:
        on_progress("Preparing…", done, total)

    for comp_folder in subfolders:
        comp_name, key, bpm = parse_comp_folder(comp_folder.name)
        comp_dst_dir = dst_dir / comp_folder.name
        comp_dst_dir.mkdir(parents=True, exist_ok=True)

        comp_wavs = sorted([p for p in comp_folder.iterdir() if p.suffix.lower() == ".wav"])

        # ---------- Pass 1: collect core instruments for Multi ----------
        seen_cores: list[str] = []
        for wav in comp_wavs:
            core, adj = guess_instrument_from_filename(wav.name, comp_name)
            if core == "Full":
                continue
            if core not in seen_cores:
                seen_cores.append(core)

        # up to 2 non-bass + Bass (if present; Bass stays last)
        multi_cores: list[str] = []
        bass_core = next((c for c in seen_cores if _is_bass_core(c)), None)
        bass_present = bass_core is not None
        non_bass = [c for c in seen_cores if not _is_bass_core(c)]
        if non_bass:
            multi_cores.append(non_bass[0])
            if len(non_bass) > 1:
                multi_cores.append(non_bass[1])
        if bass_present and bass_core:
            multi_cores.append(bass_core)

        # ---------- Pass 2: actual renaming ----------
        for wav in comp_wavs:
            core, adj = guess_instrument_from_filename(wav.name, comp_name)

            bpm_final = bpm
            if bpm_final is None:
                m = re.search(r"(\d+(?:\.\d+)?)(?:\s*)BPM", wav.name, flags=re.IGNORECASE)
                bpm_final = f"{m.group(1)}bpm" if m else "bpm"

            key_final = normalize_key(key) if key else ""
            # remove spaces, then wrap in double brackets
            comp_no_spaces = comp_name.replace(" ", "")
            descriptor_wrapped = f"[[{comp_no_spaces}]]"

            # Label | Pack | Instruments... | [[Descriptor]] | BPM | Key
            parts = [LABEL, pack_abbrev]

            if core == "Full":
                if multi_cores:
                    parts.extend(multi_cores)
                parts.append("Multi")
            else:
                parts.append(core)
                if adj:
                    parts.append(adj)

            parts.append(descriptor_wrapped)
            if bpm_final:
                parts.append(bpm_final)
            if key_final:
                parts.append(key_final)

            # filenames cannot contain spaces; use underscores
            parts = [p.replace(" ", "_") for p in parts]
            new_name = "_".join(parts) + ".wav"

            shutil.copyfile(wav, (comp_dst_dir / new_name))

            done += 1
            if on_progress:
                on_progress("Renaming…", done, total)


# ---------- GUI ----------

class RenamoratorGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("P&JxFL File Renamorator 3000")
        self.root.resizable(False, False)

        icon_dir = Path(__file__).parent / "icons"
        try:
            if sys.platform.startswith("win"):
                self.root.iconbitmap(icon_dir / "PJFLRename.ico")
            elif sys.platform == "darwin":
                self.root.iconphoto(False, tk.PhotoImage(file=icon_dir / "PJFLRename.png"))
            else:
                self.root.iconphoto(False, tk.PhotoImage(file=icon_dir / "PJFLRename.png"))
        except Exception as e:
            print(f"Warning: Could not load app icon ({e})")

        self.selected_path = tk.StringVar(value="")
        self.pack_prefix_var = tk.StringVar(value="")
        self.status_text = tk.StringVar(value="")
        self.error_text = tk.StringVar(value="")
        self.progress_value = tk.IntVar(value=0)
        self.progress_total = 1

        outer = tk.Frame(self.root, padx=16, pady=16)
        outer.pack(fill="both", expand=True)

        tk.Label(
            outer,
            text="P&JxFL File Renamorator 3000",
            font=("Helvetica", 16, "bold")
        ).pack(anchor="w")

        tk.Label(outer, text="Select Comp Folder:", pady=8).pack(anchor="w")

        row = tk.Frame(outer)
        row.pack(fill="x", anchor="w")

        self.btn_choose = tk.Button(row, text="Choose Folder", width=18, command=self.choose_folder)
        self.btn_choose.pack(side="left")

        self.path_label = tk.Label(
            row,
            textvariable=self.selected_path,
            anchor="w",
            fg="#666666",
            wraplength=520,
            justify="left"
        )
        self.path_label.pack(side="left", padx=10)

        tk.Label(
            outer,
            text="Pack Prefix (3–8 letters; no numbers, no spaces)",
            pady=8
        ).pack(anchor="w")

        prefix_row = tk.Frame(outer)
        prefix_row.pack(fill="x", anchor="w")

        self.prefix_entry = tk.Entry(prefix_row, textvariable=self.pack_prefix_var, width=20)
        self.prefix_entry.pack(side="left")

        self.btn_rename = tk.Button(outer, text="Rename", width=18, command=self.start_rename)
        self.btn_rename.pack(anchor="w", pady=(12, 0))
        self.btn_rename.pack_forget()

        self.progress = ttk.Progressbar(outer, mode="determinate", length=320, maximum=100)
        self.progress.pack(anchor="w", pady=(12, 0))
        self.progress.pack_forget()

        self.status_label = tk.Label(outer, textvariable=self.status_text, fg="#333333")
        self.status_label.pack(anchor="w")
        self.status_label.pack_forget()

        self.error_label = tk.Label(
            outer,
            textvariable=self.error_text,
            fg="red",
            wraplength=560,
            justify="left"
        )
        self.error_label.pack(anchor="w", pady=(8, 0))

        self.pack_prefix_var.trace_add("write", lambda *_: self._prefix_sanitize_and_validate())

    def _prefix_sanitize_and_validate(self):
        val = self.pack_prefix_var.get()

        if " " in val:
            val = val.replace(" ", "")
            self.pack_prefix_var.set(val)
            return

        if val == "" or re.fullmatch(r"[A-Za-z]{3,8}", val):
            self.error_text.set("")
            if self.selected_path.get():
                self.btn_rename.pack(anchor="w", pady=(12, 0))
                self.btn_rename.config(state="normal")
        else:
            self.error_text.set(
                "Pack Prefix must be 3–8 letters (A–Z), no numbers, no spaces.\n"
                "Leave blank to use the pack name."
            )
            if self.selected_path.get():
                self.btn_rename.pack(anchor="w", pady=(12, 0))
                self.btn_rename.config(state="disabled")

    def choose_folder(self):
        sel = filedialog.askdirectory(title="Choose Compositions/Loops Folder")
        if not sel:
            return

        self.selected_path.set(sel)
        self.pack_prefix_var.set("")
        self.error_text.set("")
        self._prefix_sanitize_and_validate()

    def start_rename(self):
        val = self.pack_prefix_var.get().strip()

        if not (val == "" or re.fullmatch(r"[A-Za-z]{3,8}", val)):
            self.error_text.set(
                "Pack Prefix must be 3–8 letters (A–Z), no numbers, no spaces.\n"
                "Leave blank to use the pack name."
            )
            return

        self.error_text.set("")
        self.status_text.set("Starting…")
        self.progress_value.set(0)
        self.progress_total = 1

        self.progress.pack(anchor="w", pady=(12, 0))
        self.status_label.pack(anchor="w")

        self.btn_choose.config(state="disabled")
        self.btn_rename.config(state="disabled")

        prefix = val.upper() if val else None
        threading.Thread(target=self._run_worker, args=(prefix,), daemon=True).start()

    def _on_progress(self, phase, done, total):
        self.progress_total = max(total, 1)
        pct = int((done / self.progress_total) * 100)
        self.progress["value"] = pct
        self.status_text.set(f"{phase} {done}/{total}")

    def _run_worker(self, prefix):
        try:
            process_folder(self.selected_path.get(), on_progress=self._on_progress, pack_prefix=prefix)
        except Exception as e:
            self.root.after(0, self._finish_with_error, str(e))
            return
        self.root.after(0, self._finish_success)

    def _finish_success(self):
        self.btn_choose.config(state="normal")
        self.btn_rename.config(state="normal")
        self.status_text.set("Done!")
        self.progress["value"] = 100
        messagebox.showinfo(
            "Done",
            "Renaming complete.\nOutput written to sibling folder named 'Samples'."
        )

    def _finish_with_error(self, msg):
        self.btn_choose.config(state="normal")
        self.btn_rename.config(state="normal")
        self.status_text.set("Error.")
        self.error_text.set(msg)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    RenamoratorGUI().run()
