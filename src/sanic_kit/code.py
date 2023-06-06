import ast
import sys
from dataclasses import dataclass
from textwrap import dedent

from rich import print
from rich.markup import escape


@dataclass
class APIHandler:
    name: str
    method: str
    code: str


class Extractor(ast.NodeTransformer):
    """Makes our bare files into functions"""

    def __init__(self, name, template_name, parameters, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name
        self.parameters = parameters
        self.template = template_name
        self._extracted_imports = set()

    @property
    def extracted_imports(self):
        return self._extracted_imports

    def visit_Import(self, node):
        self._extracted_imports.add(ast.unparse(node))

    def visit_ImportFrom(self, node):
        match node:
            case ast.ImportFrom(module="lib", names=names, level=1):
                node = ast.ImportFrom(module="app.lib", names=names, level=0)
            case ast.ImportFrom(module=module, names=names, level=1):
                node = ast.ImportFrom(module=f"{self.name.replace('_', '.')}.{module}", names=names, level=1)
            case _:
                ...
        self._extracted_imports.add(ast.unparse(node))

    def visit_FunctionDef(self, node):
        print(f"[red bold]Non-async handler detected: {node.name}")
        sys.exit()


class APIExtract(Extractor):
    """Makes our bare files into functions"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handlers = []

    def visit_AsyncFunctionDef(self, node):
        super().generic_visit(node)
        name = f"{self.name}_{node.name}"

        wrapper = ast.AsyncFunctionDef(
            name=name,
            decorator_list=[],
            args=ast.arguments(
                posonlyargs=[],
                defaults=[],
                args=[ast.arg(arg="request")] + [ast.arg(arg=param) for param in self.parameters],
                kwonlyargs=[ast.arg(arg="TEMPLATE")],
                kw_defaults=[ast.Constant(value=self.template)],
            ),
        )
        wrapper.body = node.body
        # wrapper.body.extend(self.new_return.body)
        wrapper.lineno = 1
        node.body = [wrapper]
        self.handlers.append(APIHandler(name=name, method=node.name.upper(), code=ast.unparse(wrapper)))
        return node


class FunctionAdder(Extractor):
    """Makes our bare files into functions"""

    def __init__(self, name, template_name, parameters, *args, **kwargs):
        super().__init__(name, template_name, parameters)
        self.new_return = ast.parse(
            dedent(
                f"""\
                    if fragment:
                        return html(await render_block_async(request.app.ext.environment, "{template_name}", fragment, **locals()))
                    else:
                        return await render("{template_name}", context=locals())"""
            )
        )
        self.template_name = template_name
        self._extracted_imports.add("from sanic.response import html")
        self._extracted_imports.add("from jinja2_fragments import render_block_async")

    def visit_Return(self, node):
        match node:
            case ast.Return(
                value=ast.Call(
                    func=ast.Name(id="fragment"),
                    args=[ast.Constant(value=fragment)],
                    keywords=[],
                )
            ):
                return ast.parse(
                    f"""return text(await render_block_async(request.app.ext.environment, "{self.template_name}", "{fragment}", **locals()))"""
                )
            case ast.Return(value=ast.Call(func=ast.Name(id="template"), args=[], keywords=[])):
                return ast.parse(f"""return await render("{self.template_name}", context=locals())""")
            case _:
                return node

    def visit_Module(self, node):
        super().generic_visit(node)

        wrapper = ast.AsyncFunctionDef(
            name=self.name,
            decorator_list=[],
            args=ast.arguments(
                posonlyargs=[],
                defaults=[],
                args=[ast.arg(arg="request")] + [ast.arg(arg=param) for param in self.parameters],
                kwonlyargs=[ast.arg(arg="fragment"), ast.arg(arg="TEMPLATE")],
                kw_defaults=[ast.Constant(value=None), ast.Constant(value=self.template)],
            ),
        )
        wrapper.body = node.body
        wrapper.body.extend(self.new_return.body)
        wrapper.lineno = 1
        node.body = [wrapper]
        return node


def extract_imports(code, name, template_name, parameters):
    tree = ast.parse(code)
    transformer = FunctionAdder(name, template_name, parameters)
    new_function_tree = transformer.visit(tree)
    return transformer.extracted_imports, ast.unparse(new_function_tree)


def extract_api(source_file, name, template_name, parameters):
    tree = ast.parse(source_file.read_text())
    transformer = APIExtract(name, template_name, parameters)
    transformer.visit(tree)
    return transformer.extracted_imports, transformer.handlers
