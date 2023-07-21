import os
import platform
import shutil
import stat
import subprocess
import sys
from contextlib import chdir
from dataclasses import asdict, dataclass
from importlib.util import find_spec
from multiprocessing import Process
from pathlib import Path
from textwrap import dedent

import click
import httpx
import tomlkit
from bs4 import BeautifulSoup as BS
from copier import run_copy
from jinja2 import BaseLoader, Environment
from rich import print
from rich.markup import escape
from tomlkit import loads
from watchfiles import watch

from .code import extract_api, extract_imports


@dataclass
class Config:
    project: str
    unpkgs: list[str]
    stylesheets: list[str]
    tailwind: bool = False


@click.group()
@click.pass_context
def cli(ctx):
    ...


def get_config():
    if Path("pyproject.toml").exists():
        pyproject = loads(Path("pyproject.toml").read_text())
    elif Path("sanickit.toml").exists():
        pyproject = loads(Path("sanickit.toml").read_text())
    else:
        Path("sanickit.toml").touch()
        pyproject = {}
        pyproject["project"] = {}
        pyproject["project"]["name"] = Path(".").absolute().stem
        Path("sanickit.toml").write_text(tomlkit.dumps(pyproject))

    sk_config = pyproject.get("sanickit", {})

    config = Config(
        project=pyproject["project"]["name"],
        unpkgs=list(sk_config.get("unpkgs", [])),
        stylesheets=list(sk_config.get("stylesheets", [])),
        tailwind=sk_config.get("tailwind", False),
    )

    return config


@cli.command
@click.pass_context
@click.argument("path", type=click.Path(file_okay=False, path_type=Path))
def new(ctx, path: Path):
    print(f"[green]Creating app in [yellow]{path}")

    template = Path(__file__).parent / "template" / "default"
    run_copy(str(template), path, data={"project": path.stem})

    Path("./.sanickit").mkdir(exist_ok=True)

    for route in path.glob("**/.gitkeep"):
        route.unlink()

    download_tailwind()


def get_os_and_arch():
    os_name = platform.system().lower()
    machine_arch = platform.machine().lower()
    if os_name == "darwin":
        if machine_arch == "arm64":
            return "macos-arm64"
        elif machine_arch == "x86_64":
            return "macos-x64"
    elif os_name == "windows":
        if machine_arch == "arm64":
            return "windows-arm64.exe"
        elif machine_arch == "amd64":
            return "windows-x64.exe"
    elif os_name == "linux":
        if machine_arch == "aarch64":
            return "linux-arm64"
        elif machine_arch == "armv7l":
            return "linux-armv7"
        elif machine_arch == "x86_64":
            return "linux-x64"
    return None

def download_tailwind():
    os_arch = get_os_and_arch()
    if os_arch is None:
        print("Unsupported OS or architecture.")
        return

    tailwind_url = f"https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-{os_arch}"
    
    Path("./.sanickit").mkdir(exist_ok=True)

    tailwind_executable = Path("./.sanickit") / "tailwindcss"
    tailwind_config = Path("./.sanickit") / "tailwind.config.js"

    if not tailwind_executable.exists():
        with open(tailwind_executable, "wb") as f:
            response = httpx.get(tailwind_url, follow_redirects=True)
            f.write(response.content)
        tailwind_executable.chmod(stat.S_IEXEC | stat.S_IREAD | stat.S_IWRITE)

    if not tailwind_config.exists():
        tailwind_config.write_text(
            dedent(
                """\
            /** @type {import('tailwindcss').Config} */
            module.exports = {
              content: ['./src/**/*.{html,sanic}'],
              theme: {
                extend: {},
              },
              plugins: [],
            }

                """
            )
        )


jinja_env = Environment(loader=BaseLoader())

IMPORTS_TEMPLATE = jinja_env.from_string(
    """\
{%- for import in imports -%}
{{- import }}
{% endfor %}
"""
)
ENDPOINT_TEMPLATE = jinja_env.from_string(
    """\

@bp.{{method|lower}}("{{route}}", name="{{route_name}}")
{%- if fragments %}
@bp.{{method|lower}}("{{route}}{%- if route != '/' %}/{% endif %}<fragment:{{fragments}}>", name="{{route_name}}-fragments")
{%- endif %}
{{code}}

"""
)


def handle_server(src, route, template_name):
    parameters = [x[1:-1] for x in route.parts if x.startswith("[") and x.endswith("]")]
    route_url = (
        str(route.relative_to(src / "routes").parent)
        .replace(os.sep, "/")
        .replace(".", "/")
        .replace("[", "<")
        .replace("]", ">")
    )

    name = (
        str(route.relative_to(src / "routes").parent)
        .replace(os.sep, "_")
        .replace(".", "index")
        .replace("[", "")
        .replace("]", "")
    )
    imports, handlers = extract_api(route, name, template_name, parameters)
    # Create the code
    code = [
        ENDPOINT_TEMPLATE.render(
            route=route_url,
            name=handler.name,
            method=handler.method,
            template=template_name,
            code=handler.code,
        )
        for handler in handlers
    ]

    return "\n".join(code), imports


def find_nearest_layout(route):
    while not (layout := route.parent / "+layout.html").exists():
        route = route.parent
        if route.stem == "src":
            break
    return layout.relative_to("src")


def handle_page(src, route, templates, template_name):
    html = BS(route.read_text(), "html.parser")

    layout = find_nearest_layout(route)
    layout_name = str(layout.as_posix()).replace("[", "").replace("]", "")

    parameters = [x[1:-1] for x in route.parts if x.startswith("[") and x.endswith("]")]
    name = route_name = (
        str(route.relative_to(src / "routes").parent)
        .replace(os.sep, "_")
        .replace(".", "index")
        .replace("[", "")
        .replace("]", "")
    )
    if script := html.find("handler"):
        route_name = script.attrs.get("route-name", name)
        python = dedent(script.extract().text)
        imports, python = extract_imports(python, name, template_name, parameters)

        url_parts = []
        for part in route.relative_to(src / "routes").parent.parts:
            if part.startswith("[") and part.endswith("]"):
                param = part[1:-1]
                if param_type := script.attrs.get(param):
                    url_parts.append(f"<{param}:{param_type}>")
                else:
                    url_parts.append(f"<{param}>")
            else:
                url_parts.append(str(part))

        route_url = "/".join(url_parts)

    else:
        route_url = (
            str(route.relative_to(src / "routes").parent)
            .replace(os.sep, "/")
            .replace(".", "/")
            .replace("[", "<")
            .replace("]", ">")
        )

        imports, python = extract_imports("", name, template_name, parameters)

    fragments = jinja_env.from_string(html.prettify()).blocks.keys()
    fragments_regex = f"({'|'.join(fragments)})"

    # Write our template
    (templates / template_name).write_text(f"""{{% extends "{layout_name}" %}}\n\n""" + html.prettify())

    return (
        ENDPOINT_TEMPLATE.render(
            route=route_url,
            route_name=route_name,
            method="get",
            template=template_name,
            fragments=fragments_regex,
            code=python,
        ),
        imports,
    )


def _build(restart=False, quiet=False):
    base = Path(".")
    src = base / "src"

    build_root = Path("build")

    if not restart:
        shutil.rmtree(build_root, ignore_errors=True)

    build = build_root / "app"
    build.mkdir(exist_ok=True, parents=True)

    (build / "__init__.py").touch()

    for name in ("blueprints", "middleware", "lib"):
        (build / name).mkdir(exist_ok=True)
        (build / name / "__init__.py").touch()

    (build / "static").mkdir(exist_ok=True)

    templates = build_root / "templates"
    templates.mkdir(exist_ok=True)

    # Make the server
    shutil.copy(find_spec("sanickit.template.server").origin, build / "server.py")

    app_blueprint = """
from sanic import Blueprint
from sanic_ext import render


bp = Blueprint("app_blueprint")

"""

    all_imports = []
    for route in src.glob("**/*"):
        if not quiet:
            print(f"[green]Processing: [yellow]{escape(str(route))}")
        template_name = f"{str(route.with_suffix('').relative_to(src).as_posix())}.html"
        if (path := route.parent.relative_to(src)) not in [Path("middleware")]:
            (templates / path).mkdir(exist_ok=True, parents=True)
        # Create our template
        match route.name:
            case "+page.sanic":
                code, imports = handle_page(src, route, templates, template_name)
                app_blueprint += code
                all_imports.extend(imports)
            case "+server.py":
                code, imports = handle_server(src, route, template_name)
                app_blueprint += code
                all_imports.extend(imports)
            case "+layout.html":
                html = BS(route.read_text(), "html.parser")
                (templates / template_name).write_text("""{% extends "index.html" %}\n\n""" + html.prettify())
            case "+head.html":
                (templates / template_name).write_text(
                    jinja_env.from_string(route.read_text()).render(**asdict(get_config()))
                )
            case _:
                # Handle other files
                match route.suffix:
                    case ".html":
                        shutil.copy(route, templates / route.parent.relative_to(src))
                    case ".py" if route.relative_to(src).parts[0] == "routes":
                        module_path_parts = [
                            part.replace("[", "").replace("]", "")
                            for part in route.relative_to(src / "routes").parent.parts
                        ]
                        module_path = (build / "blueprints").joinpath(*module_path_parts)
                        module_path.mkdir(exist_ok=True, parents=True)
                        shutil.copy(route, module_path / route.name)

    (build / "blueprints" / "app.py").write_text(IMPORTS_TEMPLATE.render(imports=all_imports) + app_blueprint)

    shutil.copy(src / "server_setup.py", build)

    shutil.copytree(base / "static", build / "static", dirs_exist_ok=True)
    shutil.copytree(src / "lib", build / "lib", dirs_exist_ok=True)
    shutil.copytree(src / "blueprints", build / "blueprints", dirs_exist_ok=True)
    shutil.copytree(src / "middleware", build / "middleware", dirs_exist_ok=True)


@cli.command
def build():
    _build()


def watch_files():
    try:
        for _ in watch(Path("./src")):
            _build(restart=True)
    except KeyboardInterrupt:
        pass


@cli.command
def run():
    _build()

    download_tailwind()

    tailwind: str
    if Path("./.sanickit/tailwindcss.exe").exists():
        tailwind = "./.sanickit/tailwindcss.exe"
    else:
        tailwind = "./.sanickit/tailwindcss"
    tailwind_process = subprocess.Popen(
        [
            tailwind,
            "--watch",
            "./src",
            "--output",
            "./build/app/static/tailwind.css",
            "--config",
            "./.sanickit/tailwind.config.js",
        ]
    )
    file_watcher = Process(target=watch_files)
    file_watcher.start()
    try:
        with chdir(Path("build")):
            subprocess.run(
                [Path(sys.executable).parent / "sanic", "app.server:create_app", "--debug", "--dev"], check=True
            )
    except KeyboardInterrupt:
        pass
    file_watcher.close()
    tailwind_process.terminate()


@cli.command
def console():
    from .console import SanicKit

    SanicKit().run()


@cli.command
@click.argument("template")
def template(template):
    if not Path("src/routes").exists():
        print("[red]Templates need to be applied from the project root")
    run_copy(template, ".", quiet=False)


if __name__ == "__main__":
    cli()
