from pathlib import Path

import tomlkit
from rich import print
from textual.app import App
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import (Checkbox, DirectoryTree, Footer, Header, Label,
                             TabbedContent)


class Logo(Label):
    def render(self):
        return """\
[white on #ea386b]                     
   ▄███ █████ ██     
   ██                
    ▀███████ ███▄    
                ██   
   ████ ████████▀    
                     """


class Config(Widget):
    DEFAULT_CSS = """
    Config {
            height: auto;
            }
    Config > Label {
            padding: 1;
            }
    """

    class AddUnpkg(Message):
        def __init__(self, package):
            super().__init__()
            self.package = package

    class RemoveUnpkg(Message):
        def __init__(self, package):
            super().__init__()
            self.package = package

    class AddStylesheet(Message):
        def __init__(self, stylesheet):
            super().__init__()
            self.stylesheet = stylesheet

    class RemoveStylesheet(Message):
        def __init__(self, stylesheet):
            super().__init__()
            self.stylesheet = stylesheet

    class ToggleTailwind(Message):
        def __init__(self, value):
            super().__init__()
            self.value = value

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.unpkg_config = config["sanic-kit"].get("unpkg", [])
        self.stylesheets_config = config["sanic-kit"].get("stylesheet", [])

    STYLESHEETS = {
        "classless": "https://classless.de/classless.css",
        "Pico": "https://www.jsdelivr.com/package/npm/@picocss/pico",
    }

    UNPKG = {
        "HTMX": "htmx.org",
        "Hyperscript": "hyperscript.org",
        "AlpineJs": "alpinejs",
        "Petite-Vue": "petite-vue",
    }

    def compose(self):
        yield Label("JavaScript Libraries")
        for pkg, value in self.UNPKG.items():
            yield Checkbox(pkg, value=value in self.unpkg_config)
        yield Label("CSS Libraries")
        for css, value in self.STYLESHEETS.items():
            yield Checkbox(css, value=value in self.stylesheets_config)
        yield Checkbox("Tailwind", value=self.config["sanic-kit"].get("tailwind"))

    def on_checkbox_changed(self, event: Checkbox.Changed):
        label = str(event.checkbox.label)
        if label in self.UNPKG:
            if event.checkbox.value:
                self.post_message(self.AddUnpkg(self.UNPKG[label]))
            else:
                self.post_message(self.RemoveUnpkg(self.UNPKG[label]))
        if label in self.STYLESHEETS:
            if event.checkbox.value:
                self.post_message(self.AddStylesheet(self.STYLESHEETS[label]))
            else:
                self.post_message(self.RemoveStylesheet(self.STYLESHEETS[label]))
        if label == "Tailwind":
            self.post_message(self.ToggleTailwind(event.checkbox.value))


class SanicKit(App):
    CSS = """
    DirectoryTree {
            height: auto;
            }
    Logo {
        width: 23;
        margin: 2;
    }
    """

    async def on_load(self):
        if (pyproj := Path("pyproject.toml")).exists():
            self.config = tomlkit.parse(pyproj.read_text())
            if "sanic-kit" not in self.config:
                self.config["sanic-kit"] = tomlkit.table()
        else:
            print("[yellow]pyproject.toml[/yellow] [red]not found")
            await self.action_quit()

    def add_to_list(self, list_name, item):
        sk_table = self.config["sanic-kit"]
        if list_name not in sk_table:
            sk_table.add(list_name, [item])
        elif item not in sk_table[list_name]:
            sk_table[list_name].append(item)
        self.save_config()

    def remove_from_list(self, list_name, item):
        sk_table = self.config["sanic-kit"]
        if list_name in sk_table and item in sk_table[list_name]:
            sk_table[list_name].remove(item)
        self.save_config()

    def on_config_add_unpkg(self, message):
        package = message.package
        self.add_to_list("unpkg", package)

    def on_config_remove_unpkg(self, message):
        package = message.package
        self.remove_from_list("unpkg", package)

    def on_config_add_stylesheet(self, message):
        stylesheet = message.stylesheet
        self.add_to_list("stylesheet", stylesheet)

    def on_config_remove_stylesheet(self, message):
        stylesheet = message.stylesheet
        self.remove_from_list("stylesheet", stylesheet)

    def on_config_toggle_tailwind(self, message):
        self.config["sanic-kit"]["tailwind"] = message.value
        self.save_config()

    def save_config(self):
        Path("pyproject.toml").write_text(tomlkit.dumps(self.config))

    def compose(self):
        yield Header()
        with Horizontal():
            yield Logo()
            with TabbedContent("Config", "Routes", "Server"):
                yield Config(self.config)
                yield DirectoryTree("./src/routes")
                yield Label("hello")
        yield Footer()
