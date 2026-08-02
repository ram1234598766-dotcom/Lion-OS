"""Built-in application registry loader for Lion-OS."""

from .base import App, AppRegistry, registry

# Apps that open automatically after login
AUTO_LAUNCH = ["Welcome"]


def load_apps() -> AppRegistry:
    """Import and register every built-in app. Idempotent."""
    if registry.all():
        return registry
    from . import (about, calculator, filemanager, monitor, notes, paint,
                   settings, terminal, texteditor, welcome, assistant,
                   mediaplayer, browser, appstore, widgets_demo, devices, help,
                   inbox, health, today)
    registry.register_all([
        about.AboutApp,
        calculator.CalculatorApp,
        filemanager.FileManagerApp,
        monitor.SystemMonitorApp,
        notes.NotesApp,
        paint.PaintApp,
        settings.SettingsApp,
        terminal.TerminalApp,
        texteditor.TextEditorApp,
        welcome.WelcomeApp,
        assistant.AIAssistantApp,
        mediaplayer.MediaPlayerApp,
        browser.BrowserApp,
        appstore.AppStoreApp,
        widgets_demo.WidgetsDemoApp,
        devices.DevicesApp,
        help.HelpApp,
        inbox.InboxApp,
        health.SystemHealthApp,
        today.TodayApp,
    ])
    return registry


def get_apps():
    """Return the list of registered app classes (stable order)."""
    load_apps()
    return [registry.get(n) for n in registry.all()]
