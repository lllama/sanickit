import ast
from rich import print
from dataclasses import dataclass
import sys


@dataclass
class APIHandler:
    name: str
    method: str
    code: str


class APIExtract(ast.NodeTransformer):
    """Makes our bare files into functions"""

    def __init__(self, name, template_name, parameters, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name
        self.parameters = parameters
        self.template = template_name
        self.extracted_imports = set()
        self.handlers = []

    def visit_Import(self, node):
        self.extracted_imports.add(ast.unparse(node))

    def visit_ImportFrom(self, node):
        self.extracted_imports.add(ast.unparse(node))

    def visit_FunctionDef(self, node):
        print(f"[red bold]Non-async handler detected: {node.name}")
        sys.exit()

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


class FunctionAdder(ast.NodeTransformer):
    """Makes our bare files into functions"""

    def __init__(self, name, template, parameters, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.function_name = name
        self.parameters = parameters
        self.template = template
        self.new_return = ast.parse(f"""return await render("{template}", context=locals())""")
        self.extracted_imports = set()

    def visit_Import(self, node):
        self.extracted_imports.add(ast.unparse(node))

    def visit_ImportFrom(self, node):
        self.extracted_imports.add(ast.unparse(node))

    def visit_Module(self, node):
        super().generic_visit(node)

        wrapper = ast.AsyncFunctionDef(
            name=self.function_name,
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
    new_function_tree = transformer.visit(tree)
    return transformer.extracted_imports, transformer.handlers
