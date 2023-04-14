import ast
from rich import print


class FunctionAdder(ast.NodeTransformer):
    """Makes our bare files into functions"""

    def __init__(self, name, template, parameters, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.function_name = name
        self.parameters = parameters
        self.new_return = ast.parse(f"""return await render("{template}", context=locals())""")
        self.extracted_imports = []

    def visit_Import(self, node):
        self.extracted_imports.append(ast.unparse(node))

    def visit_ImportFrom(self, node):
        self.extracted_imports.append(ast.unparse(node))

    def visit_Module(self, node):
        super().generic_visit(node)

        wrapper = ast.AsyncFunctionDef(
            name=self.function_name,
            decorator_list=[],
            args=ast.arguments(
                posonlyargs=[],
                kwonlyargs=[],
                defaults=[],
                kw_defaults=[],
                args=[ast.arg(arg="request")] + [ast.arg(arg=param) for param in self.parameters],
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
