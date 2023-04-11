import os

from bs4 import BeautifulSoup as BS
from importlib.util import find_spec
from contextlib import chdir
from jinja2 import Environment, BaseLoader
from watchfiles import watch

from multiprocessing import Process

import subprocess
from pathlib import Path
from copier import run_auto
import shutil
import click
from rich import print


@click.group()
def cli():
    ...


@cli.command
@click.argument("path", type=click.Path(file_okay=False, path_type=Path))
@click.pass_context
def new(ctx: click.Context, path: Path):
    if path.exists():
        print("[red]Path already exists")
        ctx.exit()

    print(f"[green]Creating app in [yellow]{path}")
    run_auto("templates/default", path)


jinja_env = Environment(loader=BaseLoader())

ENDPOINT_TEMPLATE = jinja_env.from_string(
    """
@bp.get("{{route}}", name="{{name}}")
{{code}}
    return await render("{{template}}", context=locals())
"""
)


def _build(restart=False):
    base = Path("test")
    src = base / "src"

    build_root = Path("build")

    if not restart:
        shutil.rmtree(build_root, ignore_errors=True)

    build = build_root / "app"
    build.mkdir(exist_ok=True, parents=True)

    (build / "__init__.py").touch()

    (build / "blueprints").mkdir(exist_ok=True)
    (build / "blueprints" / "__init__.py").touch()
    (build / "middleware").mkdir(exist_ok=True)
    templates = build_root / "templates"
    templates.mkdir(exist_ok=True)

    # Make the server
    shutil.copy(find_spec("sanic_kit.template.server").origin, build / "server.py")

    app_blueprint = """
from sanic import Blueprint
from sanic_ext import render


bp = Blueprint("app")

"""

    for route in (src / "routes").glob("**/*.sanic"):
        print(route)
        (build / route.parent).mkdir(parents=True, exist_ok=True)
        # (templates / route.parent).mkdir(parents=True, exist_ok=True)

        shutil.copy(route, build / route)

        template_name = f"{str(route.with_suffix('')).replace(os.sep, '_')}.html"

        html = BS(route.read_text(), "html.parser")
        if script := html.find("script"):
            python = script.extract().text.lstrip()
            # Create the code
            app_blueprint += ENDPOINT_TEMPLATE.render(
                route=str(route.relative_to(src / "routes").parent).replace(os.sep, "/").replace(".", "/"),
                name=str(route.relative_to(src / "routes").parent).replace(os.sep, "_").replace(".", "index"),
                template=template_name,
                code=python,
            )

        # Create our template
        match route.stem:
            case "+page":
                (templates / template_name).write_text(
                    """{% extends "test_src_routes_+layout.html" %}\n\n""" + html.prettify()
                )
            case "+layout":
                (templates / template_name).write_text("""{% extends "index.html" %}\n\n""" + html.prettify())

    (build / "blueprints" / "app.py").write_text(app_blueprint)

    shutil.copy(src / "index.html", templates)


@cli.command
def build():
    _build()


def watch_files():
    try:
        for change in watch(Path("test")):
            _build(restart=True)
    except KeyboardInterrupt:
        pass


@cli.command
def run():
    _build()
    file_watcher = Process(target=watch_files)
    file_watcher.start()
    try:
        with chdir(Path("build")):
            proc = subprocess.run(["sanic", "app.server:create_app", "--debug", "--dev"], check=True)
    except KeyboardInterrupt:
        file_watcher.close()


if __name__ == "__main__":
    cli()
