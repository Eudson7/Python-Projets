"""Caixa de confirmação usada antes de qualquer exclusão."""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from . import theme


class ConfirmDialog(ctk.CTkToplevel):
    """Janela modal: título, resumo, detalhes e dois botões (cancelar / confirmar)."""

    def __init__(
        self,
        master,
        *,
        title: str,
        message: str,
        details: str = "",
        note: str = "",
        confirm_text: str = "Confirmar",
        danger: bool = True,
        on_confirm: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._on_confirm = on_confirm
        self.title("")
        self.geometry("520x440")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.configure(fg_color=theme.BG)

        body = theme.card(self)
        body.pack(fill="both", expand=True, padx=18, pady=18)

        accent = theme.DANGER if danger else theme.ACCENT
        theme.label(body, title.upper(), kind="label", color=accent).pack(
            anchor="w", padx=22, pady=(20, 6)
        )
        theme.label(body, message, kind="heading").pack(anchor="w", padx=22)

        if details:
            detail_box = ctk.CTkTextbox(
                body,
                height=150,
                fg_color=theme.SURFACE_2,
                corner_radius=10,
                text_color=theme.TEXT,
                font=theme.FONT_SMALL,
                border_width=1,
                border_color=theme.BORDER,
            )
            detail_box.pack(fill="both", expand=True, padx=22, pady=(14, 0))
            detail_box.insert("1.0", details)
            detail_box.configure(state="disabled")

        if note:
            theme.label(
                body, note, kind="small", color=theme.MUTED, wraplength=440, justify="left"
            ).pack(anchor="w", padx=22, pady=(12, 0))

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.pack(fill="x", padx=22, pady=(18, 20))

        theme.button(
            actions,
            "Cancelar",
            self.destroy,
            kind="ghost",
            width=140,
        ).pack(side="right", padx=(10, 0))
        theme.button(
            actions,
            confirm_text,
            self._confirm,
            kind="danger" if danger else "accent",
            width=200,
        ).pack(side="right")

        self.after(60, self._focus)

    def _focus(self) -> None:
        self.focus_force()
        self.lift()

    def _confirm(self) -> None:
        callback = self._on_confirm
        self.destroy()
        if callback is not None:
            callback()
