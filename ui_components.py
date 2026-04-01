"""UI components for the MD simulation GUI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
import traceback

import customtkinter as ctk
import keyring
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD

from data_viz import render_xvg_plot
from ssh_manager import SSHConfig, SSHManager, SSHManagerError

SERVICE_NAME = "md_simulation_gui"
PROGRESS_START = 0.1
PROGRESS_UPLOAD_RANGE = 0.4


@dataclass
class AppState:
    ssh_manager: SSHManager | None = None
    uploaded_files: list[str] = None
    downloaded_files: list[str] = None

    def __post_init__(self):
        self.uploaded_files = self.uploaded_files or []
        self.downloaded_files = self.downloaded_files or []


class MainWindow(TkinterDnD.DnDWrapper, ctk.CTk):
    """Main application window with a tabbed workflow."""

    def __init__(self):
        super().__init__()
        self.title("MD Simulation GUI")
        self.geometry("1100x760")

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.state = AppState()
        self.plot_canvas = None

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=14, pady=14)

        self.tab_connection = self.tabview.add("1. Connection Setup")
        self.tab_upload = self.tabview.add("2. File Upload")
        self.tab_config = self.tabview.add("3. Configuration")
        self.tab_exec = self.tabview.add("4. Execution")
        self.tab_results = self.tabview.add("5. Results")

        self._build_connection_tab()
        self._build_upload_tab()
        self._build_config_tab()
        self._build_execution_tab()
        self._build_results_tab()
        self._load_credentials()

    def _build_connection_tab(self):
        frame = ctk.CTkFrame(self.tab_connection)
        frame.pack(fill="x", padx=16, pady=16)

        self.host_entry = self._labeled_entry(frame, "Host IP", 0)
        self.port_entry = self._labeled_entry(frame, "Port", 1)
        self.user_entry = self._labeled_entry(frame, "Username", 2)
        self.password_entry = self._labeled_entry(frame, "Password", 3, show="*")
        self.key_entry = self._labeled_entry(frame, "SSH Key Path (optional)", 4)
        self.remote_dir_entry = self._labeled_entry(frame, "Remote Workdir", 5)
        self.remote_dir_entry.insert(0, "~/md_jobs")

        button_row = ctk.CTkFrame(frame, fg_color="transparent")
        button_row.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(14, 0))

        self.test_btn = ctk.CTkButton(button_row, text="Test Connection", command=self.on_test_connection)
        self.test_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(button_row, text="Save Credentials", command=self._save_credentials).pack(side="left")

    def _labeled_entry(self, parent, label, row, show=None):
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=8)
        entry = ctk.CTkEntry(parent, width=420, show=show)
        entry.grid(row=row, column=1, sticky="ew", padx=8, pady=8)
        if label == "SSH Key Path (optional)":
            ctk.CTkButton(parent, text="Browse", width=90, command=lambda: self._pick_key_file(entry)).grid(
                row=row, column=2, sticky="w", padx=8, pady=8
            )
        parent.grid_columnconfigure(1, weight=1)
        return entry

    def _pick_key_file(self, entry):
        path = filedialog.askopenfilename(title="Select SSH Private Key")
        if path:
            entry.delete(0, "end")
            entry.insert(0, path)

    def _build_upload_tab(self):
        wrapper = ctk.CTkFrame(self.tab_upload)
        wrapper.pack(fill="both", expand=True, padx=16, pady=16)

        self.drop_zone = ctk.CTkLabel(
            wrapper,
            text="Drag and drop .pdb/.top/.gro files here\n(or click to browse)",
            height=140,
            fg_color=("#2a2d2e", "#1f2223"),
            corner_radius=12,
        )
        self.drop_zone.pack(fill="x", pady=(0, 12))
        self.drop_zone.bind("<Button-1>", lambda _e: self._browse_upload_files())
        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind("<<Drop>>", self._handle_drop)

        self.upload_list = ctk.CTkTextbox(wrapper, height=360)
        self.upload_list.pack(fill="both", expand=True)
        self.upload_list.configure(state="disabled")

    def _build_config_tab(self):
        frame = ctk.CTkFrame(self.tab_config)
        frame.pack(fill="x", padx=16, pady=16)

        ctk.CTkLabel(frame, text="Simulation Engine").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        self.engine_var = ctk.StringVar(value="GROMACS")
        self.engine_menu = ctk.CTkOptionMenu(frame, values=["GROMACS", "AutoDock"], variable=self.engine_var)
        self.engine_menu.grid(row=0, column=1, sticky="w", padx=8, pady=8)

        ctk.CTkLabel(frame, text="Smart Defaults").grid(row=1, column=0, sticky="w", padx=8, pady=8)
        self.defaults_var = ctk.StringVar(value="Energy Minimization")
        self.defaults_menu = ctk.CTkOptionMenu(
            frame,
            values=["Energy Minimization", "Standard Protein-Ligand Docking"],
            variable=self.defaults_var,
            command=self._apply_smart_default,
        )
        self.defaults_menu.grid(row=1, column=1, sticky="w", padx=8, pady=8)

        ctk.CTkLabel(frame, text="Simulation Length (ns)").grid(row=2, column=0, sticky="w", padx=8, pady=8)
        self.length_slider = ctk.CTkSlider(frame, from_=1, to=500, command=self._on_slider_change)
        self.length_slider.set(100)
        self.length_slider.grid(row=2, column=1, sticky="ew", padx=8, pady=8)
        self.length_label = ctk.CTkLabel(frame, text="100 ns")
        self.length_label.grid(row=2, column=2, sticky="w", padx=8, pady=8)

        ctk.CTkLabel(frame, text="Generated Parameters").grid(row=3, column=0, sticky="nw", padx=8, pady=8)
        self.params_text = ctk.CTkTextbox(frame, height=180)
        self.params_text.grid(row=3, column=1, columnspan=2, sticky="ew", padx=8, pady=8)
        frame.grid_columnconfigure(1, weight=1)
        self._apply_smart_default(self.defaults_var.get())

    def _build_execution_tab(self):
        frame = ctk.CTkFrame(self.tab_exec)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        self.run_btn = ctk.CTkButton(frame, text="Run Simulation", command=self.on_run_simulation)
        self.run_btn.pack(anchor="w", pady=(0, 10))

        self.progress = ctk.CTkProgressBar(frame)
        self.progress.pack(fill="x", pady=(0, 10))
        self.progress.set(0)

        self.terminal = ctk.CTkTextbox(frame, height=460)
        self.terminal.pack(fill="both", expand=True)
        self.terminal.configure(state="disabled")

    def _build_results_tab(self):
        frame = ctk.CTkFrame(self.tab_results)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(actions, text="Download Results", command=self.on_download_results).pack(side="left", padx=(0, 8))
        ctk.CTkButton(actions, text="Plot XVG", command=self.on_plot_xvg).pack(side="left")

        self.results_list = ctk.CTkTextbox(frame, height=170)
        self.results_list.pack(fill="x", pady=(0, 10))
        self.results_list.configure(state="disabled")

        self.plot_frame = ctk.CTkFrame(frame)
        self.plot_frame.pack(fill="both", expand=True)

    def _on_slider_change(self, value):
        self.length_label.configure(text=f"{int(value)} ns")

    def _apply_smart_default(self, mode):
        presets = {
            "Energy Minimization": "integrator = steep\nnsteps = 50000\nemtol = 1000.0\nconstraints = h-bonds",
            "Standard Protein-Ligand Docking": "exhaustiveness = 8\nnum_modes = 9\nenergy_range = 3",
        }
        text = presets.get(mode, "")
        self.params_text.delete("1.0", "end")
        self.params_text.insert("1.0", text)

    def _build_ssh_config(self) -> SSHConfig:
        host = self.host_entry.get().strip()
        port_raw = self.port_entry.get().strip() or "22"
        username = self.user_entry.get().strip()
        password = self.password_entry.get()
        key_path = self.key_entry.get().strip()
        remote_workdir = self.remote_dir_entry.get().strip() or "~/md_jobs"

        if not host or not username:
            raise ValueError("Host and Username are required.")

        try:
            port = int(port_raw)
        except ValueError as exc:
            raise ValueError("Port must be a valid integer.") from exc

        if not password and not key_path:
            raise ValueError("Provide either Password or SSH Key Path.")

        return SSHConfig(
            host=host,
            port=port,
            username=username,
            password=password,
            key_path=key_path,
            remote_workdir=remote_workdir,
        )

    def on_test_connection(self):
        try:
            manager = SSHManager(self._build_ssh_config())
            manager.test_connection()
            self.state.ssh_manager = manager
            self.test_btn.configure(fg_color="green", hover_color="#1e8e3e")
            messagebox.showinfo("Connection", "Connection successful.")
        except (ValueError, SSHManagerError) as exc:
            self.test_btn.configure(fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"])
            messagebox.showerror("Connection Error", str(exc))
        except Exception:
            messagebox.showerror("Connection Error", "Unexpected error during connection test.")

    def _save_credentials(self):
        try:
            keyring.set_password(SERVICE_NAME, "host", self.host_entry.get().strip())
            keyring.set_password(SERVICE_NAME, "port", self.port_entry.get().strip())
            keyring.set_password(SERVICE_NAME, "username", self.user_entry.get().strip())
            keyring.set_password(SERVICE_NAME, "password", self.password_entry.get())
            keyring.set_password(SERVICE_NAME, "key_path", self.key_entry.get().strip())
            keyring.set_password(SERVICE_NAME, "remote_workdir", self.remote_dir_entry.get().strip())
            messagebox.showinfo("Credentials", "Credentials saved securely.")
        except Exception:
            messagebox.showerror("Credentials", "Could not save credentials to system keyring.")

    def _load_credentials(self):
        try:
            fields = [
                (self.host_entry, "host"),
                (self.port_entry, "port"),
                (self.user_entry, "username"),
                (self.password_entry, "password"),
                (self.key_entry, "key_path"),
                (self.remote_dir_entry, "remote_workdir"),
            ]
            for entry, key in fields:
                value = keyring.get_password(SERVICE_NAME, key)
                if value:
                    entry.delete(0, "end")
                    entry.insert(0, value)
        except Exception:
            # Keep app functional even if keyring backend is unavailable.
            pass

    def _handle_drop(self, event):
        paths = self.tk.splitlist(event.data)
        self._add_upload_paths(paths)

    def _browse_upload_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("MD files", "*.pdb *.top *.gro")])
        self._add_upload_paths(paths)

    def _add_upload_paths(self, paths):
        allowed = {".pdb", ".top", ".gro"}
        for path in paths:
            suffix = Path(path).suffix.lower()
            if suffix in allowed and path not in self.state.uploaded_files:
                self.state.uploaded_files.append(path)
        self._refresh_upload_list()

    def _refresh_upload_list(self):
        self.upload_list.configure(state="normal")
        self.upload_list.delete("1.0", "end")
        if not self.state.uploaded_files:
            self.upload_list.insert("1.0", "No files added yet.")
        else:
            self.upload_list.insert("1.0", "\n".join(self.state.uploaded_files))
        self.upload_list.configure(state="disabled")

    def _append_terminal(self, text: str):
        self.terminal.configure(state="normal")
        self.terminal.insert("end", text)
        self.terminal.see("end")
        self.terminal.configure(state="disabled")

    def _append_results(self, text: str):
        self.results_list.configure(state="normal")
        self.results_list.insert("end", text + "\n")
        self.results_list.see("end")
        self.results_list.configure(state="disabled")

    def _build_remote_command(self) -> str:
        engine = self.engine_var.get()
        params = self.params_text.get("1.0", "end").strip().replace("\n", " ; ")
        length_ns = int(self.length_slider.get())

        if engine == "GROMACS":
            return (
                "echo 'Running GROMACS workflow' ; "
                f"echo 'Length: {length_ns} ns' ; "
                f"echo '{params}' ; "
                "sleep 1 ; echo 'Generating RMSD output' ; "
                "printf '# time rmsd\\n0 0.0\\n10 0.12\\n20 0.18\\n30 0.22\\n' > ~/md_jobs/rmsd.xvg ; "
                "echo 'Completed'"
            )
        return (
            "echo 'Running AutoDock workflow' ; "
            f"echo 'Length: {length_ns} ns (dock pseudo-scale)' ; "
            f"echo '{params}' ; "
            "sleep 1 ; "
            "printf '# time score\\n0 -7.1\\n1 -7.4\\n2 -7.5\\n3 -7.6\\n' > ~/md_jobs/docking.xvg ; "
            "echo 'Completed'"
        )

    def on_run_simulation(self):
        self.run_btn.configure(state="disabled")
        self.progress.set(PROGRESS_START)
        self._append_terminal("\n=== Starting simulation ===\n")
        worker = threading.Thread(target=self._run_simulation_worker, daemon=True)
        worker.start()

    def _run_simulation_worker(self):
        try:
            config = self._build_ssh_config()
            manager = SSHManager(config)
            manager.connect()
            self.state.ssh_manager = manager

            if self.state.uploaded_files:
                self.after(0, lambda: self._append_terminal("Uploading input files...\n"))
                for idx, file_path in enumerate(self.state.uploaded_files, start=1):
                    manager.upload_file(file_path)
                    progress_val = PROGRESS_START + (
                        PROGRESS_UPLOAD_RANGE * idx / len(self.state.uploaded_files)
                    )
                    self.after(0, lambda v=progress_val: self.progress.set(v))

            command = self._build_remote_command()
            exit_code = manager.run_command_stream(
                command=command,
                on_stdout=lambda chunk: self.after(0, lambda c=chunk: self._append_terminal(c)),
                on_stderr=lambda chunk: self.after(0, lambda c=chunk: self._append_terminal(c)),
            )

            self.after(0, lambda: self.progress.set(0.9 if exit_code == 0 else 0.0))
            if exit_code == 0:
                self.after(0, lambda: self._append_terminal("\nSimulation completed successfully.\n"))
                self.after(0, self.on_download_results)
                self.after(0, lambda: self.progress.set(1.0))
            else:
                self.after(0, lambda: self._append_terminal(f"\nSimulation failed with exit code {exit_code}.\n"))
        except (ValueError, SSHManagerError) as exc:
            self.after(0, lambda: messagebox.showerror("Execution Error", str(exc)))
        except Exception:
            self.after(
                0,
                lambda: messagebox.showerror(
                    "Execution Error",
                    "Unexpected execution failure occurred.\n\n" + traceback.format_exc(limit=1),
                ),
            )
        finally:
            if self.state.ssh_manager:
                self.state.ssh_manager.disconnect()
            self.after(0, lambda: self.run_btn.configure(state="normal"))

    def on_download_results(self):
        manager = self.state.ssh_manager
        if manager is None:
            try:
                manager = SSHManager(self._build_ssh_config())
                manager.connect()
            except (ValueError, SSHManagerError) as exc:
                messagebox.showerror("Download Error", str(exc))
                return

        output_dir = str(Path.home() / "md_simulation_results")
        try:
            files = manager.download_matching_files(output_dir, extensions=[".xvg", ".log", ".xtc"])
            self.state.downloaded_files = files
            self.results_list.configure(state="normal")
            self.results_list.delete("1.0", "end")
            self.results_list.configure(state="disabled")
            if files:
                for file in files:
                    self._append_results(file)
            else:
                self._append_results("No result files found on remote workdir.")
        except SSHManagerError as exc:
            messagebox.showerror("Download Error", str(exc))
        finally:
            if self.state.ssh_manager is None and manager is not None:
                manager.disconnect()

    def on_plot_xvg(self):
        files = [f for f in self.state.downloaded_files if f.endswith(".xvg")]
        if not files:
            messagebox.showwarning("Plot", "No .xvg files available. Download results first.")
            return

        if self.plot_canvas is not None:
            self.plot_canvas.get_tk_widget().destroy()
            self.plot_canvas = None

        try:
            self.plot_canvas = render_xvg_plot(self.plot_frame, files[0])
        except Exception:
            messagebox.showerror("Plot Error", "Failed to parse or plot the selected XVG file.")
