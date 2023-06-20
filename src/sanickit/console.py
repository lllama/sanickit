import asyncio
import os
import subprocess
import sys
from contextlib import chdir, contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

import tomlkit
from rich import print
from textual import work
from textual.app import App
from textual.binding import Binding
from textual.containers import Grid, Horizontal
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import (Button, Checkbox, DirectoryTree, Footer, Header,
                             Input, Label, TabbedContent, TextLog)
from textual.widgets._directory_tree import DirEntry
from watchfiles import awatch

from .cli import _build as build_app
from .cli import download_tailwind

SANIC_EXE = Path(sys.executable).parent / "sanic"


class NewRoute(ModalScreen):
    class CreateRoute(Message):
        def __init__(self, route):
            super().__init__()
            self.route = route

    def on_mount(self):
        self.query_one(Input).focus()

    def compose(self):
        with Grid(id="newroute"):
            yield Label("Add new route")
            yield Input(placeholder="new route")

    def on_input_submitted(self, event):
        self.app.post_message(self.CreateRoute(event.input.value))
        self.app.pop_screen()


class Logo(Label):
    def render(self):
        return (
            "[white on #ea386b]"
            "                     \n"
            "   ▄███ █████ ██     \n"
            "   ██                \n"
            "    ▀███████ ███▄    \n"
            "                ██   \n"
            "   ████ ████████▀    \n"
            "                     \n"
        )


class Config(Widget):
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
        self.unpkg_config = config["sanickit"].get("unpkgs", [])
        self.stylesheets_config = config["sanickit"].get("stylesheets", [])

    STYLESHEETS = {
        "classless": "https://classless.de/classless.css",
        "Pico": "https://www.jsdelivr.com/package/npm/@picocss/pico",
    }

    UNPKG = {
        "HTMX": "htmx.org",
        "Hyperscript": "hyperscript.org",
        "AlpineJs": "alpinejs",
    }

    def compose(self):
        yield Label("JavaScript Libraries")
        for pkg, value in self.UNPKG.items():
            yield Checkbox(pkg, value=value in self.unpkg_config)

        yield Label("CSS Libraries")
        for css, value in self.STYLESHEETS.items():
            yield Checkbox(css, value=value in self.stylesheets_config)

        yield Checkbox("Tailwind", value=self.config["sanickit"].get("tailwind"))

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


class Server(Widget):
    def __init__(self):
        super().__init__()
        self.server_process = None
        self.tailwind_process = None

    def compose(self):
        with Horizontal():
            yield Button("Start", id="start")
            yield Button("Reload", id="reload", disabled=True)
            yield Button("Stop", id="stop", disabled=True)
        yield TextLog(auto_scroll=True)

    async def run_inspector(self, command):
        process = await asyncio.subprocess.create_subprocess_exec(
            *[SANIC_EXE, "inspect", "reload"],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.wait()

    async def on_button_pressed(self, event):
        button = event.button
        match button.id:
            case "start":
                button.disabled = True
                self.query_one("#reload").disabled = False
                self.query_one("#stop").disabled = False
                self.start_tailwind()
                self.watch_files()
                self.start_server()
            case "reload":
                await self.run_inspector("reload")
            case "stop":
                button.disabled = True
                self.query_one("#reload").disabled = True
                self.query_one("#start").disabled = False
                await self.run_inspector("shutdown")

            case _:
                self.query_one(TextLog).write("Some random button got pressed")

    @work(exclusive=True, group="watcher")
    async def watch_files(self):
        async for _ in awatch(Path("./src")):
            build_app(restart=True, quiet=True)

    @work(exclusive=True, group="tailwind")
    def start_tailwind(self):
        download_tailwind()

        self.tailwind_process = process = subprocess.Popen(
            [
                "./.sanickit/tailwindcss",
                "--poll",
                "--watch",
                "./src",
                "--output",
                "./build/app/static/tailwind.css",
                "--config",
                "./.sanickit/tailwind.config.js",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        process.wait()

    @work(exclusive=True, group="server")
    async def start_server(self):
        text_log = self.query_one(TextLog)

        build_app()

        my_env = os.environ.copy()
        my_env["SANIC_INSPECTOR"] = "True"

        with chdir(Path("build")):
            self.server_process = process = await asyncio.subprocess.create_subprocess_exec(
                *[
                    SANIC_EXE,
                    "app.server:create_app",
                    "--debug",
                    "--dev",
                    "--no-motd",
                    "--coffee",
                ],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=my_env,
            )

        while line := await process.stdout.readline():
            text_log.write(line.decode().rstrip())

        await process.wait()
        self.query_one("#start").disabled = False
        self.query_one("#reload").disabled = True
        self.query_one("#stop").disabled = True

    def on_unmount(self, _):
        if self.server_process:
            self.server_process.terminate()
        if self.tailwind_process:
            self.tailwind_process.terminate()


class Routes(Widget):
    def __init__(self, root):
        super().__init__()
        self.root = root

    def update_preview(self, node):
        textlog = self.query_one(TextLog)
        textlog.clear()
        textlog.write(Path(node.path).read_text())

    def on_tree_node_highlighted(self, event):
        if not event.node.data.path.is_dir():
            self.update_preview(event.node.data)

    def on_directory_tree_file_selected(self, event):
        self.update_preview(event)

    def compose(self):
        with Horizontal():
            yield Button("Add route", id="addroute")
            yield Button("Add layout")
        with Horizontal():
            yield DirectoryTree(self.root)
            yield TextLog(highlight=True, classes="hidden")

    async def refresh_tree(self, path_to_select):
        tree = self.query_one(DirectoryTree)
        await tree.remove()
        text_log = self.query_one(TextLog)
        await self.mount(DirectoryTree(self.root), before=text_log)
        tree = self.query_one(DirectoryTree)

        path_parts = path_to_select.relative_to(self.root).parts

        node = tree.root
        current_path = Path(self.root)
        for part in path_parts:
            node = [n for n in node.children if Path(n.data.path) == current_path / part][0]
            if node.data.path.is_dir():
                tree.load_directory(node)
            else:
                tree.select_node(node)
            current_path = current_path / part

        tree.select_node(node)


class SanicKit(App):
    CSS_PATH = "console.css"

    BINDINGS = [
        Binding(key="q", action="quit", description="Quit the app"),
        Binding(key="a", action="add_route", description="Add route"),
        Binding(key="e", action="edit_route", description="Edit route"),
    ]

    @contextmanager
    def suspend(self):
        driver = self._driver
        if driver is not None:
            driver.stop_application_mode()

            with redirect_stdout(sys.__stdout__), redirect_stderr(sys.__stderr__):
                yield

            driver.start_application_mode()

    def action_add_route(self):
        self.push_screen(NewRoute())

    async def action_edit_route(self):
        tree = self.query_one(DirectoryTree)
        if not (file := tree.cursor_node.data).path.is_dir():
            self.log(f"editing file {file.path}")
            with self.suspend():
                process = await asyncio.subprocess.create_subprocess_exec(
                    *[os.environ["EDITOR"], file.path],
                )
                await process.wait()
            self.query_one(Routes).update_preview(file)

    async def on_load(self):
        if (pyproj := Path("pyproject.toml")).exists():
            self.config = tomlkit.parse(pyproj.read_text())
            if "sanickit" not in self.config:
                self.config["sanickit"] = tomlkit.table()
        else:
            print("[yellow]pyproject.toml[/yellow] [red]not found")
            await self.action_quit()

    def add_to_list(self, list_name, item):
        sk_table = self.config["sanickit"]
        if list_name not in sk_table:
            sk_table.add(list_name, [item])
        elif item not in sk_table[list_name]:
            sk_table[list_name].append(item)
        self.save_config()

    def remove_from_list(self, list_name, item):
        sk_table = self.config["sanickit"]
        if list_name in sk_table and item in sk_table[list_name]:
            sk_table[list_name].remove(item)
        self.save_config()

    def on_config_add_unpkg(self, message):
        package = message.package
        self.add_to_list("unpkgs", package)

    def on_config_remove_unpkg(self, message):
        package = message.package
        self.remove_from_list("unpkgs", package)

    def on_config_add_stylesheet(self, message):
        stylesheet = message.stylesheet
        self.add_to_list("stylesheets", stylesheet)

    def on_config_remove_stylesheet(self, message):
        stylesheet = message.stylesheet
        self.remove_from_list("stylesheets", stylesheet)

    def on_config_toggle_tailwind(self, message):
        self.config["sanickit"]["tailwind"] = message.value
        self.save_config()

    def save_config(self):
        Path("pyproject.toml").write_text(tomlkit.dumps(self.config))

    def on_button_pressed(self, event):
        match event.button.id:
            case "addroute":
                self.push_screen(NewRoute())

    async def on_new_route_create_route(self, message):
        route = Path(message.route)
        if route.is_absolute():
            route = route.relative_to("/")

        new_dir = Path("src/routes") / route
        new_dir.mkdir(exist_ok=True, parents=True)
        new_page = new_dir / "+page.sanic"
        if not new_page.exists():
            new_page.touch()
            new_page.write_text(
                """\
<handler>
</handler>
{% block main %}
{% endblock %}
"""
            )
        await self.query_one(Routes).refresh_tree(new_page)

    def compose(self):
        yield Header()
        with Horizontal():
            yield Logo()
            with TabbedContent("Routes", "Server", "Config"):
                yield Routes("./src/routes")
                yield Server()
                yield Config(self.config)
        yield Footer()
