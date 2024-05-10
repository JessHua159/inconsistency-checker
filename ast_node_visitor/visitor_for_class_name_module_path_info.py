import ast
from util import *

class VisitorForClassNameModulePathInfo(ast.NodeVisitor):
    def __init__(self, source_code_path, module_path, codebase_parent_path, codebase_root_path,
                class_name_module_paths, module_paths_class_names):

        self.source_code_path = source_code_path
        self.module_path = module_path
        self.codebase_parent_path = codebase_parent_path
        self.codebase_root_path = codebase_root_path

        self.class_name_module_paths = class_name_module_paths
        self.module_paths_class_names = module_paths_class_names

    def visit_Module(self, node):
        for inner_node in node.body:
            if isinstance(inner_node, ast.ClassDef):
                self._parse_ClassDef(inner_node)
        self.generic_visit(node)

    def _parse_ClassDef(self, node):
        """
        Updates class_name_module_paths and module_paths_class_names based on ClassDef node
        """

        class_name = node.name

        if class_name in self.class_name_module_paths:
            module_paths = self.class_name_module_paths[class_name]
            if self.module_path not in module_paths:    # if self.module_path in module_paths, then a duplicate class name in same module
                module_paths.append(self.module_path)
        else:
            self.class_name_module_paths[class_name] = [self.module_path]

        if self.module_path not in self.module_paths_class_names:
            self.module_paths_class_names[self.module_path] = set()
        self.module_paths_class_names[self.module_path].add(class_name)