#!/usr/bin/env python3
from __future__ import annotations

import queue
import re
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, VERTICAL, BooleanVar, IntVar, StringVar, Tk, filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

ROOT = Path(__file__).resolve().parent
TV_REELS = ROOT / "tv_reels.py"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from modules.idea_to_script import suggest_ideas


class App:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("TradeVera Reels Factory (Local)")
        self.root.geometry("900x760")

        self.idea_var = StringVar()
        self.idea_preset_var = StringVar()
        self.style_var = StringVar(value="tradevera_premium")
        self.length_var = StringVar(value="")
        self.no_broll_var = BooleanVar(value=True)
        self.images: list[Path] = []
        self.proc: subprocess.Popen[str] | None = None
        self.q: queue.Queue[tuple[str, str]] = queue.Queue()
        self.last_output_dir: Path | None = None

        self._build_ui()
        self.root.after(150, self._poll_queue)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text="Idea").grid(row=0, column=0, sticky="w")
        self.idea_entry = ttk.Entry(frame, textvariable=self.idea_var, width=90)
        self.idea_entry.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        self.idea_entry.insert(0, "Why most traders fail risk management")

        ttk.Label(frame, text="Idea Presets (more examples)").grid(row=2, column=0, sticky="w")
        self.idea_combo = ttk.Combobox(frame, textvariable=self.idea_preset_var, values=suggest_ideas(), width=58)
        self.idea_combo.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Button(frame, text="Use Preset", command=self._use_preset).grid(row=3, column=2, sticky="w", pady=(0, 10))

        ttk.Label(frame, text="Style").grid(row=4, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.style_var, width=28).grid(row=5, column=0, sticky="w", pady=(0, 10))

        ttk.Label(frame, text="Length (20-35, blank=random)").grid(row=4, column=1, sticky="w")
        ttk.Entry(frame, textvariable=self.length_var, width=18).grid(row=5, column=1, sticky="w", pady=(0, 10))

        ttk.Checkbutton(frame, text="No b-roll (slides + images only)", variable=self.no_broll_var).grid(
            row=5, column=2, columnspan=2, sticky="w", pady=(0, 10)
        )

        img_bar = ttk.Frame(frame)
        img_bar.grid(row=6, column=0, columnspan=4, sticky="ew")
        ttk.Label(img_bar, text="Images (optional, 0-12)").pack(side=LEFT)
        ttk.Button(img_bar, text="Add Images", command=self._pick_images).pack(side=LEFT, padx=(10, 6))
        ttk.Button(img_bar, text="Clear", command=self._clear_images).pack(side=LEFT)

        self.images_list = ScrolledText(frame, height=6, wrap="word")
        self.images_list.grid(row=7, column=0, columnspan=4, sticky="nsew", pady=(6, 12))
        self.images_list.insert("1.0", "No images selected.\n")
        self.images_list.config(state="disabled")

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        self.run_btn = ttk.Button(btn_row, text="Generate Reel", command=self._run)
        self.run_btn.pack(side=LEFT)
        self.open_out_btn = ttk.Button(btn_row, text="Open Last Output", command=self._open_last_output, state="disabled")
        self.open_out_btn.pack(side=LEFT, padx=(8, 0))
        ttk.Button(btn_row, text="Open outputs/", command=lambda: self._open_path(ROOT / "outputs")).pack(side=LEFT, padx=(8, 0))
        ttk.Button(btn_row, text="Setup Check", command=self._setup_check).pack(side=LEFT, padx=(8, 0))

        self.status_var = StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.status_var).grid(row=9, column=0, columnspan=4, sticky="w")

        self.log = ScrolledText(frame, height=20, wrap="word")
        self.log.grid(row=10, column=0, columnspan=4, sticky="nsew", pady=(8, 0))
        self._append_log("Local click UI ready. This runs the offline Python + FFmpeg pipeline on your machine.\n")

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)
        frame.columnconfigure(3, weight=1)
        frame.rowconfigure(7, weight=0)
        frame.rowconfigure(10, weight=1)

    def _use_preset(self) -> None:
        value = self.idea_preset_var.get().strip()
        if value:
            self.idea_var.set(value)

    def _append_log(self, text: str) -> None:
        self.log.insert(END, text)
        self.log.see(END)

    def _refresh_images_box(self) -> None:
        self.images_list.config(state="normal")
        self.images_list.delete("1.0", END)
        if not self.images:
            self.images_list.insert("1.0", "No images selected.\n")
        else:
            for p in self.images:
                self.images_list.insert(END, f"{p}\n")
        self.images_list.config(state="disabled")

    def _pick_images(self) -> None:
        files = filedialog.askopenfilenames(
            title="Select images",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")],
        )
        if not files:
            return
        for f in files:
            p = Path(f).resolve()
            if p not in self.images:
                self.images.append(p)
        self.images = self.images[:12]
        self._refresh_images_box()

    def _clear_images(self) -> None:
        self.images = []
        self._refresh_images_box()

    def _setup_check(self) -> None:
        self._append_log("\nRunning setup check...\n")
        try:
            cp = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "setup_check.py")],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
            )
            self._append_log(cp.stdout)
            if cp.stderr:
                self._append_log(cp.stderr)
        except Exception as exc:
            self._append_log(f"Setup check failed: {exc}\n")

    def _run(self) -> None:
        if self.proc and self.proc.poll() is None:
            messagebox.showinfo("Busy", "A build is already running.")
            return
        idea = self.idea_var.get().strip()
        if not idea:
            messagebox.showerror("Missing idea", "Please enter an idea.")
            return

        cmd = [sys.executable, str(TV_REELS), "--idea", idea]
        style = self.style_var.get().strip() or "tradevera_premium"
        cmd += ["--style", style]

        length_txt = self.length_var.get().strip()
        if length_txt:
            if not length_txt.isdigit():
                messagebox.showerror("Invalid length", "Length must be blank or a number (20-35).")
                return
            cmd += ["--length", length_txt]
        if self.no_broll_var.get():
            cmd.append("--no_broll")
        if self.images:
            cmd.append("--images")
            cmd.extend(str(p) for p in self.images)

        self.run_btn.config(state="disabled")
        self.status_var.set("Running...")
        self.last_output_dir = None
        self.open_out_btn.config(state="disabled")
        self._append_log("\n=== Generate Reel ===\n")
        self._append_log("Command: " + " ".join(repr(c) for c in cmd) + "\n")

        t = threading.Thread(target=self._run_subprocess, args=(cmd,), daemon=True)
        t.start()

    def _run_subprocess(self, cmd: list[str]) -> None:
        try:
            self.proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert self.proc.stdout is not None
            for line in self.proc.stdout:
                self.q.put(("log", line))
            rc = self.proc.wait()
            self.q.put(("done", str(rc)))
        except Exception as exc:
            self.q.put(("log", f"Failed to start process: {exc}\n"))
            self.q.put(("done", "-1"))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                    m = re.search(r"SUCCESS:\s+(.+)$", payload.strip())
                    if m:
                        self.last_output_dir = Path(m.group(1).strip())
                        self.open_out_btn.config(state="normal")
                        self._append_build_log(self.last_output_dir)
                elif kind == "done":
                    rc = int(payload)
                    self.run_btn.config(state="normal")
                    self.status_var.set("Done" if rc == 0 else f"Failed (exit {rc})")
                    if rc != 0:
                        self._try_discover_last_output_from_log_text()
                self.q.task_done()
        except queue.Empty:
            pass
        self.root.after(150, self._poll_queue)

    def _try_discover_last_output_from_log_text(self) -> None:
        text = self.log.get("1.0", END)
        m = re.findall(r"Build log:\s+(.+?/outputs/[^/]+/build_log\.txt)", text)
        if m:
            build_log = Path(m[-1])
            if build_log.exists():
                self.last_output_dir = build_log.parent
                self.open_out_btn.config(state="normal")
                self._append_build_log(self.last_output_dir)

    def _append_build_log(self, out_dir: Path) -> None:
        build_log = out_dir / "build_log.txt"
        if not build_log.exists():
            return
        self._append_log("\n--- build_log.txt ---\n")
        try:
            self._append_log(build_log.read_text(encoding="utf-8"))
        except Exception as exc:
            self._append_log(f"Could not read build_log.txt: {exc}\n")
        self._append_log("--- end build_log.txt ---\n")

    def _open_last_output(self) -> None:
        if not self.last_output_dir:
            return
        self._open_path(self.last_output_dir)

    def _open_path(self, path: Path) -> None:
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif sys.platform.startswith("win"):
                subprocess.Popen(["explorer", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror("Open failed", str(exc))


def main() -> int:
    if not TV_REELS.exists():
        print("tv_reels.py not found", file=sys.stderr)
        return 1
    root = Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
