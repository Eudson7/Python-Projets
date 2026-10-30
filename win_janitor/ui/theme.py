"""Paleta e elementos visuais — tema escuro, direto e moderno."""

from __future__ import annotations

import customtkinter as ctk

# Fundo grafite, superfícies em camadas, acento azul, vermelho só para destruir.
BG = "#0d1117"
SURFACE = "#151a21"
SURFACE_2 = "#1c232c"
BORDER = "#2b333d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#2f81f7"
ACCENT_HOVER = "#1f6feb"
DANGER = "#f85149"
DANGER_HOVER = "#da3633"
SUCCESS = "#2ea043"
WARNING = "#e3b341"

FONT_TITLE = ctk.CTkFont(size=30, weight="bold")
FONT_H = ctk.CTkFont(size=21, weight="bold")
FONT_LABEL = ctk.CTkFont(size=11, weight="bold")
FONT_STRONG = ctk.CTkFont(size=15, weight="bold")
FONT_BODY = ctk.CTkFont(size=14)
FONT_SMALL = ctk.CTkFont(size=12)
FONT_NUMBER = ctk.CTkFont(size=23, weight="bold")

_STYLES = {
    "accent": (ACCENT, ACCENT_HOVER, "#ffffff"),
    "danger": (DANGER, DANGER_HOVER, "#ffffff"),
    "ghost": ("transparent", SURFACE_2, TEXT),
    "plain": (SURFACE_2, BORDER, TEXT),
}


def apply() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")


def button(
    master,
    text: str,
    command=None,
    kind: str = "accent",
    height: int = 40,
    font=None,
    **kwargs,
) -> ctk.CTkButton:
    """Botão no padrão visual do app: accent / danger / ghost."""
    fg, hover, text_color = _STYLES[kind]
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        fg_color=fg,
        hover_color=hover,
        text_color=text_color,
        border_width=1 if kind == "ghost" else 0,
        border_color=BORDER,
        corner_radius=10,
        height=height,
        font=font or FONT_BODY,
        **kwargs,
    )


def card(master, **kwargs) -> ctk.CTkFrame:
    kwargs.setdefault("fg_color", SURFACE)
    kwargs.setdefault("corner_radius", 14)
    kwargs.setdefault("border_width", 1)
    kwargs.setdefault("border_color", BORDER)
    return ctk.CTkFrame(master, **kwargs)


def label(
    master,
    text: str,
    kind: str = "body",
    color: str | None = None,
    **kwargs,
) -> ctk.CTkLabel:
    fonts = {
        "title": FONT_TITLE,
        "heading": FONT_H,
        "label": FONT_LABEL,
        "strong": FONT_STRONG,
        "body": FONT_BODY,
        "small": FONT_SMALL,
        "number": FONT_NUMBER,
    }
    return ctk.CTkLabel(
        master,
        text=text,
        font=fonts.get(kind, FONT_BODY),
        text_color=color or TEXT,
        **kwargs,
    )
