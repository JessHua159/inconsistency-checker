import ast
from util import *

class VisitorForNonRelImportSubsequences(ast.NodeVisitor):
    def __init__(self, module_path,
                nonrel_import_subsequences):

        self.module_path = module_path
        self.nonrel_import_subsequences = nonrel_import_subsequences

    def visit_Module(self, node):
        for inner_node in node.body:
            if isinstance(inner_node, ast.Import):
                self._parse_Import(inner_node)
            elif isinstance(inner_node, ast.ImportFrom):
                self._parse_ImportFrom(inner_node)
        self.generic_visit(node)

    def _parse_Import(self, node):
        """
        Updates nonrel_import_subsequences based on Import node
        """

        for alias in node.names:
            self.nonrel_import_subsequences.append(alias.name)

    def _parse_ImportFrom(self, node):
        """
        Updates nonrel_import_subsequences based on ImportFrom node \\
        If the node refers to a non-relative import, nonrel_import_subsequences is updated
        """

        if node.level == 0: # if non-relative ImportFrom
            self.nonrel_import_subsequences.append(node.module)