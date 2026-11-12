"""Applies the theme tokens to Qt itself, so menus, lists and dialogs match the canvas."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from homelab_maker.gui.theme import Scheme, Tokens, choose, contrast


def system_is_dark() -> bool:
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def tokens_for(scheme: Scheme) -> Tokens:
    return choose(scheme, system_is_dark())


def build_palette(tokens: Tokens) -> QPalette:
    # Selected text goes on the accent: white or the background, whichever reads better.
    on_accent = max(("#ffffff", tokens.background), key=lambda c: contrast(c, tokens.accent))
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: tokens.background,
        QPalette.ColorRole.WindowText: tokens.text,
        QPalette.ColorRole.Base: tokens.card,
        QPalette.ColorRole.AlternateBase: tokens.background,
        QPalette.ColorRole.Text: tokens.text,
        QPalette.ColorRole.Button: tokens.card,
        QPalette.ColorRole.ButtonText: tokens.text,
        QPalette.ColorRole.ToolTipBase: tokens.card,
        QPalette.ColorRole.ToolTipText: tokens.text,
        QPalette.ColorRole.PlaceholderText: tokens.text_muted,
        QPalette.ColorRole.Highlight: tokens.accent,
        QPalette.ColorRole.HighlightedText: on_accent,
        QPalette.ColorRole.Link: tokens.accent,
        QPalette.ColorRole.BrightText: tokens.danger,
    }
    for role, colour in roles.items():
        palette.setColor(role, QColor(colour))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(tokens.text_muted))
    return palette


def apply(app: QApplication, tokens: Tokens) -> None:
    app.setStyle("Fusion")  # the one style that follows a custom palette on every platform
    app.setPalette(build_palette(tokens))
