import ast
import enum
import os
import sys

DIRECTORY_SEPARATOR = { "\\", "/" }

FOLDER_WITH_CLASS_HIERARCHY_GRAPHS = "class_hierarchy_graphs"
CLASS_HIERARCHY_GRAPH_DUMP_SUFFIX = "_class_hierarchy_graph"

class PathType(enum.Enum):
    file = 0
    folder = file + 1

def print_class_hierarchy_graph_info(class_hierarchy_graph):
    """
    Prints information about the class hierarchy graph
    """

    class_identifiers = class_hierarchy_graph.keys()
    for class_identifier in class_identifiers:
        print(f"class {class_identifier} inheritance list: {class_hierarchy_graph[class_identifier][0]}")

    print(f"number of classes: {len(class_identifiers)}")

def get_path(argument_index, usage_info):
    """
    Gets path from command line argument \\
    Assumes that the path is provided at argument_index, 0-index \\
    Returns the path if it could be parsed and if the path exists \\
    Otherwise, returns None
    """

    argv = sys.argv

    if len(argv) < argument_index + 1:
        print(f"Error: expected path")
        usage_info()
        return None

    path = argv[argument_index]

    if os.path.exists(path):
        return os.path.realpath(path)
    else:
        print(f"Error: {path} does not refer to an existing file or directory")

    return None

def get_name_directory_or_file(path):
    """
    Given a path to a directory or file \\
    returns the respective directory name or filename

    Examples: \\
    given <path to file>/filename.py, returns filename \\
    given <path to folder>/name_of_folder, returns name_of_folder
    """

    name = ""
    index = len(path) - 1
    if os.path.isfile(path):
        index = path.rfind(".") - 1

    while index >= 0 and path[index] not in DIRECTORY_SEPARATOR:
        name = path[index] + name
        index -= 1

    return name

def get_parent_path(path):
    """
    Given a path to a folder or file, returns the parent path if one exists, None otherwise
    """

    directory_separator_index = -1
    for separator in DIRECTORY_SEPARATOR:
        directory_separator_index = path.rfind(separator)
        if directory_separator_index != -1:
            break

    if directory_separator_index == -1:
        return None

    return path[:directory_separator_index]

def path_contains_os_directory_separator(path):
    """
    Given a path, checks to see if it contains os directory separator
    """

    for separator in DIRECTORY_SEPARATOR:
        if path.find(separator) != -1:
            return False

    return True

def get_dot_notation_path(path):
    """
    Returns the dot notation version of the path
    """

    res = path
    for separator in DIRECTORY_SEPARATOR:
        res = res.replace(separator, ".")
    return res

def is_identifier_rightmost_subsequence_of_identifier(partial_identifier_str, src_identifier_str):
    """
    Returns whether partial_identifier_str is rightmost subsequence of src_identifier_str \\
    Rightmost subsequence is defined as whether partial_identifier_str appears at the rightmost part of src_identifier_str \\
    and if so, whether the element to the left of partial_identifier_str in src_identifier_str is a "." if partial_identifier_str is not each element in src_identifier_str

    Also returns the index of partial_identifier_str in src_identifier_str \\
    if partial_identifier_str is rightmost subsequence of src_identifier_str \\
    or -1 otherwise
    """

    len_partial_identifier_str = len(partial_identifier_str)
    len_src_identifier_str = len(src_identifier_str)

    index_of_partial_identifier_str = src_identifier_str.rfind(partial_identifier_str)
    is_rightmost_subsequence_of = index_of_partial_identifier_str != -1 and partial_identifier_str[len(partial_identifier_str) - 1] == src_identifier_str[len(src_identifier_str) - 1]

    return is_rightmost_subsequence_of and (len_partial_identifier_str == len_src_identifier_str or src_identifier_str[index_of_partial_identifier_str - 1] == "."), index_of_partial_identifier_str

def get_ast_node_str(ast_node, field_name=None):
    """
    Given ast_node, and optional field_name, name of field that ast_node was from, \\
    attempts to retrieve the string form of the node

    Returns the string form of the node or None if it cannot be determined
    """

    if isinstance(ast_node, ast.Attribute):
        return get_ast_node_str(ast_node.value) + "." + ast_node.attr
    elif isinstance(ast_node, ast.Call):
        ast_node_str = get_ast_node_str(ast_node.func)
        ast_node_str += "("

        args = ast_node.args
        for index, arg in enumerate(args):
            ast_node_str += get_ast_node_str(arg)

            if index < len(args) - 1:
                ast_node_str += ", "

        ast_node_str += ")"
        return ast_node_str
    elif isinstance(ast_node, ast.Constant):
        value = ast_node.value
        if isinstance(value, str):
            value = f"\"{value}\""
        else:
            value = str(value)
        return value
    elif isinstance(ast_node, ast.Name):
        return ast_node.id
    elif isinstance(ast_node, ast.Subscript):
        return get_ast_node_str(ast_node.value) + "[" + get_ast_node_str(ast_node.slice, "slice") + "]"
    elif isinstance(ast_node, ast.Slice):
        lower = ast_node.lower
        upper = ast_node.upper
        return "{}:{}".format(get_ast_node_str(lower) if lower else "", get_ast_node_str(upper) if upper else "")
    elif isinstance(ast_node, ast.List) or isinstance(ast_node, ast.Tuple):
        ast_node_str = ""
        if isinstance(ast_node, ast.Tuple):
            ast_node_str = "(" if field_name != "slice" else ""
        else:
            ast_node_str = "["

        elts = ast_node.elts
        for index, elt in enumerate(elts):
            ast_node_str += get_ast_node_str(elt)

            if index < len(elts) - 1:
                ast_node_str += ", "

        if isinstance(ast_node, ast.Tuple):
            ast_node_str += ")" if field_name != "slice" else ""
        else:
            ast_node_str += "]"

        return ast_node_str
    return None

def get_path_of_node_module(node, source_code_path, codebase_parent_path, codebase_root_path, alias_name):
    """
    Given an Import or ImportFrom node, source code path, codebase parent path, codebase root path, and alias_name \\
    alias_name only used if node is ast.Import \\
    returns the path of node module in codebase or None if none
    """

    # edge case of the os drive name in module not handled

    if isinstance(node, ast.ImportFrom):
        module = node.module
        num_dots = node.level
        if node.level > 0:
            path = source_code_path
            for i in range(num_dots):
                path = get_parent_path(path)
                if path == None:
                    return None
            resolved_path = get_dot_notation_path(path)

            if module:
                resolved_path += "." + module

            # if resolved path in codebase
            if resolved_path.find(get_dot_notation_path(codebase_root_path)) == 0:
                resolved_path = resolved_path[len(codebase_parent_path) + 1:]
                return resolved_path
            else:
                return None
        else: # non-relative ImportFrom
            return get_name_directory_or_file(codebase_root_path) + "." + module
    elif isinstance(node, ast.Import):
        return get_name_directory_or_file(codebase_root_path) + "." + alias_name

def remove_alias_str_entry(node, dct):
    """
    Recursively removes alias_str entries from node from dct
    """

    if isinstance(node, ast.Name):
        alias_str = node.id
        if alias_str in dct:
            del dct[alias_str]
    elif isinstance(node, ast.Tuple):
        for elt in node.elts:
            remove_alias_str_entry(elt, dct)
    elif isinstance(node, ast.Attribute):
        alias_str = get_ast_node_str(node)
        if alias_str in dct:
            del dct[alias_str]