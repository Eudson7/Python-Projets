"""Janela principal: 3 passos (Limpeza → Arquivos grandes → Relatório).

Toda operação pesada roda em thread e só devolve resultado para a interface
via fila, para a janela nunca congelar durante uma varredura longa.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from typing import Callable

import customtkinter as ctk

from .. import bigfiles, report
from ..clean import clean_targets
from ..scan import human_size, scan_all
from ..targets import TARGETS, Risk, default_selection, get_target
from . import theme
from .dialogs import ConfirmDialog

DISPLAY_LIMIT = 200  # linhas máximas desenhadas (o resto fica no contador)

NAV_ORDER = ("clean", "big", "report")
NAV_TITLES = {
    "clean": "1   Limpeza",
    "big": "2   Arquivos grandes",
    "report": "3   Relatório",
}


class Step(ctk.CTkFrame):
    """Passo da interface + utilitário de trabalho em thread."""

    def __init__(self, master, app: "App") -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.app = app
        self.events: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.busy = False
        self._polling = False

    # ------------------------------------------------------------------ util
    def header(self, eyebrow: str, title: str, subtitle: str) -> None:
        theme.label(self, eyebrow, kind="label", color=theme.ACCENT).pack(
            anchor="w", padx=34, pady=(28, 4)
        )
        theme.label(self, title, kind="heading").pack(anchor="w", padx=34)
        theme.label(
            self, subtitle, kind="body", color=theme.MUTED, wraplength=760, justify="left"
        ).pack(anchor="w", padx=34, pady=(4, 0))

    def run_job(
        self,
        work: Callable[[Callable[[object], None]], object],
        on_done: Callable,
        on_progress: Callable | None = None,
    ) -> None:
        """Roda ``work`` numa thread; ``work(emit)`` pode emitir progresso."""
        if self.busy:
            return
        self.busy = True

        def emit(payload: object) -> None:
            self.events.put(("progress", payload))

        def worker() -> None:
            try:
                result = work(emit)
            except Exception as exc:  # noqa: BLE001 - interface precisa ver o erro
                self.events.put(("error", exc))
            else:
                self.events.put(("done", result))

        threading.Thread(target=worker, daemon=True).start()
        if not self._polling:
            self._polling = True
            self.after(100, self._poll, on_done, on_progress)

    def _poll(self, on_done: Callable, on_progress: Callable | None) -> None:
        handled_done = False
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                if on_progress is not None:
                    on_progress(payload)
                continue
            self.busy = False
            self._polling = False
            if kind == "error":
                self.on_error(payload)  # type: ignore[arg-type]
            else:
                on_done(payload)
            handled_done = True
            break
        if not handled_done:
            self.after(120, self._poll, on_done, on_progress)

    def on_error(self, exc: Exception) -> None:
        self.app.set_status(f"Erro: {exc}")
        self.after_idle(self._reset_ui)

    def _reset_ui(self) -> None:
        """Sobrescrito por quem usa barra de progresso."""


# ====================================================================== PASSO 1
class StepClean(Step):
    def __init__(self, master, app: "App") -> None:
        super().__init__(master, app)
        self.rows: dict[str, dict] = {}
        self.sizes: dict[str, int] = {}

        self.header(
            "PASSO 1 · LIMPEZA",
            "Lixo que já pode sumir",
            "Só o que está nesta lista é tocado. Verifique, escolha as categorias e confirme.",
        )

        bar = theme.card(self)
        bar.pack(fill="x", padx=34, pady=(16, 10))
        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)

        self.scan_btn = theme.button(inner, "Verificar agora", self.start_scan, width=160)
        self.scan_btn.pack(side="left")
        theme.button(
            inner, "Marcar tudo", lambda: self._select_all(True), kind="ghost", width=130
        ).pack(side="left", padx=(10, 0))
        theme.button(
            inner, "Desmarcar", lambda: self._select_all(False), kind="ghost", width=130
        ).pack(side="left", padx=(10, 0))

        self.progress = ctk.CTkProgressBar(
            inner, mode="indeterminate", width=170, height=14, progress_color=theme.ACCENT
        )
        self.progress.pack(side="right", padx=(12, 0))
        self.progress.set(0)
        self.status_label = theme.label(
            inner, "Pronto para verificar.", kind="body", color=theme.MUTED
        )
        self.status_label.pack(side="right", padx=(0, 14))

        self.rows_box = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.rows_box.pack(fill="both", expand=True, padx=34, pady=(0, 6))
        self.rows_box.grid_columnconfigure(0, weight=1)
        self._build_rows()

        foot = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=14,
                            border_width=1, border_color=theme.BORDER)
        foot.pack(fill="x", padx=34, pady=(6, 22))
        foot_inner = ctk.CTkFrame(foot, fg_color="transparent")
        foot_inner.pack(fill="x", padx=18, pady=14)
        self.clean_btn = theme.button(
            foot_inner, "Limpar ▸", self.ask_clean, kind="danger", width=200
        )
        self.clean_btn.pack(side="right")
        self.summary = theme.label(
            foot_inner, "Nenhuma verificação ainda.", kind="strong", color=theme.MUTED
        )
        self.summary.pack(side="left")

    # ------------------------------------------------------------------ build
    def _build_rows(self) -> None:
        for index, target in enumerate(TARGETS):
            row = ctk.CTkFrame(
                self.rows_box, fg_color=theme.SURFACE, corner_radius=12,
                border_width=1, border_color=theme.BORDER,
            )
            row.grid(row=index, column=0, sticky="ew", pady=5)
            row.grid_columnconfigure(1, weight=1)

            var = tk.BooleanVar(
                master=self, value=target.id in default_selection()
            )
            box = ctk.CTkCheckBox(
                row, text="", variable=var, onvalue=True, offvalue=False, width=26,
                command=self.update_summary, fg_color=theme.ACCENT,
                border_color=theme.MUTED, hover_color=theme.ACCENT_HOVER,
            )
            box.grid(row=0, column=0, padx=(16, 0), pady=18)

            texts = ctk.CTkFrame(row, fg_color="transparent")
            texts.grid(row=0, column=1, sticky="w", padx=(16, 0), pady=(14, 14))
            theme.label(texts, target.label, kind="strong").pack(anchor="w")
            theme.label(
                texts, target.description, kind="small", color=theme.MUTED
            ).pack(anchor="w", pady=(3, 0))

            if target.risk is Risk.CAUTION:
                badge, badge_color = "atenção", theme.WARNING
            elif target.requires_admin:
                badge, badge_color = "precisa de admin", theme.MUTED
            else:
                badge, badge_color = "seguro", theme.SUCCESS
            theme.label(row, badge, kind="small", color=badge_color).grid(
                row=0, column=2, padx=14, pady=18
            )

            size_label = theme.label(
                row, "—", kind="strong", color=theme.MUTED, width=120, anchor="e"
            )
            size_label.grid(row=0, column=3, padx=(0, 18), pady=18)

            self.rows[target.id] = {"var": var, "size": size_label}

    # ------------------------------------------------------------------ scan
    def start_scan(self) -> None:
        if self.busy:
            return
        self._set_working(True, "Verificando…")

        def work(emit: Callable) -> object:
            return scan_all(progress=lambda result: emit(result.target.label))

        self.run_job(
            work,
            self._scan_done,
            on_progress=lambda label: self.status_label.configure(
                text=f"Verificando {label}…"
            ),
        )

    def _scan_done(self, results: list) -> None:
        total = 0
        count = 0
        for result in results:
            self.sizes[result.target.id] = result.size
            widget = self.rows[result.target.id]["size"]
            if result.files:
                widget.configure(text=human_size(result.size), text_color=theme.TEXT)
                total += result.size
                count += 1
            else:
                widget.configure(text="—", text_color=theme.MUTED)
            if result.errors:
                widget.configure(text_color=theme.WARNING)
        self._set_working(False, "")
        self.status_label.configure(
            text=f"{count} categorias com lixo · {human_size(total)} recuperáveis"
        )
        self.update_summary()

    def _set_working(self, working: bool, status: str) -> None:
        if working:
            self.progress.start()
        else:
            self.progress.stop()
        self.scan_btn.configure(state="disabled" if working else "normal")
        self.clean_btn.configure(state="disabled" if working else "normal")
        if status:
            self.status_label.configure(text=status)

    # --------------------------------------------------------------- limpeza
    def _select_all(self, value: bool) -> None:
        for row in self.rows.values():
            row["var"].set(value)
        self.update_summary()

    def update_summary(self) -> None:
        chosen = [
            tid for tid, row in self.rows.items() if row["var"].get() and self.sizes.get(tid, 0)
        ]
        total = sum(self.sizes.get(tid, 0) for tid in chosen)
        self.summary.configure(
            text=f"{len(chosen)} de {len(TARGETS)} categorias · {human_size(total)} para liberar",
            color=theme.TEXT if chosen else theme.MUTED,
        )
        self.clean_btn.configure(state="normal" if chosen and not self.busy else "disabled")

    def ask_clean(self) -> None:
        chosen = [
            get_target(tid)
            for tid, row in self.rows.items()
            if row["var"].get() and self.sizes.get(tid, 0) > 0
        ]
        if not chosen:
            self.app.set_status("Nada selecionado — verifique e marque as categorias.")
            return
        total = sum(self.sizes.get(t.id, 0) for t in chosen)
        details = "\n".join(
            f"•  {t.label:<36} {human_size(self.sizes.get(t.id, 0))}" for t in chosen
        )
        details += f"\n\n{'TOTAL':<38} {human_size(total)}"

        def confirm() -> None:
            self._do_clean(chosen)

        ConfirmDialog(
            self.app,
            title="Confirmar limpeza",
            message=f"Liberar {human_size(total)} agora?",
            details=details,
            note=(
                "Arquivos em uso serão pulados, nada fora desta lista é tocado "
                "e a operação fica registrada na pasta de logs."
            ),
            confirm_text=f"Limpar {human_size(total)}",
            on_confirm=confirm,
        )

    def _do_clean(self, chosen: list) -> None:
        self._set_working(True, "Limpando…")

        def work(emit: Callable) -> object:
            return clean_targets(
                chosen,
                dry_run=False,
                on_progress=lambda target, _c, _f: emit(target.label),
            )

        self.run_job(
            work,
            self._clean_done,
            on_progress=lambda label: self.status_label.configure(text=f"Limpando {label}…"),
        )

    def _clean_done(self, outcome) -> None:
        self._set_working(False, "")
        message = (
            f"Liberado {human_size(outcome.freed)} · {outcome.deleted} arquivos apagados"
        )
        if outcome.kept:
            message += f" · {outcome.kept} em uso mantidos"
        self.status_label.configure(text=message, color=theme.SUCCESS)
        self.app.record(message, outcome.freed)
        self.start_scan()

    def _reset_ui(self) -> None:
        self._set_working(False, "")
        self.update_summary()


# ====================================================================== PASSO 2
class StepBigFiles(Step):
    def __init__(self, master, app: "App") -> None:
        super().__init__(master, app)
        self.files: list[bigfiles.BigFile] = []
        self.row_vars: list[tuple[tk.BooleanVar, bigfiles.BigFile]] = []
        self.cancel_requested = False
        self.roots = bigfiles.discover_roots()

        self.header(
            "PASSO 2 · ARQUIVOS GRANDES",
            "Agora você escolhe o que sai",
            "Depois da limpeza, o programa procura os arquivos maiores que o limite "
            "e mostra nome, tipo, tamanho e data de criação para você marcar.",
        )

        options = theme.card(self)
        options.pack(fill="x", padx=34, pady=(16, 10))

        top = ctk.CTkFrame(options, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(16, 6))
        theme.label(top, "PASTAS VARRIDAS", kind="label", color=theme.MUTED).pack(side="left")
        self.root_vars: dict[str, tk.BooleanVar] = {}
        for root in self.roots:
            var = tk.BooleanVar(master=self, value=True)
            ctk.CTkCheckBox(
                top, text=root, variable=var, onvalue=True, offvalue=False,
                fg_color=theme.ACCENT, border_color=theme.MUTED,
                hover_color=theme.ACCENT_HOVER, font=theme.FONT_SMALL,
            ).pack(side="left", padx=(16, 0))
            self.root_vars[root] = var

        mid = ctk.CTkFrame(options, fg_color="transparent")
        mid.pack(fill="x", padx=18, pady=(8, 6))
        theme.label(mid, "Tamanho mínimo", kind="body", color=theme.MUTED).pack(side="left")
        self.min_entry = ctk.CTkEntry(
            mid, width=90, height=34, justify="center", fg_color=theme.SURFACE_2,
            border_color=theme.BORDER, text_color=theme.TEXT, font=theme.FONT_BODY,
        )
        self.min_entry.pack(side="left", padx=(10, 6))
        self.min_entry.insert(0, str(bigfiles.DEFAULT_MIN_MB))
        theme.label(mid, "MB", kind="body", color=theme.MUTED).pack(side="left")

        self.recycle_var = tk.BooleanVar(master=self, value=False)
        ctk.CTkSwitch(
            mid, text="Mover para a lixeira", variable=self.recycle_var,
            onvalue=True, offvalue=False, progress_color=theme.ACCENT,
            text_color=theme.MUTED, font=theme.FONT_BODY,
        ).pack(side="right", padx=(0, 16))

        self.cancel_btn = theme.button(
            mid, "Cancelar", self.cancel_scan, kind="ghost", width=110, state="disabled"
        )
        self.cancel_btn.pack(side="right", padx=(0, 10))
        self.start_btn = theme.button(mid, "▶ Iniciar varredura", self.start_scan, width=170)
        self.start_btn.pack(side="right")

        bottom = ctk.CTkFrame(options, fg_color="transparent")
        bottom.pack(fill="x", padx=18, pady=(8, 16))
        self.status_label = theme.label(
            bottom, "Escolha as pastas e o tamanho mínimo.", kind="small", color=theme.MUTED
        )
        self.status_label.pack(anchor="w")
        self.progress = ctk.CTkProgressBar(
            bottom, mode="indeterminate", height=6, progress_color=theme.ACCENT
        )
        self.progress.pack(fill="x", pady=(8, 0))
        self.progress.set(0)

        self.rows_box = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.rows_box.pack(fill="both", expand=True, padx=34, pady=(0, 6))
        self.rows_box.grid_columnconfigure(0, weight=1)

        foot = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=14,
                            border_width=1, border_color=theme.BORDER)
        foot.pack(fill="x", padx=34, pady=(6, 22))
        inner = ctk.CTkFrame(foot, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=14)
        self.delete_btn = theme.button(
            inner, "Excluir ▸", self.ask_delete, kind="danger", width=220, state="disabled"
        )
        self.delete_btn.pack(side="right")
        self.summary = theme.label(inner, "Nenhum arquivo selecionado.", kind="strong",
                                   color=theme.MUTED)
        self.summary.pack(side="left")

    # ------------------------------------------------------------------ scan
    def _min_bytes(self) -> int:
        raw = self.min_entry.get().strip() or str(bigfiles.DEFAULT_MIN_MB)
        try:
            value = float(raw.replace(",", "."))
        except ValueError:
            value = float(bigfiles.DEFAULT_MIN_MB)
        value = min(max(value, 0.0), 1_000_000.0)
        self.min_entry.delete(0, "end")
        self.min_entry.insert(0, f"{value:g}")
        return int(value * 1024 * 1024)

    def start_scan(self) -> None:
        if self.busy:
            return
        roots = [root for root, var in self.root_vars.items() if var.get()]
        if not roots:
            self.app.set_status("Selecione ao menos uma pasta para varrer.")
            return
        min_size = self._min_bytes()
        self.cancel_requested = False
        self._set_working(True)
        self.status_label.configure(text="Varrendo…", color=theme.MUTED)

        def work(emit: Callable) -> object:
            return bigfiles.scan_big_files(
                roots,
                min_size=min_size,
                limit=DISPLAY_LIMIT,
                on_progress=lambda seen, size, _p: emit((seen, size)),
                should_cancel=lambda: self.cancel_requested,
            )

        def on_progress(payload: tuple) -> None:
            seen, seen_size = payload
            self.status_label.configure(
                text=f"{seen} arquivos analisados · {human_size(seen_size)} verificados…"
            )

        self.run_job(work, self._scan_done, on_progress=on_progress)

    def _scan_done(self, found: list) -> None:
        self._set_working(False)
        was_cancelled = self.cancel_requested
        self.cancel_requested = False
        self.files = found
        self._render_rows()
        total = sum(f.size for f in found)
        if was_cancelled:
            self.status_label.configure(
                text=f"Varredura cancelada · {len(found)} maiores já achados ({human_size(total)})",
                color=theme.WARNING,
            )
        else:
            suffix = " (mostrando os maiores)" if len(found) == DISPLAY_LIMIT else ""
            self.status_label.configure(
                text=f"{len(found)} arquivos · {human_size(total)} no total{suffix}",
                color=theme.TEXT,
            )
        self.update_footer()

    def cancel_scan(self) -> None:
        self.cancel_requested = True
        self.status_label.configure(text="Parando a varredura…", color=theme.WARNING)

    def _set_working(self, working: bool) -> None:
        if working:
            self.progress.start()
        else:
            self.progress.stop()
        self.start_btn.configure(state="disabled" if working else "normal")
        self.cancel_btn.configure(state="normal" if working else "disabled")

    # ------------------------------------------------------------------ rows
    def _render_rows(self) -> None:
        for child in self.rows_box.winfo_children():
            child.destroy()
        self.row_vars.clear()

        for index, item in enumerate(self.files):
            row = ctk.CTkFrame(
                self.rows_box, fg_color=theme.SURFACE, corner_radius=10,
                border_width=1, border_color=theme.BORDER,
            )
            row.grid(row=index, column=0, sticky="ew", pady=4)
            row.grid_columnconfigure(1, weight=1)

            var = tk.BooleanVar(master=self, value=False)
            ctk.CTkCheckBox(
                row, text="", variable=var, onvalue=True, offvalue=False, width=26,
                command=self.update_footer, fg_color=theme.ACCENT,
                border_color=theme.MUTED, hover_color=theme.ACCENT_HOVER,
            ).grid(row=0, column=0, padx=(14, 0), pady=14)
            self.row_vars.append((var, item))

            texts = ctk.CTkFrame(row, fg_color="transparent")
            texts.grid(row=0, column=1, sticky="w", padx=(16, 0), pady=(10, 10))
            theme.label(texts, self._shorten(item.name, 70), kind="strong").pack(anchor="w")
            theme.label(
                texts, self._shorten(item.folder, 90), kind="small", color=theme.MUTED
            ).pack(anchor="w", pady=(3, 0))

            chip = ctk.CTkFrame(row, fg_color=theme.SURFACE_2, corner_radius=8)
            chip.grid(row=0, column=2, padx=12, pady=14)
            theme.label(chip, item.kind, kind="small", color=theme.ACCENT).pack(
                padx=10, pady=3
            )

            theme.label(
                row, human_size(item.size), kind="strong", width=90, anchor="e"
            ).grid(row=0, column=3, padx=(0, 10), pady=14)
            theme.label(
                row, item.created_str(), kind="small", color=theme.MUTED, width=90, anchor="e"
            ).grid(row=0, column=4, padx=(0, 16), pady=14)

    @staticmethod
    def _shorten(text: str, keep: int) -> str:
        if len(text) <= keep:
            return text
        return text[: keep // 2] + "…" + text[-(keep // 2):]

    # ---------------------------------------------------------------- delete
    def update_footer(self) -> None:
        chosen = [item for var, item in self.row_vars if var.get()]
        total = sum(item.size for item in chosen)
        if chosen:
            self.summary.configure(
                text=f"{len(chosen)} selecionado(s) · {human_size(total)}",
                color=theme.TEXT,
            )
            self.delete_btn.configure(
                state="normal", text=f"Excluir {human_size(total)} ▸"
            )
        else:
            self.summary.configure(text="Nenhum arquivo selecionado.", color=theme.MUTED)
            self.delete_btn.configure(state="disabled", text="Excluir ▸")

    def ask_delete(self) -> None:
        chosen = [item for var, item in self.row_vars if var.get()]
        if not chosen:
            return
        total = sum(item.size for item in chosen)
        lines = [f"•  {self._shorten(item.name, 58)}   {human_size(item.size)}" for item in chosen[:10]]
        if len(chosen) > 10:
            lines.append(f"... e mais {len(chosen) - 10} arquivo(s)")
        lines.append(f"\nTOTAL{'':<32} {human_size(total)}")

        to_recycle = bool(self.recycle_var.get())
        note = (
            "Será movido para a lixeira do Windows — ainda dá para recuperar depois."
            if to_recycle
            else "EXCLUSÃO PERMANENTE: não vai para a lixeira e não pode ser desfeita. "
            "Confira a seleção antes de confirmar."
        )

        def confirm() -> None:
            self._do_delete(chosen, to_recycle)

        ConfirmDialog(
            self.app,
            title="Excluir arquivos grandes",
            message=f"Remover {human_size(total)} em {len(chosen)} arquivo(s)?",
            details="\n".join(lines),
            note=note,
            confirm_text=f"Excluir {human_size(total)}",
            on_confirm=confirm,
        )

    def _do_delete(self, chosen: list, to_recycle: bool) -> None:
        self._set_working(True)
        self.status_label.configure(text="Excluindo…", color=theme.WARNING)

        def work(_emit: Callable) -> object:
            return bigfiles.delete_files(chosen, to_recycle=to_recycle)

        self.run_job(work, self._delete_done)

    def _delete_done(self, result: tuple) -> None:
        deleted, freed, errors = result
        self._set_working(False)
        self.files = [f for f in self.files if f.path.exists()]
        self._render_rows()
        self.update_footer()

        message = f"{deleted} arquivo(s) · {human_size(freed)} liberados"
        if errors:
            message += f" · {len(errors)} não puderam ser excluídos"
            self.status_label.configure(text=message, color=theme.WARNING)
            self.app.set_status(errors[0])
        else:
            self.status_label.configure(text=message, color=theme.SUCCESS)
        self.app.record(f"Arquivos grandes: {message}", freed)

    def _reset_ui(self) -> None:
        self._set_working(False)
        self.update_footer()


# ====================================================================== PASSO 3
class StepReport(Step):
    def __init__(self, master, app: "App") -> None:
        super().__init__(master, app)
        self.header(
            "PASSO 3 · RELATÓRIO",
            "Tudo que aconteceu nesta sessão",
            "Cada operação também grava um log em JSON dentro da pasta de logs do programa.",
        )

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=34, pady=(16, 10))
        theme.button(bar, "Atualizar", self.refresh, kind="ghost", width=130).pack(side="left")
        theme.button(
            bar, "Abrir pasta de logs", self.open_folder, kind="ghost", width=190
        ).pack(side="left", padx=(10, 0))

        self.textbox = ctk.CTkTextbox(
            self, fg_color=theme.SURFACE, corner_radius=14, border_width=1,
            border_color=theme.BORDER, text_color=theme.TEXT, font=theme.FONT_SMALL,
        )
        self.textbox.pack(fill="both", expand=True, padx=34, pady=(0, 22))
        self.refresh()

    def refresh(self) -> None:
        lines = ["SESSÃO ATUAL", "=" * 62]
        events = self.app.session["events"]
        if events:
            for event in events:
                lines.append(f"  {event['hora']}   {event['texto']}")
        else:
            lines.append("  (nenhuma operação executada ainda)")

        logs = report.list_logs(limit=8)
        lines += ["", "LOGS GRAVADOS", "=" * 62]
        if logs:
            for path in logs:
                lines.append(f"  {path.name}")
            lines += ["", "ÚLTIMO LOG", "=" * 62, report.format_log(report.read_log(logs[0]))]
        else:
            lines.append("  (nenhum log gravado ainda)")

        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", "\n".join(lines))
        self.textbox.configure(state="disabled")

    def open_folder(self) -> None:
        folder = report.log_dir()
        try:
            if os.name == "nt":
                os.startfile(folder)  # noqa: S606 - ação do usuário
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            self.app.set_status(f"Pasta: {folder}  ({exc})")


# ====================================================================== JANELA
class App(ctk.CTk):
    def __init__(self) -> None:
        theme.apply()
        super().__init__(fg_color=theme.BG)
        self.title("Win Janitor — limpeza de arquivos")
        self.geometry("1140x760")
        self.minsize(1000, 660)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.session: dict = {"freed": 0, "events": []}
        self._build_sidebar()

        self.steps: dict[str, Step] = {
            "clean": StepClean(self, self),
            "big": StepBigFiles(self, self),
            "report": StepReport(self, self),
        }
        for step in self.steps.values():
            step.grid(row=0, column=1, sticky="nsew")

        self.show("clean")
        self.set_status("Verificando o que dá para limpar…")
        self.steps["clean"].start_scan()

    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, width=252, fg_color=theme.SURFACE, corner_radius=0)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(3, weight=1)

        theme.label(side, "◆  WIN JANITOR", kind="heading", color=theme.TEXT).grid(
            row=0, column=0, padx=22, pady=(28, 2), sticky="w"
        )
        theme.label(side, "limpeza segura de arquivos", kind="small",
                    color=theme.MUTED).grid(row=1, column=0, padx=22, pady=(0, 24), sticky="w")

        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        nav = ctk.CTkFrame(side, fg_color="transparent")
        nav.grid(row=2, column=0, padx=16, sticky="ew")
        nav.grid_columnconfigure(0, weight=1)
        for index, key in enumerate(NAV_ORDER):
            btn = theme.button(
                nav, NAV_TITLES[key], lambda k=key: self.show(k),
                kind="ghost", anchor="w", height=44,
            )
            btn.grid(row=index, column=0, pady=4, sticky="ew")
            self.nav_buttons[key] = btn

        bottom = ctk.CTkFrame(side, fg_color="transparent")
        bottom.grid(row=4, column=0, padx=16, pady=(0, 20), sticky="ew")

        card = theme.card(bottom, fg_color=theme.SURFACE_2)
        card.pack(fill="x")
        theme.label(card, "LIBERADO NESTA SESSÃO", kind="label",
                    color=theme.MUTED).pack(anchor="w", padx=16, pady=(14, 2))
        self.freed_label = theme.label(card, "0 B", kind="number", color=theme.SUCCESS)
        self.freed_label.pack(anchor="w", padx=16, pady=(0, 14))

        self.status_label = theme.label(
            bottom, "Pronto.", kind="small", color=theme.MUTED,
            wraplength=214, justify="left",
        )
        self.status_label.pack(anchor="w", padx=2, pady=(14, 0))

    # --------------------------------------------------------------- plumbing
    def show(self, key: str) -> None:
        step = self.steps[key]
        step.tkraise()
        if hasattr(step, "refresh"):
            step.refresh()
        for nav_key, btn in self.nav_buttons.items():
            if nav_key == key:
                btn.configure(fg_color=theme.SURFACE_2, text_color=theme.ACCENT,
                              hover_color=theme.SURFACE_2)
            else:
                btn.configure(fg_color="transparent", text_color=theme.MUTED,
                              hover_color=theme.SURFACE_2)

    def set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    def record(self, text: str, freed: int = 0) -> None:
        self.session["freed"] += freed
        self.session["events"].append(
            {"hora": time.strftime("%H:%M:%S"), "texto": text}
        )
        self.freed_label.configure(text=human_size(self.session["freed"]))
        self.set_status(text)


def run() -> None:
    App().mainloop()
