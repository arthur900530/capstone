"""
Strict test suite for rbtree.py — a pure-Python Red-Black Tree.
All 30 tests must pass: pytest test_rbtree.py -v
"""
import pytest
from rbtree import RedBlackTree, RED, BLACK


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rb_properties_hold(tree):
    """
    Returns True iff the tree satisfies all four RB properties:
      1. Every node is RED or BLACK.
      2. The root is BLACK.
      3. No red node has a red parent (no two consecutive reds on any path).
      4. Every path from root to NIL leaf has the same number of black nodes.
    """
    if tree.root is tree.NIL:
        return True

    # Property 2
    assert tree.root.color == BLACK, "Root must be BLACK"

    def check(node):
        if node is tree.NIL:
            return 1  # count this NIL as one black node
        # Property 1
        assert node.color in (RED, BLACK)
        # Property 3
        if node.color == RED:
            assert node.left.color == BLACK, f"Red node {node.key} has red left child"
            assert node.right.color == BLACK, f"Red node {node.key} has red right child"
        left_bh  = check(node.left)
        right_bh = check(node.right)
        # Property 4
        assert left_bh == right_bh, (
            f"Black-height mismatch at {node.key}: left={left_bh} right={right_bh}"
        )
        return left_bh + (1 if node.color == BLACK else 0)

    check(tree.root)
    return True


def inorder(tree):
    """Return list of keys in ascending order."""
    result = []
    def _walk(node):
        if node is tree.NIL:
            return
        _walk(node.left)
        result.append(node.key)
        _walk(node.right)
    _walk(tree.root)
    return result


def height(tree):
    """Return the height of the tree (longest root-to-leaf path)."""
    def _h(node):
        if node is tree.NIL:
            return 0
        return 1 + max(_h(node.left), _h(node.right))
    return _h(tree.root)


# ---------------------------------------------------------------------------
# Basic insertion
# ---------------------------------------------------------------------------

class TestInsert:

    def test_empty_tree(self):
        t = RedBlackTree()
        assert inorder(t) == []

    def test_single_insert(self):
        t = RedBlackTree()
        t.insert(10)
        assert inorder(t) == [10]
        assert rb_properties_hold(t)

    def test_three_nodes_left_rotate(self):
        t = RedBlackTree()
        for v in [10, 20, 30]:
            t.insert(v)
        assert inorder(t) == [10, 20, 30]
        assert rb_properties_hold(t)

    def test_three_nodes_right_rotate(self):
        t = RedBlackTree()
        for v in [30, 20, 10]:
            t.insert(v)
        assert inorder(t) == [10, 20, 30]
        assert rb_properties_hold(t)

    def test_seven_nodes(self):
        t = RedBlackTree()
        for v in [7, 3, 18, 10, 22, 8, 11]:
            t.insert(v)
        assert inorder(t) == [3, 7, 8, 10, 11, 18, 22]
        assert rb_properties_hold(t)

    def test_duplicate_insert_ignored(self):
        """Inserting a duplicate key must be a no-op."""
        t = RedBlackTree()
        t.insert(5)
        t.insert(5)
        assert inorder(t) == [5]
        assert rb_properties_hold(t)

    def test_root_is_always_black(self):
        t = RedBlackTree()
        for v in [1, 2, 3, 4, 5]:
            t.insert(v)
        assert t.root.color == BLACK

    def test_log_height_after_100_inserts(self):
        """Height must be <= 2 * log2(n+1) for n=100."""
        import math
        t = RedBlackTree()
        for v in range(1, 101):
            t.insert(v)
        assert height(t) <= 2 * math.log2(101), \
            f"Tree height {height(t)} exceeds 2*log2(101)≈{2*math.log2(101):.1f}"

    def test_inorder_sorted_after_random_inserts(self):
        import random
        random.seed(42)
        vals = random.sample(range(1000), 50)
        t = RedBlackTree()
        for v in vals:
            t.insert(v)
        assert inorder(t) == sorted(vals)
        assert rb_properties_hold(t)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class TestSearch:

    def test_search_present(self):
        t = RedBlackTree()
        for v in [5, 3, 7]:
            t.insert(v)
        assert t.search(3) is True

    def test_search_absent(self):
        t = RedBlackTree()
        for v in [5, 3, 7]:
            t.insert(v)
        assert t.search(99) is False

    def test_search_empty(self):
        t = RedBlackTree()
        assert t.search(1) is False

    def test_search_after_insert(self):
        t = RedBlackTree()
        t.insert(42)
        assert t.search(42) is True
        assert t.search(41) is False


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------

class TestDelete:

    def test_delete_only_node(self):
        t = RedBlackTree()
        t.insert(10)
        t.delete(10)
        assert inorder(t) == []

    def test_delete_leaf(self):
        t = RedBlackTree()
        for v in [10, 5, 20]:
            t.insert(v)
        t.delete(5)
        assert inorder(t) == [10, 20]
        assert rb_properties_hold(t)

    def test_delete_node_with_two_children(self):
        t = RedBlackTree()
        for v in [10, 5, 20, 3, 7]:
            t.insert(v)
        t.delete(5)   # node with children 3 and 7
        assert inorder(t) == [3, 7, 10, 20]
        assert rb_properties_hold(t)

    def test_delete_root(self):
        t = RedBlackTree()
        for v in [10, 5, 20]:
            t.insert(v)
        t.delete(10)
        assert 10 not in inorder(t)
        assert rb_properties_hold(t)

    def test_delete_nonexistent_is_noop(self):
        t = RedBlackTree()
        for v in [10, 5, 20]:
            t.insert(v)
        t.delete(99)  # must not raise
        assert inorder(t) == [5, 10, 20]
        assert rb_properties_hold(t)

    def test_delete_all_nodes(self):
        t = RedBlackTree()
        vals = [10, 5, 20, 3, 7, 15, 25]
        for v in vals:
            t.insert(v)
        for v in vals:
            t.delete(v)
        assert inorder(t) == []

    def test_rb_properties_after_sequential_deletes(self):
        t = RedBlackTree()
        for v in range(1, 21):
            t.insert(v)
        for v in [4, 8, 12, 16, 20, 2, 6, 10, 14, 18]:
            t.delete(v)
            assert rb_properties_hold(t), f"RB properties violated after deleting {v}"

    def test_rb_properties_after_random_deletes(self):
        import random
        random.seed(7)
        vals = list(range(1, 51))
        t = RedBlackTree()
        for v in vals:
            t.insert(v)
        delete_order = random.sample(vals, 25)
        for v in delete_order:
            t.delete(v)
        assert rb_properties_hold(t)
        remaining = sorted(set(vals) - set(delete_order))
        assert inorder(t) == remaining

    def test_inorder_correct_after_mixed_ops(self):
        t = RedBlackTree()
        for v in [50, 25, 75, 10, 35, 60, 90]:
            t.insert(v)
        t.delete(25)
        t.insert(30)
        t.delete(75)
        t.insert(80)
        expected = sorted([50, 10, 35, 60, 90, 30, 80])
        assert inorder(t) == expected
        assert rb_properties_hold(t)

    def test_search_after_delete(self):
        t = RedBlackTree()
        for v in [1, 2, 3, 4, 5]:
            t.insert(v)
        t.delete(3)
        assert t.search(3) is False
        assert t.search(2) is True
        assert t.search(4) is True
