import ast
import enum
import os
import pickle

from ast_node_visitor.visitor_for_alias_info import VisitorForAliasInfo
from ast_node_visitor.visitor_for_graph import VisitorForGraph

from util import *

SOURCE_CODE_PATH_ARGUMENT_INDEX = 1 # 0-indexed

# two types of output: console log (LOG_<identifier>) and dump to file (DUMP_<identifier>)
DUMP_AST = False
AST_DUMP_FOLDER_NAME = "ast_dump"

LOG_AST_PARSE_DATA = False
LOG_FILE_PARSE = False
LOG_GRAPH_INFO = True

PYTHON_SCRIPT_EXTENSION = ".py"

class GetOp(enum.Enum):
    get_alias_info_op = 0
    get_graph_op = get_alias_info_op + 1

def is_file_Python_script(filepath):
    """
    Given a path to a file \\
    returns whether the file is a Python script
    """

    if not os.path.isfile(filepath):
        return False

    index_begin_dot_py = len(filepath) - len(PYTHON_SCRIPT_EXTENSION)
    if filepath[index_begin_dot_py:] == PYTHON_SCRIPT_EXTENSION:
        return True

    return False

def create_ast_dump_folder(source_code_path):
    """
    Assumes the source_code_path points to a Python script or directory \\
    Creates ast dump folder for the respective ast dump and returns the path of that folder
    """

    if not os.path.exists(AST_DUMP_FOLDER_NAME):
        os.mkdir(AST_DUMP_FOLDER_NAME)

    name_of_folder = get_name_directory_or_file(source_code_path)

    ast_dump_folder_path = os.path.join(AST_DUMP_FOLDER_NAME, name_of_folder)
    if not os.path.exists(ast_dump_folder_path):
        os.mkdir(ast_dump_folder_path)

    return ast_dump_folder_path

def get_data_from_ast_parse(paths_dct,
                            data_dct,
                            dependencies_dct,
                            get_op,
                            ast_dump_info = None):
    """
    Fills in respective data in data_dct from ast parse of Python files within paths_dct["source_code_path"] \\
    with corresponding paths from paths_dct and dependencies from dependencies_dct
    """

    ast_dump_folder_path = None
    ast_dump_filename_prefix = None
    at_root_directory = None

    if ast_dump_info:
        ast_dump_folder_path, ast_dump_filename_prefix, at_root_directory = ast_dump_info

    source_code_path = paths_dct["source_code_path"]
    relative_import_path = paths_dct["relative_import_path"]

    if is_file_Python_script(source_code_path):
        if LOG_FILE_PARSE:
            print(f"{get_op}: Python file: {source_code_path}")

        python_script_contents = ""
        with open(source_code_path) as file:
            python_script_contents = None
            try:
                python_script_contents = file.read()
            except:
                if LOG_FILE_PARSE:
                    print(f"{get_op}: Could not parse Python file {source_code_path}")

            if python_script_contents:
                filename = get_name_directory_or_file(source_code_path)
                ast_parse = None

                try:
                    ast_parse = ast.parse(python_script_contents)
                except Exception as e:
                    print(f"{get_op}: Error with ast parse of {source_code_path}: {e}")

                try:
                    if ast_parse != None:
                        module_path = relative_import_path + filename

                        if get_op == GetOp.get_alias_info_op:
                            data_dct["module_paths"].append(module_path)
                            data_dct["path_type"][module_path] = PathType.file

                        parse_ast(source_code_path, module_path, paths_dct,
                                    data_dct,
                                    dependencies_dct,
                                    get_op,
                                    ast_parse)
                except Exception as e:
                    print(f"{get_op}: Error with parse ast of {source_code_path}: {e}")

                if ast_dump_info:
                    ast_dump_path = os.path.join(ast_dump_folder_path, ast_dump_filename_prefix + filename + "_ast_parse.txt")
                    try:
                        write_ast_parse_to_dump_file(ast_parse, ast_dump_path)
                    except:
                        if LOG_FILE_PARSE:
                            print(f"{get_op}: Could not write ast dump of Python file {source_code_path}")
        file.close()

    elif os.path.isdir(source_code_path):
        if LOG_FILE_PARSE:
            print(f"{get_op}: Folder: {source_code_path}")

        directory_files = os.listdir(source_code_path)

        ast_dump_filename_prefix_update = ast_dump_filename_prefix
        if ast_dump_info and not at_root_directory:
            ast_dump_filename_prefix_update += get_name_directory_or_file(source_code_path) + "%"
        updated_ast_dump_info = None
        if ast_dump_info:
            updated_ast_dump_info = (ast_dump_folder_path, ast_dump_filename_prefix_update, False)

        relative_import_path_update_no_dot_at_end = None
        if get_op == GetOp.get_alias_info_op:
            relative_import_path_update_no_dot_at_end = relative_import_path + get_name_directory_or_file(source_code_path)
            data_dct["module_paths"].append(relative_import_path_update_no_dot_at_end)
            data_dct["path_type"][relative_import_path_update_no_dot_at_end] = PathType.folder

            data_dct["path_alias_info"][relative_import_path_update_no_dot_at_end] = []

        for file in directory_files:
            source_code_path_update = os.path.join(source_code_path, file)
            paths_dct["source_code_path"] = source_code_path_update

            if relative_import_path_update_no_dot_at_end != None:
                paths_dct["relative_import_path"] = relative_import_path_update_no_dot_at_end + "."
            else:
                paths_dct["relative_import_path"] = relative_import_path + get_name_directory_or_file(source_code_path) + "."

            if get_op == GetOp.get_alias_info_op:
                filename = get_name_directory_or_file(source_code_path_update)
                data_dct["path_alias_info"][relative_import_path_update_no_dot_at_end].append([(filename, filename, relative_import_path_update_no_dot_at_end + "." + filename, "module")])

            get_data_from_ast_parse(paths_dct,
                                    data_dct,
                                    dependencies_dct,
                                    get_op,
                                    updated_ast_dump_info)

def parse_ast(source_code_path, module_path, paths_dct,
            data_dct,
            dependencies_dct,
            get_op,
            ast_parse):
    """
    Fills in respective data in data_dct from ast parse with corresponding paths from paths_dct and dependencies from dependencies_dct
    """

    visitor = None

    if get_op == GetOp.get_alias_info_op:
        codebase_parent_path = paths_dct["codebase_parent_path"]
        codebase_root_path = paths_dct["codebase_root_path"]

        path_alias_info = data_dct["path_alias_info"]
        path_alias_info[module_path] = []
        alias_info = path_alias_info[module_path]

        visitor = VisitorForAliasInfo(source_code_path, module_path, codebase_parent_path, codebase_root_path,
                                    alias_info)
    elif get_op == GetOp.get_graph_op:
        codebase_parent_path = paths_dct["codebase_parent_path"]
        codebase_root_path = paths_dct["codebase_root_path"]

        class_hierarchy_graph = data_dct["class_hierarchy_graph"]
        alias_name_path_resolved_path = data_dct["alias_name_path_resolved_path"]

        path_last_alias_str_info = dependencies_dct["path_last_alias_str_info"]
        path_type = dependencies_dct["path_type"]

        visitor = VisitorForGraph(source_code_path, module_path, codebase_parent_path, codebase_root_path,
                                class_hierarchy_graph, alias_name_path_resolved_path,
                                path_last_alias_str_info, path_type,
                                LOG_AST_PARSE_DATA)

    visitor.visit(ast_parse)

def get_alias_info(source_code_path, codebase_parent_path, codebase_root_path,
                path_alias_info, module_paths, path_type):
    """
    Populates path_alias_info by ast parse \\
    Adds to module_paths and path_type
    """

    paths_dct = {
        "source_code_path": source_code_path,
        "relative_import_path": "",
        "codebase_parent_path": codebase_parent_path,
        "codebase_root_path": codebase_root_path
    }
    data_dct = {
        "path_alias_info": path_alias_info,
        "module_paths": module_paths,
        "path_type": path_type
    }
    dependencies_dct = {}
    get_data_from_ast_parse(paths_dct,
                            data_dct,
                            dependencies_dct,
                            GetOp.get_alias_info_op)

def get_graph(source_code_path, codebase_parent_path, codebase_root_path,
            class_hierarchy_graph, alias_name_path_resolved_path,
            path_last_alias_str_info, path_type,
            ast_dump_info):
    """
    Populates class_hierarchy_graph from ast parse and dependencies
    """

    paths_dct = {
        "source_code_path": source_code_path,
        "relative_import_path": "",
        "codebase_parent_path": codebase_parent_path,
        "codebase_root_path": codebase_root_path
    }
    data_dct = {
        "class_hierarchy_graph": class_hierarchy_graph,
        "alias_name_path_resolved_path": alias_name_path_resolved_path
    }
    dependencies_dct = {
        "path_last_alias_str_info": path_last_alias_str_info,
        "path_type": path_type
    }
    get_data_from_ast_parse(paths_dct,
                            data_dct,
                            dependencies_dct,
                            GetOp.get_graph_op,
                            ast_dump_info)

def write_ast_parse_to_dump_file(ast_parse, ast_dump_path):
    """
    Writes ast_parse to file at ast_dump_path
    """

    ast_dump = ast.dump(ast_parse, indent=4)

    if os.path.exists(ast_dump_path):
        os.remove(ast_dump_path)

    with open(ast_dump_path, "w") as file:
        for line in ast_dump:
            file.write(line)
    file.close()

def dump_graph(class_hierarchy_graph, pickle_dump_folder, pickle_dump_filename):
    """
    Dumps the class hierarchy graph to pickle file at folder_for_dump\\pickle_dump_filename
    """

    if not os.path.exists(pickle_dump_folder):
        os.mkdir(pickle_dump_folder)

    filename_for_pickle_dump = os.path.join(pickle_dump_folder, pickle_dump_filename)
    with open(filename_for_pickle_dump, "wb") as f:
        pickle.dump(class_hierarchy_graph, f, pickle.HIGHEST_PROTOCOL)
    f.close()

def usage_info():
    """
    Outputs the proper usage of this script
    """

    print("Usage:")
    print("python get_class_hierarchy_graph.py [path to Python source code]")
    print()
    print("Example:")
    print(f"python get_class_hierarchy_graph.py sample_script.py (sample_script.py is relative to {sys.argv[0]})")
    print("python get_class_hierarchy_graph.py <relative path to sample_script.py>")
    print("python get_class_hierarchy_graph.py \"<full path to sample_script.py>\"")
    print("python get_class_hierarchy_graph.py <relative path to source_code_folder>")
    print("python get_class_hierarchy_graph.py \"<full path to source_code_folder>\"")

def get_path_last_alias_str_info(path_alias_info, path_type):
    """
    Gets path last alias str info by retrieval and \\
    update, for wildcard imports, of alias info from path alias info
    """

    path_last_alias_str_info = dict()

    for path in path_alias_info:
        if path in path_last_alias_str_info:
            continue

        visited_paths = set()
        update_path_alias_dcts(visited_paths,
                               path_alias_info,
                               path_last_alias_str_info,
                               path,
                               path_type)

    return path_last_alias_str_info

def update_path_alias_dcts(visited_paths,
                           path_alias_info,
                           path_last_alias_str_info,
                           path,
                           path_type):
    """
    Returns the last defined alias_strs in path and recursively updates path_last_alias_str_info
    """

    if path in visited_paths:
        if LOG_AST_PARSE_DATA:
            print(f"\nfrom update path alias information: possible circular import that began at {path} or traversed to {path}")
        return [], False

    visited_paths.add(path)

    alias_info = path_alias_info[path]

    last_alias_str_info = None
    if path not in path_last_alias_str_info:
        path_last_alias_str_info[path] = dict()
        last_alias_str_info = path_last_alias_str_info[path]

        for i in range(len(alias_info)):
            first_alias_entry = alias_info[i][0]
            if first_alias_entry[0] == "*":
                p = first_alias_entry[2]
                if p not in path_alias_info: # path of module of from module import * is not in code base
                    continue
                p = p if path_type[p] == PathType.file else p + ".__init__"
                if p not in path_alias_info: # path of module of from module import * is not in code base
                    continue
                last_defined_alias_strs, status = update_path_alias_dcts(visited_paths,
                                                                        path_alias_info,
                                                                        path_last_alias_str_info,
                                                                        p,
                                                                        path_type)
                if not status:
                    continue

                node = first_alias_entry[3]
                alias_info[i] = []
                for alias_str in last_defined_alias_strs:
                    alias_info[i].append((alias_str, alias_str, p, node))
                    last_alias_str_info[alias_str] = (alias_str, p, node)    # overwrites alias_str entry in last_alias_str_info
            else:
                for alias_entry in alias_info[i]:
                    alias_str = alias_entry[0]
                    if alias_str == "del":
                        alias_str = alias_entry[1]
                        if alias_str in last_alias_str_info:
                            del last_alias_str_info[alias_str]
                    else:
                        last_alias_str_info[alias_str] = (alias_entry[1], alias_entry[2], alias_entry[3])   # overwrites alias_str entry in last_alias_str_info
    else:
        last_alias_str_info = path_last_alias_str_info[path]

    return last_alias_str_info.keys(), True

if __name__ == "__main__":
    """
    Get input that corresponds to a Python code library (from command line arguments) \\
    Create directed graphs in which each graph represents the class hierarchy of the code library
        Nodes represent the classes
        Edges represent an inheritance relationship between the classes
        For directed edge (v_i, v_j), v_j is direct subclass of v_i

    Only gets graph in directory \\
    Does not parse to classes from external libraries or modules \\
    Classes in Python files that could not be parsed are not accounted for in the graph.

    Dumps graph into a pickle file
    """

    source_code_path = get_path(SOURCE_CODE_PATH_ARGUMENT_INDEX, usage_info)
    if source_code_path == None:
        exit(1)

    print(f"retrieval of class hierarchy graph of source code at {source_code_path}")
    print("does not account for definitions of classes with same names within same file or classes within closures")

    ast_dump_folder_path = None
    ast_dump_filename_prefix = None
    ast_dump_info = None
    if DUMP_AST:
        ast_dump_folder_path = create_ast_dump_folder(source_code_path)
        ast_dump_filename_prefix = ""
        ast_dump_info = (ast_dump_folder_path, ast_dump_filename_prefix, True)

    # key: module_path, value: list of list of the following entry
        # alias_str, alias_name, path with alias_name, node
        # or
        # "del", alias_str
    path_alias_info = dict()

    codebase_parent_path = get_parent_path(source_code_path)
    codebase_root_path = source_code_path

    # first scan gets the module paths in dot notation and path_type
    # since scan is recursive, shorter subsequence paths are before longer ones
    module_paths = []

    # key: path in dot notation, value: PathType
    path_type = dict()

    get_alias_info(source_code_path, codebase_parent_path, codebase_root_path,
                path_alias_info, module_paths, path_type)

    # key: module_path, value:
        # key: alias_str, value: alias_name, path with alias_name, node
    path_last_alias_str_info = get_path_last_alias_str_info(path_alias_info, path_type)

    # key: class identifier, value: list of identifiers of inherited classes, module path of class
    class_hierarchy_graph = dict()

    # key: (alias_name, path), value: resolved path of alias_name
    # for memoization of the resolved path of an alias name in path
    alias_name_path_resolved_path = dict()

    get_graph(source_code_path, codebase_parent_path, codebase_root_path,
            class_hierarchy_graph, alias_name_path_resolved_path,
            path_last_alias_str_info, path_type,
            ast_dump_info)

    if LOG_GRAPH_INFO:
        print()
        print("class hierarchy graph information")
        print_class_hierarchy_graph_info(class_hierarchy_graph)

    pickle_dump_filename = get_name_directory_or_file(source_code_path) + CLASS_HIERARCHY_GRAPH_DUMP_SUFFIX + ".pkl"

    print()
    print(f"dump class hierarchy graph to {os.path.join(FOLDER_WITH_CLASS_HIERARCHY_GRAPHS, pickle_dump_filename)}")
    dump_graph(class_hierarchy_graph, FOLDER_WITH_CLASS_HIERARCHY_GRAPHS, pickle_dump_filename)