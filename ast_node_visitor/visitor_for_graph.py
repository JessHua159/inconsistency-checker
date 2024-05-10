import ast
from util import *

DEBUG = False

NO_OUTPUT_INVALID_BASE = True
NO_OUTPUT_SOME_UNRESOLVABLE_BASE_STR = True
NO_OUTPUT_CIRCULAR_IMPORT = True
SOME_UNRESOLVABLE_BASE_STR_PY_FILE = {
}
SOME_UNRESOLVABLE_BASE_STR_PYI_FILE = {
}

ATTRIBUTE_NAME_NOT_STATICALLY_TYPED_CLASS = {
    "__annotations__", "__base__", "__bases__",
    "__basicsize__", "__call__", "__class__",
    "__delattr__", "__dict__", "__dictoffset__",
    "__dir__", "__doc__", "__eq__",
    "__flags__", "__format__", "__getattribute__",
    "__getstate__", "__hash__", "__init__",
    "__init_subclass__", "__instancecheck__", "__itemsize__",
    "__module__", "__mro__", "mro",
    "__name__", "__ne__", "__new__",
    "__or__", "__prepare__", "__qualname__",
    "__reduce__", "__reduce_ex__", "__repr__",
    "__ror__", "__setattr__", "__sizeof__",
    "__str__", "__subclasscheck__", "__subclasses__",
    "__subclasshook__", "__text_signature__"
}

class VisitorForGraph(ast.NodeVisitor):
    def __init__(self, source_code_path, module_path, codebase_parent_path, codebase_root_path,
                class_hierarchy_graph, alias_name_path_resolved_path,
                path_last_alias_str_info, path_type,
                log_ast_parse=False):

        self.source_code_path = source_code_path
        self.module_path = module_path
        self.codebase_parent_path = codebase_parent_path
        self.codebase_root_path = codebase_root_path

        self.class_hierarchy_graph = class_hierarchy_graph
        self.alias_name_path_resolved_path = alias_name_path_resolved_path

        self.path_last_alias_str_info = path_last_alias_str_info
        self.path_type = path_type

        # key: alias, value: path of alias in dot notation, node that the path refers to
        self.alias_str_path_node = dict()

        self.log_ast_parse = log_ast_parse

        self.current_class_name = ""
        self.edge_case = False

    def visit_Module(self, node):
        for inner_node in node.body:
            if isinstance(inner_node, ast.Import):
                self._parse_Import(inner_node)
            elif isinstance(inner_node, ast.ImportFrom):
                self._parse_ImportFrom(inner_node)
            elif isinstance(inner_node, ast.ClassDef):
                self._parse_ClassDef(inner_node)
            elif isinstance(inner_node, ast.Delete):
                for target_node in inner_node.targets:
                    remove_alias_str_entry(target_node, self.alias_str_path_node)
        self.generic_visit(node)

    def _parse_Import(self, node):
        """
        Updates alias_path based on the contents of the Import node
        """

        for alias in node.names:
            alias_name = alias.name
            alias_asname = alias.asname
            alias_str = alias_asname if alias_asname != None else alias_name

            alias_path_and_node = self._get_alias_path_and_node(self.module_path, alias_str, alias_name, node, True)
            if alias_path_and_node != None:
                self.alias_str_path_node[alias_str] = alias_path_and_node # overwrites if alias_str in self.alias_str_path_node
                self._check_alias_str_underscore_init_underscore(alias_str, alias_path_and_node)

    def _parse_ImportFrom(self, node):
        """
        Updates alias_str_path_node based on the contents of the ImportFrom node
        """

        for alias in node.names:
            alias_strs_names = []

            alias_name = alias.name
            alias_asname = alias.asname
            alias_str = alias_asname if alias_asname != None else alias_name

            if alias_str == "*":
                path = get_path_of_node_module(node, self.source_code_path, self.codebase_parent_path, self.codebase_root_path, alias_name)
                if path not in self.path_last_alias_str_info:   # path of module of from module import * is not in code base
                    continue
                path = path if self.path_type[path] == PathType.file else path + ".__init__"
                if path not in self.path_last_alias_str_info:   # path of module of from module import * is not in code base
                    continue
                last_defined_alias_strs = self.path_last_alias_str_info[path].keys()
                for alias_str in last_defined_alias_strs:
                    alias_strs_names.append((alias_str, alias_str))
            else:
                alias_strs_names.append((alias_str, alias_name))

            for alias_str, alias_name in alias_strs_names:
                alias_path_and_node = self._get_alias_path_and_node(self.module_path, alias_str, alias_name, node, True)
                if alias_path_and_node != None:
                    self.alias_str_path_node[alias_str] = alias_path_and_node # overwrites if duplicate alias_str found
                    self._check_alias_str_underscore_init_underscore(alias_str, alias_path_and_node)

    def _add_entries_to_class_name_alias_paths(self, class_name_alias_paths, class_names, module_path):
        """
        Adds entries to class_name_alias_paths dictionary where the path added is module_path + class_name
        """

        for class_name in class_names:
            alias_path = module_path + "." + class_name
            if class_name in class_name_alias_paths:
                class_name_alias_paths[class_name].append(alias_path)
            else:
                class_name_alias_paths[class_name] = [alias_path]

    def _parse_ClassDef(self, node):
        """
        Statically evaluates the bases in ClassDef to <relative path to class in dot notation>.<inherited class name> \\
        and adds the respective resolved names to the class hierarchy graph
        """

        class_name = node.name
        class_identifier = self.module_path + "." + class_name

        if class_identifier not in self.class_hierarchy_graph:    # not duplicate class
            self.current_class_identifier = class_identifier
            self.class_hierarchy_graph[class_identifier] = ([], self.source_code_path)

            bases = node.bases
            for base in bases:
                if type(base) not in { ast.Attribute, ast.Call, ast.Constant, ast.List, ast.Name, ast.Subscript, ast.Slice, ast.Tuple }:
                    print(f"Unhandled edge case of base {type(base)}")
                    self.edge_case = True
                    continue

                if isinstance(base, ast.Constant) or isinstance(base, ast.List) or \
                    isinstance(base, ast.Slice) or isinstance(base, ast.Tuple):
                    if self.log_ast_parse:
                        base_str = self._get_ast_node_str(base)
                        self._output_invalid_base(class_identifier, base, base_str)
                elif isinstance(base, ast.Call):
                    module_func_name = self._get_ast_node_str(base.func)
                    module, func_name = self._get_module_name_from_path(module_func_name)
                    args = base.args

                    if self._is_or_args_of_same_module(module, func_name, args) or \
                        self._is_ror_args_of_same_module(module, func_name, args):
                        module, inherited_class_name = self._get_module_name_from_path(module)
                        # self._insert_to_graph(class_name, original_class_name, inherited_class_name)
                        inherited_class_identifier = self._get_identifier(module, inherited_class_name)
                        if inherited_class_identifier == None:
                            if self.log_ast_parse:
                                self._output_unresolvable_inherited_class_identifier(class_identifier, module, inherited_class_name)
                            continue
                        self._insert_to_graph(class_identifier, inherited_class_identifier)
                    else:
                        if self.log_ast_parse:
                            args_str = self._get_args_str(args)
                            base_str = module_func_name + args_str
                            self._output_invalid_base(class_identifier, base, base_str)
                else:   # not ast.Constant, ast.Call, ast.Slice, or ast.Tuple
                    if isinstance(base, ast.Subscript):
                        subscript_base = base
                        base = base.value

                        # check if it is not of form <class name>[<generic type>]
                        if not (isinstance(base, ast.Name) or isinstance(base, ast.Attribute)):
                            if self.log_ast_parse:
                                subscript_base_str = self._get_ast_node_str(subscript_base)
                                self._output_invalid_base(class_identifier, base, subscript_base_str)
                                continue

                    module_inherited_class_name = self._get_ast_node_str(base)
                    module, inherited_class_name = self._get_module_name_from_path(module_inherited_class_name)

                    if DEBUG:
                        print(f"\nfrom base from {self.source_code_path}: module: {module}, inherited_class_name: {inherited_class_name}")
                        print(f"self.alias_str_path_node: {self.alias_str_path_node}")
                        pass

                    if isinstance(base, ast.Attribute):
                        if inherited_class_name in ATTRIBUTE_NAME_NOT_STATICALLY_TYPED_CLASS:
                            if self.log_ast_parse:
                                self._output_invalid_base(class_identifier, base, module_inherited_class_name)
                        else:
                            # self._insert_to_graph(class_name, original_class_name, inherited_class_name)
                            inherited_class_identifier = self._get_identifier(module, inherited_class_name)
                            if inherited_class_identifier == None:
                                if self.log_ast_parse:
                                    self._output_unresolvable_inherited_class_identifier(class_identifier, module, inherited_class_name)
                                continue
                            self._insert_to_graph(class_identifier, inherited_class_identifier)
                    else:
                        # self._insert_to_graph(class_name, original_class_name, inherited_class_name)
                        inherited_class_identifier = self._get_identifier(module, inherited_class_name)
                        if inherited_class_identifier == None:
                            if self.log_ast_parse:
                                self._output_unresolvable_inherited_class_identifier(class_identifier, module, inherited_class_name)
                            continue
                        self._insert_to_graph(class_identifier, inherited_class_identifier)

            # possible can use the proposed modified _get_alias_path_and_node
            # self.alias_str_path_node[class_name] = self.module_path + "." + class_name  # placed here to avoid overwriting an alias string before use of it for identifier retrieval
            self.alias_str_path_node[class_name] = self._get_alias_path_and_node(self.module_path, class_name, class_name, node, True)

    def _get_alias_path_and_node(self, path_with_alias_str, alias_str, alias_name, node, not_last_defined=False):
        """
        Given path_with_alias_str and alias_str, attempts to resolve the path of alias_str \\
        Returns the resolved alias path and node or None if the alias path could not be resolved
        """

        visited_paths = set()
        return self._get_alias_path_and_node_helper(visited_paths, path_with_alias_str, alias_str, alias_name, node, not_last_defined)

    def _get_alias_path_and_node_helper(self, visited_paths, path_with_alias_str, alias_str, alias_name, node, not_last_defined=False):
        visited_paths.add(path_with_alias_str)

        if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
            path = None
            if not_last_defined:
                path = get_path_of_node_module(node, self.source_code_path, self.codebase_parent_path, self.codebase_root_path, alias_name)
            else:
                last_alias_str_info = self.path_last_alias_str_info[path_with_alias_str] if path_with_alias_str in self.path_last_alias_str_info else None
                if last_alias_str_info == None:
                    return None
                alias_str_info_entry = last_alias_str_info[alias_str] if alias_str in last_alias_str_info else None
                if alias_str_info_entry == None:
                    return None
                path = alias_str_info_entry[1]

            if path == None:
                return None

            if isinstance(node, ast.Import):
                return path, "module"   # path may refer to a file or folder

            # if ImportFrom, recurse on the path
            for p in [path + ".__init__", path]:
                if (alias_name, p) in self.alias_name_path_resolved_path:
                    ret = self.alias_name_path_resolved_path[(alias_name, p)]
                    if ret != None:
                        return ret
                else:
                    if p in self.path_last_alias_str_info:
                        last_alias_str_info = self.path_last_alias_str_info[p]
                        alias_str_other = alias_name
                        if alias_str_other in last_alias_str_info:
                            alias_str_info_entry = last_alias_str_info[alias_str_other]
                            alias_name_other = alias_str_info_entry[0]
                            node_other = alias_str_info_entry[2]

                            # circular import check
                            if p in visited_paths:
                                if self.log_ast_parse and not NO_OUTPUT_CIRCULAR_IMPORT:
                                    print(f"\npossible circular import with import that began at {p} or traversed to {p}")
                                self.alias_name_path_resolved_path[(alias_name, p)] = None
                                continue

                            ret = self._get_alias_path_and_node_helper(visited_paths, p, alias_str_other, alias_name_other, node_other)
                            self.alias_name_path_resolved_path[(alias_name, p)] = ret
                            if ret != None:
                                return ret

        # if ClassDef, alias_str defined in file; if "other", alias_str likely defined in file
        elif isinstance(node, ast.ClassDef) or node == "other":
            return path_with_alias_str, node

        # if module, then alias_str refers to the module
        elif node == "module":
            return self.path_last_alias_str_info[path_with_alias_str][alias_str][1], node

        return None

    def _check_alias_str_underscore_init_underscore(self, alias_str, entry):
        """
        Checks if alias_str is of the form <name>.__init__
        If so, add entry <name>: alias_path to alias_str_path_node
        """

        condition, index = is_identifier_rightmost_subsequence_of_identifier("__init__", alias_str)
        # import x.__init__ case
        if len("__init__") < len(alias_str) and condition:
            self.alias_str_path_node[alias_str[:index - 1]] = entry

    def _add_entry_to_alias_path_dct(self, alias_str, alias_path):
        if alias_str not in self.alias_str_path_node:
            self.alias_str_path_node[alias_str] = [alias_path]
        else:
            self.alias_str_path_node[alias_str].append(alias_path)

    def _is_or_args_of_same_module(self, call_value, call_attr, args):
        """
        Given that call_value, call_attr, and args from ast.Call, returns whether the call is of form <module>.__or__(<same module>)
        """

        return call_attr == "__or__" and len(args) == 1 and call_value == self._get_ast_node_str(args[0])

    def _is_ror_args_of_same_module(self, call_value, call_attr, args):
        """
        Given that call_value, call_attr, and args from ast.Call, returns whether the call is of form <module>.__ror__(<same module>)
        """

        return call_attr == "__ror__" and len(args) == 1 and call_value == self._get_ast_node_str(args[0])

    def _output_invalid_base(self, class_name, base, base_str):
        ##
        if NO_OUTPUT_INVALID_BASE:
            return
        ##

        print()
        print(f"Base in ast bases for class {class_name} in {self.source_code_path} is {type(base)} of {base_str}")
        print(f"Cannot statically determine inconsistency of class {class_name} with that base")

    def _output_from_x_import_double_underscore_init_double_underscore_case(self, num_dots, module, alias_asname):
        dots = ""
        for i in range(num_dots):
            dots += "."

        print()
        print("{}: from {}{} import __init__{}".format(self.source_code_path, dots, module, " as {}".format(alias_asname) if alias_asname != None else ""))
        print("__init__ may be a method-wrapper object.")

    def _output_from_dot_import_wildcard_case(self):
        print()
        print(f"{self.source_code_path}: from (>= 1 .) import * found")

    def _output_unresolvable_inherited_class_identifier(self, class_name, module, inherited_class_name):
        base_str = "{}{}".format(module + "." if module != "" else "", inherited_class_name)

        ###
        if NO_OUTPUT_SOME_UNRESOLVABLE_BASE_STR:
            len_source_code_path = len(self.source_code_path)
            if self.source_code_path[len_source_code_path - 3:] == ".py" and \
                base_str in SOME_UNRESOLVABLE_BASE_STR_PY_FILE:
                return
            elif self.source_code_path[len_source_code_path - 4:] == ".pyi" and \
                base_str in SOME_UNRESOLVABLE_BASE_STR_PYI_FILE:
                return
        ###

        print()
        print(f"Base in ast bases for class {class_name} in {self.source_code_path} is {base_str}")
        print(f"{base_str} is not a class, a variable, a class defined in a non-module closure, a class that is not defined statically, or a class not from this code base")

    def _get_identifier(self, module, class_name):
        """
        Given a module and class_name, attempts to resolve the full class name in the following format: \\
        <relative module path to class in dot notation>.<non-alias class_name> \\
        Returns the resolved name if can be resolved or None if it cannot be resolved
        """

        is_alias_str_class_name = module == ""

        ret = self._resolve_base_path(class_name, True) if is_alias_str_class_name else self._resolve_base_path(module, False)

        if ret == None:
            return None

        path, node = ret

        # checks that the path is not None and the node from path matches the alias_str semantic
        if path == None or \
            (is_alias_str_class_name and not isinstance(node, ast.ClassDef)) or \
            (not is_alias_str_class_name and node != "module"):
            return None

        # confirms class_name is in the possible paths from path and returns the identifier path if class_name found
        node_name = node.name if is_alias_str_class_name else class_name
        for p in [path + ".__init__", path]:
            # if p refers to the module path, alias_str defined in module path
            if p == self.module_path:
                return p + "." + node_name

            if p == None or p not in self.path_last_alias_str_info:
                continue
            last_alias_str_info = self.path_last_alias_str_info[p]
            if node_name not in last_alias_str_info:
                continue
            alias_str_info_entry = last_alias_str_info[node_name]

            if is_alias_str_class_name:
                if not isinstance(alias_str_info_entry[2], ast.ClassDef):
                    continue
                return p + "." + node_name
            else:
                alias_name = alias_str_info_entry[0]
                node = alias_str_info_entry[2]
                ret = self._get_alias_path_and_node(p, class_name, alias_name, node)
                if ret == None:
                    continue
                pth, node = ret
                if pth == None or pth not in self.path_last_alias_str_info or not isinstance(node, ast.ClassDef):
                    continue
                return pth + "." + node.name
        return None

    def _resolve_base_path(self, alias_str, is_alias_str_class_name):
        """
        Resolves the path of alias_str with the assumption that alias_str is class_name or module path from base \\
        Uses information from alias_paths to attempt to resolve the path of alias_str \\
        Returns the resolved path and node that path refers to if a path is resolvable from alias_str or None if not possible
        """

        if is_alias_str_class_name:
            if alias_str in self.alias_str_path_node:
                return self.alias_str_path_node[alias_str]
        else:
            alias_str_with_init = alias_str + ".__init__"
            if alias_str_with_init in self.alias_str_path_node:
                return self.alias_str_path_node[alias_str_with_init]
            if alias_str in self.alias_str_path_node:
                return self.alias_str_path_node[alias_str]

            alias_str_dot_index = alias_str.rfind(".")
            while alias_str_dot_index != -1:
                left_subsequence = alias_str[:alias_str_dot_index]
                left_subsequence_with_init = left_subsequence + ".__init__"

                ret = self.alias_str_path_node[left_subsequence_with_init] if left_subsequence_with_init in self.alias_str_path_node else None
                if ret == None:
                    ret = self.alias_str_path_node[left_subsequence] if left_subsequence in self.alias_str_path_node else None
                if ret == None: # left_subsequence does not correspond to an alias_str
                    return None

                path, node_from_path = ret
                if path != None and path in self.path_last_alias_str_info:
                    right_subsequence_alias_strs = alias_str[alias_str_dot_index + 1:].split(".")
                    invalid_path = False

                    for a_str in right_subsequence_alias_strs:
                        # looks for a_str in path + ".__init__", then path if a_str not in path + ".__init__"
                        # gets the next path from the path in which a_str is defined in
                        path_in_code_base = False
                        for p in [path + ".__init__", path]:
                            if p not in self.path_last_alias_str_info:
                                continue

                            last_alias_str_info = self.path_last_alias_str_info[p]
                            if a_str not in last_alias_str_info:
                                continue

                            alias_str_info_entry = last_alias_str_info[a_str]
                            alias_name = alias_str_info_entry[0]
                            node = alias_str_info_entry[2]

                            ret = self._get_alias_path_and_node(p, a_str, alias_name, node)

                            if ret == None:
                                continue

                            pth, node_from_path = ret
                            if pth == None or pth not in self.path_last_alias_str_info:
                                continue

                            path_in_code_base = True
                            path = pth
                            break

                        if not path_in_code_base:
                            invalid_path = True
                            break

                    if not invalid_path:
                        return path, node_from_path

                alias_str_dot_index = alias_str.rfind(".", 0, alias_str_dot_index)

        return None

    def _insert_to_graph(self, class_identifier, inherited_class_identifier):
        """
        Adds element to adjacency list in class hierarchy graph
        """

        # cases of inherited "object" classes from custom modules are not handled
        if not is_identifier_rightmost_subsequence_of_identifier("object", inherited_class_identifier)[0]:
            self.class_hierarchy_graph[class_identifier][0].append(inherited_class_identifier)

    def _get_ast_node_str(self, ast_node, field_name=None):
        """
        Given ast_node, and optional field_name, name of field that ast_node was from, \\
        attempts to retrieves the string form of the node
        """

        ast_node_str = get_ast_node_str(ast_node, field_name)

        if ast_node_str == None:
            print(f"unhandled case of ast_node {type(ast_node)} for class {self.current_class_name} in {self.source_code_path}")
            self.edge_case = True

        return ast_node_str

    def _get_args_str(self, args):
        """
        Given args, list of ast nodes, retrieves the arguments in a string form
        """

        args_str = "("

        for index, arg in enumerate(args):
            args_str += self._get_ast_node_str(arg)

            if index < len(args) - 1:
                args_str += ", "

        args_str += ")"
        return args_str

    def _get_module_name_from_path(self, module_path):
        """
        Given module_path, gets module and name
        If no module, then module is returned as ""
        """

        index_of_rightmost_dot = None
        for i in range(len(module_path) - 1, -1, -1):
            if module_path[i] == ".":
                index_of_rightmost_dot = i
                break

        module = None
        name = None
        if index_of_rightmost_dot == None:
            module = ""
            name = module_path
        else:
            module = module_path[0:index_of_rightmost_dot]
            name = module_path[index_of_rightmost_dot + 1:]

        return module, name