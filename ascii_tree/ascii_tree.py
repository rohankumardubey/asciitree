'''
Print tree of ascii boxes
Currently does not stagger nodes, i.e.
only works if all nodes on the same level
can fit on the same level.

Many ways to do this. It would be interesting to see which
configuration allows most objects to
be placed on the screen.

'''
import math
from copy import copy
from typing import List, Callable
from .constants import SCREEN_WIDTH, MARGIN, PADDING, BOX_MAX_WIDTH, SHOW_CONT_DIALOG
from .custom_types import Node, Offset, AsciiBox
from .draw import draw


def get_margin(node_count: int, margin: int=MARGIN)->float:
    '''
    determine the amount of margin for node_count
    '''
    return margin*(node_count-1)


def recomp_node_width(root: Node, add_on: Node=None)->int:
    '''
    Similar to get_node_widths, but only
    computes the width of a single node.
    Assumes children widths are computed
    for non-leaf nodes.
    Optionally accepts an `add_on`, i.e. a child
    Node, not actually added to parent
    '''
    if root.is_leaf and add_on is None:
        return root.box.width

    if add_on:
        total_width = sum(child.box.total_width for child in root.children) + \
            + get_margin(len(root.children) + 1) + add_on.box.total_width
    else:
        total_width = sum(child.box.total_width for child in root.children) + \
            + get_margin(len(root.children))

    total_width = max(total_width, root.box.width)
    return total_width


def get_node_widths(root: Node, margin: int=MARGIN):
    '''
    - compute width of each node
    - for a leaf node, this is width of encapsulating AsciiBox
    - for a non-leaf node this is the width of the tree
      rooted at node. this includes width between
      children but not around them

    Args:
        margin: space between two nodes
    Returns:
        dict: map of width of each node.
    '''
    total_width = 0
    if root.is_leaf:
        total_width = root.box.width
    else:
        for child in root.children:
          total_width += get_node_widths(child)
        # n children need n-1 spaces between them
        total_width += get_margin(len(root.children))
        # in case parent is wider than all children
        total_width = max(total_width, root.box.width)
    root.box.total_width = total_width
    return total_width


def get_tree_height(root: Node, margin: int=MARGIN)->int:
    '''
    compute height of tree rooted at `root`.
    this assumes nodes are not staggered
    '''
    stack = [(root, root.box.box_height)]
    tree_height = 0
    while stack:
        node, height = stack.pop()
        tree_height = max(tree_height, height)
        for child in node.children:
            stack.append((child, child.box.box_height + height + margin))
    return tree_height


def position_nodes(root: Node, left_offset: int, top_offset: int, margin: int=MARGIN)-> Offset:
    '''
    compute top-left coordinate for each AsciiBox
    update node.box.position in place
    Args:
        left_offset: (inclusive) left position;
                    for root this is 0
        top_offset
    '''
    if root.is_leaf:
        root.box.position = Offset(left_offset, top_offset)
    else:
        # compute positions for children
        # compute offsets for children
        child_top_offset = top_offset + root.box.box_height + margin
        for i, child in enumerate(root.children):
            if i == 0:
                child_left_offset = left_offset
            else:
                prev_child = root.children[i-1]
                # using the offset of previous sibling is wrong since
                # if the sibling has children, the sibling will be positioned
                # in the middle of its children and its offset will shifted to right
                # want the left offset of the leftmost descendent of the prev
                # sibling. This can be achieved by directly storing that value
                child_left_offset = prev_child.box.tree_left_offset + margin + prev_child.box.total_width
                # print('prev_child is {} w: {}, pos: {}'.format(prev_child, prev_child.box.total_width, prev_child.box.position))
            position_nodes(child, child_left_offset, child_top_offset, margin)
            # print('In position_node: {} {}'.format(child, child.box.position))
            # import pdb; pdb.set_trace()
        # compute self positions
        # place between first and last child
        first = root.children[0].box.position.left
        last = root.children[-1].box.position.left
        node_left_offset = left_offset + (last - first) // 2
        root.box.position = Offset(node_left_offset, top_offset)
    # store the left-offset of the space for the box and it's descendents
    root.box.tree_left_offset = left_offset
    return root.box.position


def gen_ascii_nodes(root):
    '''
    Traverse tree and update `Node`.box with AsciiBox instance
    '''
    stack = [root]
    while stack:
        node = stack.pop()
        node.box = AsciiBox(node.val)
        for child in node.children:
            stack.append(child)


def update_page_nums(page_map: dict, splits: List[Node]):
    '''
    page_map: maps root to msg_node, referencing it
    '''
    for i, split in enumerate(splits):
        if split in page_map:
            # relies on template string value
            page_map[split].val = page_map[split].val.format(str(i))


def split_tree(root: Node, max_width: int=SCREEN_WIDTH, first_max_width: int=SCREEN_WIDTH,
               margin: int=MARGIN, show_page: bool=SHOW_CONT_DIALOG):
    '''
    split a tree that is too wide/tall.
    allows specifying a different first_max_width, e.g.
    if node needs to be attached to parent, in some limited
    space.
    Whether to display page number is configurable, i.e. when the parent
    node is distinct enough to visually track.
    Splitting algorithm:
        - keep list of splits
        - clone root
        - iteratively add a child (to this split) and determine
          width (try with pagenum box if enabled)
        - if tree gets too wide, split root
        - if child is too wide, iteratively split child
        - track page number
    NB: typically have to fully copy a root at a split since
    location and width info is stored directly on the objects.

    TODO: implement turning off cont. on ... dialog
    '''
    # a child call will update a clone
    # we may want to update actual, especially when slicing the tree
    sroot = copy(root)
    splits = []
    child_splits = []  # inserted after splits on current level
    msg_node = Node.init_with_box('Cont. on page {}  ')
    msg_node_copy = None
    # maximum width a single child can consume
    max_child_width = max_width - margin - msg_node.box.width
    # map root to msg_node
    page_map = {}
    for i, child in enumerate(root.children):
        if child.box.total_width > max_child_width:
            # recursively split child
            csplits, cpage_map = split_tree(child, max_width=max_width, first_max_width=max_child_width,
                                            show_page=show_page)
            # will get attached to sroot
            child = csplits[0]  # partitioned child
            # keep separated so these splits can be inserted after siblings
            child_splits.extend(csplits[1:])
            page_map.update(cpage_map)

        sroot.children.append(child)
        is_last_child = i == len(root.children) - 1
        if is_last_child:
            new_width = recomp_node_width(sroot)
        else:
            new_width = recomp_node_width(sroot, add_on=msg_node)

        # handle different first_max_width and max_width
        if i == 0:
            alloc_width = first_max_width
        else:
            alloc_with = max_width

        if new_width > alloc_width:
            sroot.children.pop()
            msg_node_copy = copy(msg_node)
            sroot.children.append(msg_node_copy)
            # recompute widths
            get_node_widths(sroot)
            position_nodes(sroot, 0, 0)
            splits.append(sroot)
            # handle new childs
            sroot = copy(sroot)
            sroot.children.append(child)
            page_map[sroot] = msg_node_copy

    page_map[sroot] = msg_node_copy
    get_node_widths(sroot)
    position_nodes(sroot, 0, 0)
    splits.append(sroot)
    splits.extend(child_splits)
    return splits, page_map


def draw_tree(root)->List[List[List[str]]]:
    '''
    Draw Ascii tree repr of root.
    Return a list of screen objects with chunks of tree.
    '''
    screens = []
    gen_ascii_nodes(root)
    get_node_widths(root)
    if root.box.total_width <= SCREEN_WIDTH:
        # set screen height to be height of tree
        screen_height = get_tree_height(root)
        # construct screen buffer
        screen = [[' ']*SCREEN_WIDTH for _ in range(screen_height)]
        position_nodes(root, 0, 0)
        draw(screen, root)
        screens.append(screen)
    else:
        # if tree is too wide, split the tree
        splits, page_map = split_tree(root)
        update_page_nums(page_map, splits)
        for sroot in splits:
            screen_height = get_tree_height(sroot)
            screen = [[' ']*SCREEN_WIDTH for _ in range(screen_height)]
            draw(screen, sroot)
            screens.append(screen)

    return screens


def print_screen(screen):
    '''
    print each row of the screen
    '''
    for row in screen:
        print(''.join(row))


def print_tree(root: Node):
    '''
    Output tree to stdout
    '''
    screens = draw_tree(root)
    for i, screen in enumerate(screens):
        print('page: {}'.format(i))
        print_screen(screen)
        if i != len(screens)-1:
            print('-'*SCREEN_WIDTH)



if __name__ == '__main__':
    root = Node('onomatopaie'*10)
    root.children = [Node('boobar'), Node('car'), Node('scuba'), Node('tarzanman'), Node('spandan'), Node('abcdccd')] # , Node('sadgshdd'), Node('saddsddadadadadaa')]
    root.children[-1].children = [Node('navreet'), Node('smartcat'*20), Node('amcdcdcs dfdfdfsfdfsdffsdfsfsfsfssfs')]
    root.children[-1].children[0].children = [Node('fooobarsf'*10)]
    root.children[-1].children[1].children = [Node('fooobarsf')]
    root.children.append(Node('carbar'))

    # this produces an empty imput
    root3 = Node('cloner '*20)
    for i in range(6):
        root3.children.append(Node(str(i)*50))

    root2 = Node('c'*10)
    for i in range(7):
        root2.children.append(Node(str(i)*10))
    for i in range(5):    root2.children[2].children.append(Node(str(i*10)*10))

    root4 = Node('R'*10)
    root4.children = [Node('c1'*10)]
    for i in range(9):
        root4.children[0].children.append(Node(str(i)*10))
    root4.children.append(Node('c2'*10))
    for i in range(3, 8):
        root4.children.append(Node('c'+str(i)))

    print_tree(root)