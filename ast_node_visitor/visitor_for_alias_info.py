import ast
from util import *

class VisitorForAliasInfo(ast.NodeVisitor):
    def __init__(self, source_code_path, module_path, codebase_parent_path, codebase_root_path,
                alias_info):

        self.source_code_path = source_code_path
        self.module_path = module_path
        self.codebase_parent_path = codebase_parent_path
        self.codebase_root_path = codebase_root_path

        self.alias_info = alias_info

    def visit_Module(self, node):
        for inner_node in node.body:
            if isinstance(inner_node, ast.ClassDef):
                self._parse_ClassDef(inner_node)
            elif isinstance(inner_node, ast.Import):
                self._parse_Import(inner_node)
            elif isinstance(inner_node, ast.ImportFrom):
                self._parse_ImportFrom(inner_node)
            self._check_non_ClassDef_Import_ImportFrom_alias_str(inner_node)

        self.generic_visit(node)

    def _check_non_ClassDef_Import_ImportFrom_alias_str(self, node):
        """
        Adds alias_str from irrelevant nodes with node as "other" to alias_info \\
        Adds ("del", alias_str) from ast.Delete nodes to alias_info
        """

        if isinstance(node, ast.FunctionDef):
            name = node.name
            self.alias_info.append([(name, name, self.module_path, "other")])
        elif isinstance(node, ast.Assign):
            for target_node in node.targets:
                self._add_alias_str_other_entry(target_node)
        elif isinstance(node, ast.AnnAssign):
            self._add_alias_str_other_entry(node.target)
        elif isinstance(node, ast.Delete):
            for target_node in node.targets:
                self._add_del_alias_str_entry(target_node)

    def _parse_ClassDef(self, node):
        """
        Updates alias_info based on ClassDef node
        """

        class_name = node.name
        self.alias_info.append([(class_name, class_name, self.module_path, node)])

    def _parse_Import(self, node):
        """
        Updates alias_info based on Import node
        """

        for alias in node.names:
            alias_name = alias.name
            alias_asname = alias.asname
            alias_str = alias_asname if alias_asname != None else alias_name

            path_with_alias_str = get_path_of_node_module(node, self.source_code_path, self.codebase_parent_path, self.codebase_root_path, alias_name)
            self.alias_info.append([(alias_str, alias_name, path_with_alias_str, node)])

    def _parse_ImportFrom(self, node):
        """
        Updates alias_info based on ImportFrom node \\
        """

        for alias in node.names:
            alias_name = alias.name
            alias_asname = alias.asname
            alias_str = alias_asname if alias_asname != None else alias_name

            path_with_alias_str = get_path_of_node_module(node, self.source_code_path, self.codebase_parent_path, self.codebase_root_path, alias_name)
            self.alias_info.append([(alias_str, alias_name, path_with_alias_str, node)])

    def _add_alias_str_other_entry(self, node):
        """
        Recursively adds alias_str from irrelevant nodes to alias_info
        """

        if isinstance(node, ast.Name):
            alias_str = node.id
            self.alias_info.append([(alias_str, alias_str, self.module_path, "other")])
        elif isinstance(node, ast.Tuple):
            for elt in node.elts:
                self._add_alias_str_other_entry(elt)
        elif isinstance(node, ast.Attribute):
            alias_str = get_ast_node_str(node)
            self.alias_info.append([(alias_str, alias_str, self.module_path, "other")])

    def _add_del_alias_str_entry(self, node):
        """
        Recursively adds ("del", alias_str) entries to alias_str for alias_str from node
        """

        if isinstance(node, ast.Name):
            alias_str = node.id
            self.alias_info.append([("del", alias_str)])
        elif isinstance(node, ast.Tuple):
            for elt in node.elts:
                remove_alias_str_entry(elt)
        elif isinstance(node, ast.Attribute):
            alias_str = get_ast_node_str(node)
            self.alias_info.append([("del", alias_str)])