from importlib import import_module
from pathlib import Path
from typing import Optional, Sequence, Tuple

from jinja2.ext import Extension
from jinja2.lexer import Token
# Modules imported here should NOT have a Sanic.get_app() call in the global
# scope. Doing so will cause a circular import. Therefore, we progromatically
# import those modules inside of the create_app() factory.
# from app.common.auth.startup import setup_auth
# from app.common.csrf import setup_csrf
# from app.common.log import setup_logging
# from app.common.pagination import setup_pagination
from sanic import Sanic


class RelativeInclude(Extension):
    def preprocess(self, source, name, filename=None):
        self.name = name
        self.filename = filename
        return source

    def filter_stream(self, stream):
        in_include_tag = False
        for token in stream:
            match token:
                case Token(type="name", value="include"):
                    in_include_tag = True
                    yield token
                case Token(type="block_end") if in_include_tag:
                    in_include_tag = False
                    yield token
                case Token(type="string") if in_include_tag and token.value.startswith("."):
                    new_token = Token(
                        lineno=token.lineno,
                        type=token.type,
                        value=str(Path(self.filename).relative_to("templates").parent / token.value),
                    )
                    yield new_token
                case _:
                    yield token


# from .blueprints.app import bp as app_bp

DEFAULT: Tuple[str, ...] = (
    "app.blueprints.app",
    "app.middleware.htmx",
    # "app.middleware.request_context",
    # "app.middleware.redirect",
)


def load_modules(path):
    for module in (Path(__file__).parent / path).glob("*.py"):
        if module.stem == "__init__":
            continue
        yield import_module(f"app.{path}.{module.stem}")


def setup_blueprints(app: Sanic):
    """
    Load the blueprints
    """
    for module in load_modules("blueprints"):
        if bp := getattr(module, "bp", None):
            app.blueprint(bp)


def setup_middleware(app: Sanic):
    """
    Load the middleware
    """
    for module in load_modules("middleware"):
        pass  # Don't need to do anything


def create_app(namespace, module_names: Optional[Sequence[str]] = None) -> Sanic:
    """
    Application factory: responsible for gluing all of the pieces of the
    application together. In most use cases, running the application will be
    done will a None value for module_names. Therefore, we provide a default
    list. This provides flexibility when unit testing the application. The main
    purpose for this pattern is to avoide import issues. This should be the
    first thing that is called.
    """
    if module_names is None:
        module_names = DEFAULT

    app = Sanic("myapp")
    app.static("/static/", Path(__file__).parent / "static")
    app.config.CSRF_REF_PADDING = 12
    app.config.CSRF_REF_LENGTH = 18
    app.ext.templating.environment.add_extension(RelativeInclude)

    # setup_logging(app)
    # setup_pagination(app)
    # setup_auth(app)
    setup_middleware(app)
    setup_blueprints(app)
    # setup_csrf(app)

    return app
