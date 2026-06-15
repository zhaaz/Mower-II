# App/dialogs/trafo_dialog.py

from __future__ import annotations

import queue
import threading
from typing import Callable, Any

import customtkinter as ctk

from Transformation.trafo_manager import TrafoManager
from Transformation.trafo_workflow import TrafoWorkflow, TrafoWorkflowConfig


def show_trafo_dialog(
    *,
    parent,
    xyz_worker,
    tracker_receiver,
    xyz_state_getter: Callable[[], Any],
    trafo_manager: TrafoManager,
    on_finished: Callable[[], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> None:
    dialog = TrafoDialog(
        master=parent,
        xyz_worker=xyz_worker,
        tracker_receiver=tracker_receiver,
        xyz_state_getter=xyz_state_getter,
        trafo_manager=trafo_manager,
        on_finished=on_finished,
        external_log=log,
    )

    dialog.grab_set()


class TrafoDialog(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        xyz_worker,
        tracker_receiver,
        xyz_state_getter: Callable[[], Any],
        trafo_manager: TrafoManager,
        on_finished: Callable[[], None] | None = None,
        external_log: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)

        self.title("Transformation")
        self.geometry("860x680")

        self.master_app = master
        self.xyz_worker = xyz_worker
        self.tracker_receiver = tracker_receiver
        self.xyz_state_getter = xyz_state_getter
        self.trafo_manager = trafo_manager
        self.on_finished = on_finished
        self.external_log = external_log

        self.workflow: TrafoWorkflow | None = None
        self.workflow_thread: threading.Thread | None = None
        self.result = None

        self.gui_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

        self._center_on_parent(width=860, height=680)
        self._build_ui()

        self.after(100, self.process_gui_queue)
        self.protocol("WM_DELETE_WINDOW", self.discard_and_close)

        self.start_workflow()

    # --------------------------------------------------
    # UI
    # --------------------------------------------------

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.lbl_title = ctk.CTkLabel(
            self,
            text="Transformation läuft...",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        self.lbl_title.grid(
            row=0,
            column=0,
            padx=20,
            pady=(20, 10),
            sticky="w",
        )

        self.lbl_status = ctk.CTkLabel(
            self,
            text="Status: -",
            justify="left",
            anchor="w",
        )
        self.lbl_status.grid(
            row=1,
            column=0,
            padx=20,
            pady=5,
            sticky="ew",
        )

        self.progress = ctk.CTkProgressBar(self)
        self.progress.grid(
            row=2,
            column=0,
            padx=20,
            pady=10,
            sticky="ew",
        )
        self.progress.set(0.0)

        self.textbox = ctk.CTkTextbox(self, wrap="none")
        self.textbox.grid(
            row=3,
            column=0,
            padx=20,
            pady=10,
            sticky="nsew",
        )

        button_frame = ctk.CTkFrame(self)
        button_frame.grid(
            row=4,
            column=0,
            padx=20,
            pady=(5, 20),
            sticky="ew",
        )
        button_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_cancel = ctk.CTkButton(
            button_frame,
            text="Abbrechen",
            command=self.cancel_workflow,
        )
        self.btn_cancel.grid(
            row=0,
            column=0,
            padx=10,
            pady=10,
            sticky="ew",
        )

        self.btn_accept = ctk.CTkButton(
            button_frame,
            text="Trafo übernehmen",
            command=self.accept_trafo,
            state="disabled",
        )
        self.btn_accept.grid(
            row=0,
            column=1,
            padx=10,
            pady=10,
            sticky="ew",
        )

        self.btn_discard = ctk.CTkButton(
            button_frame,
            text="Verwerfen / Schließen",
            command=self.discard_and_close,
        )
        self.btn_discard.grid(
            row=0,
            column=2,
            padx=10,
            pady=10,
            sticky="ew",
        )

    # --------------------------------------------------
    # Workflow
    # --------------------------------------------------

    def start_workflow(self) -> None:
        config = TrafoWorkflowConfig(
            tracker_capture_timeout_s=10.0,
            max_allowed_rms_mm=0.10,
            max_allowed_max_residual_mm=0.15,
            minimum_required_measurements=4,
            allow_scale=True,
            min_geometry_rank=2,
        )

        self.workflow = TrafoWorkflow(
            xyz_worker=self.xyz_worker,
            tracker_receiver=self.tracker_receiver,
            xyz_state_getter=self.xyz_state_getter,
            config=config,
            on_status=lambda text: self.gui_queue.put(("status", text)),
            on_progress=lambda current, total, label: self.gui_queue.put(
                ("progress", (current, total, label))
            ),
            on_log=lambda text: self.gui_queue.put(("log", text)),
        )

        self.workflow_thread = threading.Thread(
            target=self._workflow_thread_main,
            daemon=True,
        )
        self.workflow_thread.start()

    def _workflow_thread_main(self) -> None:
        if self.workflow is None:
            self.gui_queue.put(("log", "FEHLER: Kein TrafoWorkflow vorhanden."))
            return

        result = self.workflow.run()
        self.gui_queue.put(("result", result))

    def cancel_workflow(self) -> None:
        if self.workflow is not None:
            self.workflow.cancel()
            self.log("Abbruch angefordert...")

    def accept_trafo(self) -> None:
        if self.result is None:
            return

        try:
            self.trafo_manager.set_pending(self.result)
            self.trafo_manager.accept_pending()
        except Exception as exc:
            self.log(f"FEHLER beim Übernehmen der Trafo: {exc}")
            return

        self.log("Trafo wurde übernommen und ist jetzt gültig.")

        if self.on_finished:
            self.on_finished()

        self.destroy()

    def discard_and_close(self) -> None:
        if self.workflow is not None:
            self.workflow.cancel()

        try:
            self.trafo_manager.clear_pending()
        except Exception:
            pass

        if self.on_finished:
            self.on_finished()

        self.destroy()

    # --------------------------------------------------
    # Queue / GUI update
    # --------------------------------------------------

    def process_gui_queue(self) -> None:
        try:
            while True:
                kind, payload = self.gui_queue.get_nowait()

                if kind == "status":
                    self.lbl_status.configure(text=f"Status: {payload}")
                    self.log(payload)

                elif kind == "progress":
                    current, total, label = payload
                    value = current / total if total else 0.0
                    self.progress.set(value)
                    self.log(f"Fortschritt {current}/{total}: {label}")

                elif kind == "log":
                    self.log(payload)

                elif kind == "result":
                    self.handle_result(payload)

        except queue.Empty:
            pass

        self.after(100, self.process_gui_queue)

    # --------------------------------------------------
    # Ergebnis
    # --------------------------------------------------

    def handle_result(self, result) -> None:
        self.result = result

        self.btn_cancel.configure(state="disabled")

        self.log("")
        self.log("------------------------------------------------------------")
        self.log("ERGEBNIS TRANSFORMATION")
        self.log("------------------------------------------------------------")
        self.log(f"Status: {result.status}")
        self.log(f"Meldung: {result.message}")
        self.log(f"Dauer: {result.duration_s:.2f} s")

        if result.error:
            self.log("")
            self.log(f"Fehler: {result.error}")

        if result.failed_measurements:
            self.log("")
            self.log("Nicht messbare Punkte:")

            for failed in result.failed_measurements:
                self.log(
                    f"  {failed['name']}: "
                    f"X={failed['robot_target_x']:.3f}, "
                    f"Y={failed['robot_target_y']:.3f} | "
                    f"{failed['reason']}"
                )

        if result.trafo is not None:
            trafo = result.trafo

            self.log("")
            self.log("Restklaffungen:")

            for measurement, residual_norm in zip(
                    result.used_measurements,
                    trafo.residual_norms,
            ):
                self.log(
                    f"  {measurement['name']}: "
                    f"{float(residual_norm):.3f} mm"
                )

            quality_text = self._evaluate_trafo_quality(
                rms=trafo.rms,
                max_residual=trafo.max_residual,
            )

            self.log("")
            self.log("Qualität:")
            self.log(f"  Punktanzahl: {trafo.point_count}")
            self.log(f"  RMS:         {trafo.rms:.3f} mm")
            self.log(f"  Max:         {trafo.max_residual:.3f} mm")
            self.log(f"  Maßstab:     {trafo.scale:.9f}")
            self.log(f"  Bewertung:   {quality_text}")

        self.log("")
        self.log("Ergebnis:")

        if result.success:
            self.log("  Transformation erfolgreich.")

            self.lbl_title.configure(text="Transformation erfolgreich")
            self.lbl_status.configure(text="Status: fertig")
            self.btn_accept.configure(state="normal")
        else:
            self.log("  Transformation nicht erfolgreich.")

            self.lbl_title.configure(text="Transformation nicht erfolgreich")
            self.lbl_status.configure(text=f"Status: {result.status}")
            self.btn_accept.configure(state="disabled")

    def _evaluate_trafo_quality(
            self,
            *,
            rms: float,
            max_residual: float,
    ) -> str:
        if rms <= 0.05 and max_residual <= 0.10:
            return "SEHR GUT"

        if rms <= 0.10 and max_residual <= 0.20:
            return "GUT"

        if rms <= 0.25 and max_residual <= 0.50:
            return "OK"

        return "PRÜFEN"

    # --------------------------------------------------
    # Logging / helpers
    # --------------------------------------------------

    def log(self, text: str) -> None:
        self.textbox.insert("end", text + "\n")
        self.textbox.see("end")

        if self.external_log:
            self.external_log(f"[Trafo] {text}")

    def _center_on_parent(self, width: int, height: int) -> None:
        self.update_idletasks()

        try:
            parent_x = self.master_app.winfo_rootx()
            parent_y = self.master_app.winfo_rooty()
            parent_w = self.master_app.winfo_width()
            parent_h = self.master_app.winfo_height()

            x = parent_x + max(0, (parent_w - width) // 2)
            y = parent_y + max(0, (parent_h - height) // 2)
        except Exception:
            x = 100
            y = 100

        self.geometry(f"{width}x{height}+{x}+{y}")