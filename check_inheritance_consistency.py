import enum
import pickle

from util import *

GRAPH_PICKLE_DUMP_PATH_ARGUMENT_INDEX = 1 # 0-indexed

# two types of output: console log (LOG_<identifier>) and dump to file (DUMP_<identifier>)
LOG_GRAPH_INFO = False
LOG_LINEARIZATION_ORDER = False
LOG_LINEARIZATION = False
LOG_LINEARIZATION_VERBOSE = False   # only log if LOG_LINEARIZATION is set to True

LOG_ERROR_LINEARIZATION = False # for log of error with linearization not due to inconsistency
LOG_CYCLE_INCONSISTENT = True
LOG_SOURCE_LOGICAL_INCONSISTENT = True

DUMP_SOURCE_LOGICAL_INCONSISTENT = True
SOURCE_LOGICAL_INCONSISTENT_INFO_FOLDER_NAME = "source_logical_inconsistent_info"

DUMP_CYCLE_INCONSISTENT = True
CYCLE_INCONSISTENT_INFO_FOLDER_NAME = "cycle_inconsistent_info"

LOG_INHERITED_LOGICAL_INCONSISTENT = False

class LinearizationStatus(enum.Enum):
    success = 0
    error = success + 1
    cycle_inconsistent = error + 1
    source_logical_inconsistent = cycle_inconsistent + 1
    inherited_logical_inconsistent = source_logical_inconsistent + 1

def load_class_hierarchy_graph():
    graph_pickle_dump_path = get_path(GRAPH_PICKLE_DUMP_PATH_ARGUMENT_INDEX, usage_info)
    if graph_pickle_dump_path == None:
        exit(1)

    class_hierarchy_graph = None
    with open(graph_pickle_dump_path, "rb") as f:
        class_hierarchy_graph = pickle.load(f)
    f.close()

    return class_hierarchy_graph, graph_pickle_dump_path

def cycle_inconsistency_check(class_hierarchy_graph):
    """
    Searches for classes that are in cycles in the class hierarchy graph \\
    Those classes are considered cycle inconsistent

    Returns the names of classes that are in cycle, the number of classes that are cycle inconsistent, \\
    and information on the cycles
    """

    classes_in_cycle = set()

    cycles_info = ""
    sccs = find_sccs(class_hierarchy_graph)
    for scc in sccs:
        # if the scc consists of one node and does not have edge to itself
        # that scc is not a cycle
        if len(scc) == 1:
            class_identifier = scc[0]
            inherited_class_identifiers = class_hierarchy_graph[class_identifier][0]
            if class_identifier not in inherited_class_identifiers:
                continue

        cycles_info += f"cycle: {scc}\n"
        for class_identifier in scc:
            classes_in_cycle.add(class_identifier)
            cycles_info += f"class {class_identifier} from {class_hierarchy_graph[class_identifier][1]}\n"
        cycles_info += "\n"

    num_classes_cycle_inconsistent = len(classes_in_cycle)
    if num_classes_cycle_inconsistent > 0 and LOG_CYCLE_INCONSISTENT:
        classes_in_cycle_lst = sorted(list(classes_in_cycle))

        for class_identifier in classes_in_cycle_lst:
            print(f"Class {class_identifier} is in cycle inheritance. Class {class_identifier} is cycle inconsistent.")

    return classes_in_cycle, num_classes_cycle_inconsistent, cycles_info

def find_sccs(class_hierarchy_graph):
    """
    Uses Tarjan's algorithm for finding strongly connected components to find each \\
    strongly connected component in the class hierarchy graph

    Returns a list of each strongly connected component from the graph
    """

    sccs = []

    # index and lowlink initialized to None, onStack initialized to False
    node_info = dict()  # key: class_identifier, value: [index, lowlink, onStack]
    class_identifiers = class_hierarchy_graph.keys()
    for class_identifier in class_identifiers:
        node_info[class_identifier] = [None, None, False]

    def strongconnect(v, index):
        node_info[v][0] = index
        node_info[v][1] = index
        index += 1
        stack.append(v)
        node_info[v][2] = True

        neighbors = class_hierarchy_graph[v][0]
        for w in neighbors:
            # neighbor may not be in the graph as it may refer to a parent class that was not parsed
            # i. e. does not account for parent classes in external modules
            # only considers parent classes in code base
            if w not in class_hierarchy_graph:
                continue

            if node_info[w][0] == None:
                index = strongconnect(w, index)
                node_info[v][1] = min(node_info[v][1], node_info[w][1])
            elif node_info[w][2]:
                # neighbor w is in stack and in current scc
                node_info[v][1] = min(node_info[v][1], node_info[w][0])

        if node_info[v][1] == node_info[v][0]:
            scc = []
            w = None
            while w != v:
                w = stack.pop()
                node_info[w][2] = False
                scc.append(w)
            sccs.append(scc)

        return index

    index = 0
    stack = []
    for class_identifier in class_identifiers:
        if node_info[class_identifier][0] == None:
            index = strongconnect(class_identifier, index)

    return sccs

def logical_inconsistency_check(class_hierarchy_graph, classes_in_cycle):
    """
    Attempts to compute the c3 linearization of classes to check for logical inconsistency \\
    Returns the number of classes that are source logical inconsistent, inherited logical inconsistent, logical inconsistent, \\
    and source logical inconsistent information
    """

    print()
    print("get c3 linearizations")

    c3_linearizations, source_logical_inconsistent_info = get_c3_linearizations(class_hierarchy_graph, classes_in_cycle)

    num_classes_source_logical_inconsistent = 0
    num_classes_inherited_logical_inconsistent = 0
    num_classes_logical_inconsistent = 0
    for linearization in c3_linearizations.values():
        if linearization == LinearizationStatus.source_logical_inconsistent:
            num_classes_source_logical_inconsistent += 1
        elif linearization == LinearizationStatus.inherited_logical_inconsistent:
            num_classes_inherited_logical_inconsistent += 1

    num_classes_logical_inconsistent = num_classes_source_logical_inconsistent + num_classes_inherited_logical_inconsistent

    return num_classes_source_logical_inconsistent, num_classes_inherited_logical_inconsistent, num_classes_logical_inconsistent, \
        source_logical_inconsistent_info

def get_c3_linearizations(class_hierarchy_graph, classes_in_cycle):
    """
    Returns the c3 linearizations and the source logical inconsistent information
    """

    c3_linearizations = dict()
    source_logical_inconsistent_info = ""

    for class_identifier in class_hierarchy_graph.keys():
        if class_identifier in c3_linearizations:
            pass

        visited = set()
        linearization_order = []

        get_linearization_order(class_hierarchy_graph, class_identifier, visited, linearization_order)

        if LOG_LINEARIZATION_ORDER:
            print(f"linearization order from class {class_identifier}: {linearization_order}")

        source_logical_inconsistent_info += get_c3_linearizations_helper(class_hierarchy_graph, classes_in_cycle, linearization_order, c3_linearizations)

    return c3_linearizations, source_logical_inconsistent_info

def get_linearization_order(class_hierarchy_graph, class_identifier, visited, linearization_order):
    """
    Uses recursive DFS to compute the order to linearize classes in inheritance hierarchy from class_identifier \\
    Order is such that for class u, v in layer
        - If class v inherits from class u, class u before class v.
        - If no inheritance relationship between class u, v, class u before class v. \n
    For cycles, the ordering is undefined.
    """

    if class_identifier in visited or \
        class_identifier not in class_hierarchy_graph:    # class is not in local directory
        return

    visited.add(class_identifier)

    inherited_class_identifiers = class_hierarchy_graph[class_identifier][0]
    for inherited_class_identifier in inherited_class_identifiers:
        get_linearization_order(class_hierarchy_graph, inherited_class_identifier, visited, linearization_order)

    linearization_order.append(class_identifier)

def get_c3_linearizations_helper(class_hierarchy_graph, classes_in_cycle, linearization_order, c3_linearizations):
    """
    Computes the c3 linearization of classes in the order given by linearization_order \\
    Returns source logical inconsistent information found from the linearization computation
    """

    source_logical_inconsistent_info = ""
    for class_identifier in linearization_order:
        if not class_identifier in class_hierarchy_graph:
            continue
        if class_identifier in c3_linearizations:
            continue
        if class_identifier in classes_in_cycle:
            if LOG_CYCLE_INCONSISTENT:
                print(f"Linearization of class {class_identifier} could not be computed since class {class_identifier} is in cycle inheritance.")

            c3_linearizations[class_identifier] = LinearizationStatus.cycle_inconsistent
            continue

        inherited_class_identifiers = class_hierarchy_graph[class_identifier][0].copy()

        # m = number of sublists, number of classes inherited + 1
        # n = length of sublist, length of linearization of parent class, number of classes inherited (for last sublist)
        # to get linearization of a class is O(mn * mn)

        merge_lists = []
        can_compute = True
        for inherited_class_identifier in inherited_class_identifiers:
            if not inherited_class_identifier in class_hierarchy_graph:
                continue

            inherited_class_linearization = c3_linearizations[inherited_class_identifier]

            # could not compute linearization of parent class
            if inherited_class_linearization == LinearizationStatus.error:
                if LOG_ERROR_LINEARIZATION:
                    output_str = f"Linearization of class {class_identifier} could not be computed since there was an error with computation of linearization of parent class {inherited_class_identifier}."
                    output_str += f" Error with computation of linearization of class {class_identifier}"
                    print(output_str)

                can_compute = False
                c3_linearizations[class_identifier] = LinearizationStatus.error
                break
            elif inherited_class_linearization == LinearizationStatus.cycle_inconsistent:
                if LOG_INHERITED_LOGICAL_INCONSISTENT:
                    output_str = f"Linearization of class {class_identifier} could not be computed since parent class {inherited_class_identifier} is in a cycle."
                    output_str += f" Class {class_identifier} is inherited logical inconsistent."
                    print(output_str)

                can_compute = False
                c3_linearizations[class_identifier] = LinearizationStatus.inherited_logical_inconsistent
                break
            elif inherited_class_linearization == LinearizationStatus.source_logical_inconsistent or \
                inherited_class_linearization == LinearizationStatus.inherited_logical_inconsistent:

                if LOG_INHERITED_LOGICAL_INCONSISTENT:
                    logical_inconsistency_type = None
                    if inherited_class_linearization == LinearizationStatus.source_logical_inconsistent:
                        logical_inconsistency_type = "source"
                    elif inherited_class_linearization == LinearizationStatus.inherited_logical_inconsistent:
                        logical_inconsistency_type = "inherited"

                    output_str = f"Linearization of class {class_identifier} could not be computed since parent class {inherited_class_identifier} is {logical_inconsistency_type} logical inconsistent."
                    output_str += f" Class {class_identifier} is inherited logical inconsistent."
                    print(output_str)

                can_compute = False
                c3_linearizations[class_identifier] = LinearizationStatus.inherited_logical_inconsistent
                break
            else:   # could compute linearization of parent class
                merge_lists.append(c3_linearizations[inherited_class_identifier].copy())

        if not can_compute:
            continue

        if len(inherited_class_identifiers) > 0:
            merge_lists.append(inherited_class_identifiers)

        res, status, precedence_order_mismatch_info = get_c3_linearization(class_identifier, merge_lists, inherited_class_identifiers)
        if status == LinearizationStatus.error:
            if LOG_ERROR_LINEARIZATION:
                print(f"Linearization could not be computed for class {class_identifier} due to error in linearization computation.")
            c3_linearizations[class_identifier] = status
        elif status == LinearizationStatus.source_logical_inconsistent:
            x, y, inherited_class_with_differing_precedence = precedence_order_mismatch_info
            source_logical_inconsistent_info += source_logical_inconsistent_info_from_class(class_identifier, x, y, inherited_class_with_differing_precedence, class_hierarchy_graph, c3_linearizations)

            if LOG_SOURCE_LOGICAL_INCONSISTENT:
                output_str = f"Linearization could not be computed for class {class_identifier} due to logical inconsistency in linearization computation."
                output_str += f" Class {class_identifier} is source logical inconsistent."
                print(output_str)

            c3_linearizations[class_identifier] = status
        else:
            if LOG_LINEARIZATION:
                print(f"{class_identifier} c3 linearization: {res}")
                if LOG_LINEARIZATION_VERBOSE:
                    for name in res:
                        if name in class_hierarchy_graph:
                            print(f"class {name} from {class_hierarchy_graph[name][1]}")
                        else:
                            print(f"class {name} from external")
            c3_linearizations[class_identifier] = res

    return source_logical_inconsistent_info

def get_c3_linearization(class_identifier, merge_lists, inherited_class_identifiers):
    """
    computes the c3 linearization from merge_lists with following algorithm: \\
    res = [] \\
    while merge_lists is not empty
        search for first occurence of first element in list of merge_lists that is not in tail of any of list in merge_lists

        if such an occurrence could be found
            remove that element from each list in merge_lists

            remove empty lists in merge_lists

            add that element to res
        otherwise
            source logical inconsistency, linearization could not be computed \\
            gets source logical inconsistent information

    returns linearization, stored in res, or None if it could not be computed, linearization status, source logical inconsistent information
    """

    res = [class_identifier]

    num_lists = len(merge_lists)
    empty = num_lists == 0

    while not empty:
        in_head = []
        in_tail = dict()     # key: tail element, value: list of corresponding sublist indices and index in sublist

        for lst_index, lst in enumerate(merge_lists):
            if len(lst) == 0:
                if LOG_ERROR_LINEARIZATION:
                    print("Error: empty list in merge_lists")
                return (None, LinearizationStatus.error, None)
            for index, name in enumerate(lst):
                if index == 0:
                    in_head.append(name)
                if index > 0:
                    if name in in_tail:
                        in_tail[name].append((lst_index, index))
                    else:
                        in_tail[name] = [(lst_index, index)]

        selected_class = None
        for chosen_class in in_head:
            if not chosen_class in in_tail:
                selected_class = chosen_class
                break

        if not selected_class:
            if LOG_SOURCE_LOGICAL_INCONSISTENT:
                print(f"Error: no suitable next class for linearization of class {class_identifier}")

            x, y, inherited_class_with_differing_precedence = get_precedence_order_mismatch(merge_lists, num_lists, in_tail, inherited_class_identifiers)
            return (None, LinearizationStatus.source_logical_inconsistent, (x, y, inherited_class_with_differing_precedence))

        # removes selected_class from lists in merge_lists
        for lst in merge_lists:
            try:
                lst.remove(selected_class)
            except: # selected_class not in lst
                continue

        merge_lists = [lst for lst in merge_lists if len(lst) > 0]

        res.append(selected_class)

        num_lists = len(merge_lists)
        empty = num_lists == 0

    return (res, LinearizationStatus.success, None)

def get_precedence_order_mismatch(merge_lists, num_lists, in_tail, inherited_class_identifiers):
    """
    Returns the classes x, y in which there is a precedence order mismatch in linearization \\
    Also returns the parent class in which the mismatch was found
    """

    local_procedence_order_lst = merge_lists[num_lists - 1]
    x = local_procedence_order_lst[0]
    y = None
    inherited_class_with_differing_precedence = None

    after_x = set(local_procedence_order_lst[1:])
    # for each sublist in which x is at a tail
    for lst_index, x_index in in_tail[x]:
        lst = merge_lists[lst_index]
        for i in range(x_index - 1, -1, -1):
            before_x_element = lst[i]
            # if element in set of elements right of x in local_precedence_order_lst
            if before_x_element in after_x:
                y = before_x_element
                inherited_class_with_differing_precedence = inherited_class_identifiers[lst_index]
                break
        if y:
            break

    return x, y, inherited_class_with_differing_precedence

def source_logical_inconsistent_info_from_class(class_identifier, x, y, inherited_class_with_differing_precedence, class_hierarchy_graph, c3_linearizations):
    """
    Creates dump string source logical inconsistent information \\
    x and y are the identifiers of the classes in local precedence order of class with identifier class_identifier.
    """

    source_logical_inconsistent_info = f"Linearization of class {class_identifier} cannot be computed.\n"
    source_logical_inconsistent_info += f"class {x} before class {y} in local precedence order of class {class_identifier},\n"
    source_logical_inconsistent_info += f"class {y} before class {x} in precedence order of class {inherited_class_with_differing_precedence}.\n"
    source_logical_inconsistent_info += f"class {class_identifier} from {class_hierarchy_graph[class_identifier][1]}\n"

    x_location = class_hierarchy_graph[x][1] if x in class_hierarchy_graph else "external"
    y_location = class_hierarchy_graph[y][1] if y in class_hierarchy_graph else "external"
    source_logical_inconsistent_info += f"class {x} from {x_location}, linearization: {c3_linearizations[x]}\n"
    source_logical_inconsistent_info += f"class {y} from {y_location}, linearization: {c3_linearizations[y]}\n\n"

    return source_logical_inconsistent_info

def get_info_dump_path(info_folder_name):
    graph_pickle_dump_path = get_path(GRAPH_PICKLE_DUMP_PATH_ARGUMENT_INDEX, usage_info)
    name = get_name_directory_or_file(graph_pickle_dump_path)
    name = name[:name.find(CLASS_HIERARCHY_GRAPH_DUMP_SUFFIX)]
    cycle_inconsistent_info_dump_path = os.path.join(info_folder_name, name + ".txt")
    return cycle_inconsistent_info_dump_path

def dump_info(output, info_folder_name, info_dump_path, info_identifier):
    try:
        if not os.path.exists(info_folder_name):
            os.mkdir(info_folder_name)

        if os.path.exists(info_dump_path):
            os.remove(info_dump_path)

        with open(info_dump_path, "w") as file:
            file.write(output)
        file.close()

        print(f"Dumped {info_identifier} information to {info_dump_path}")
    except:
        print(f"Could not dump {info_identifier} information")

def get_num_resolved_bases(class_hierarchy_graph):
    num_resolved_bases = 0
    for class_identifier in class_hierarchy_graph:
        num_resolved_bases += len(class_hierarchy_graph[class_identifier][0])
    return num_resolved_bases

def check_inconsistency(class_hierarchy_graph):
    """
    Static check for following type of inconsistency:
        - cycle inconsistency:
            - Classes in cycle in class hierarchy graph
        - source logical inconsistency:
            - Class k inherits from class i, j in that order; class j inherits from class i
        - inherited logical inconsistency:
            - Class k inherits from a class with cyclic or logical inconsistency
        - logical inconsistency: either source or inherited logical inconsistency

    Outputs relevant information
    """

    print()
    print("cycle inconsistency check")
    classes_in_cycle, num_classes_cycle_inconsistent, cycles_info = cycle_inconsistency_check(class_hierarchy_graph)

    print()
    print("logical inconsistency check")
    num_classes_source_logical_inconsistent, num_classes_inherited_logical_inconsistent, \
    num_classes_logical_inconsistent, source_logical_inconsistent_info = logical_inconsistency_check(class_hierarchy_graph, classes_in_cycle)

    print()
    print(f"number of classes that are cycle inconsistent: {num_classes_cycle_inconsistent}")

    if num_classes_cycle_inconsistent > 0 and DUMP_CYCLE_INCONSISTENT:
        cycle_inconsistent_info_dump_path = get_info_dump_path(CYCLE_INCONSISTENT_INFO_FOLDER_NAME)
        dump_info(cycles_info, CYCLE_INCONSISTENT_INFO_FOLDER_NAME, cycle_inconsistent_info_dump_path, "cycle inconsistent")

    print(f"number of classes that are source logical inconsistent: {num_classes_source_logical_inconsistent}")

    if num_classes_source_logical_inconsistent > 0 and DUMP_SOURCE_LOGICAL_INCONSISTENT:
        source_logical_inconsistent_info_dump_path = get_info_dump_path(SOURCE_LOGICAL_INCONSISTENT_INFO_FOLDER_NAME)
        dump_info(source_logical_inconsistent_info, SOURCE_LOGICAL_INCONSISTENT_INFO_FOLDER_NAME, source_logical_inconsistent_info_dump_path, "source logical inconsistent")

    print(f"number of classes that are inherited logical inconsistent: {num_classes_inherited_logical_inconsistent}")
    print(f"number of classes that are logical inconsistent (either source or inherited logical inconsistent): {num_classes_logical_inconsistent}")

    print()

    num_resolved_bases = get_num_resolved_bases(class_hierarchy_graph)
    print(f"number of resolved bases from ClassDef: {num_resolved_bases}")
    print(f"number of classes in class hierarchy graph: {len(class_hierarchy_graph.keys())}")

def usage_info():
    """
    Outputs the proper usage of this script
    """

    print("Usage:")
    print("python check_inheritance_consistency.py [path to class hierarchy graph pickle dump file]")
    print("can use python get_class_hierarchy_graph.py [path to Python source code] to generate the pickle dump file")
    print()
    print("Example:")
    print(f"python check_inheritance_consistency.py sample_script_class_hierarchy_graph.pkl (sample_script_class_hierarchy_graph.pkl is relative to {sys.argv[0]})")
    print("python check_inheritance_consistency.py <relative path to sample_script_class_hierarchy_graph.pkl>")
    print("python check_inheritance_consistency.py \"<full path to sample_script_class_hierarchy_graph.pkl>\"")

if __name__ == "__main__":
    """
    Given class hierarchy graph as input, searchs for cycle and logical inconsistencies \\
    Uses c3 linearization for search of logical inconsistency
    """

    class_hierarchy_graph, graph_pickle_dump_path = load_class_hierarchy_graph()

    if LOG_GRAPH_INFO:
        print()
        print("class hierarchy graph information")
        print_class_hierarchy_graph_info(class_hierarchy_graph)
        print()

    print(f"static check for cycle and logical inconsistency in class hierarchy graph from {graph_pickle_dump_path}")

    # within provided codebase, __main__.<class> classes, no check for classes from external modules
    check_inconsistency(class_hierarchy_graph)