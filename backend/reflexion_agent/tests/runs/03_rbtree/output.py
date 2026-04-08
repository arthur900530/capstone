"""
Red-Black Tree implementation.
"""

RED = 0
BLACK = 1


class Node:
    __slots__ = ['key', 'color', 'left', 'right', 'parent']
    
    def __init__(self, key, color=RED):
        self.key = key
        self.color = color
        self.left = None
        self.right = None
        self.parent = None


class RedBlackTree:
    def __init__(self):
        # NIL sentinel node - always BLACK
        self.NIL = Node(None, BLACK)
        self.NIL.left = self.NIL
        self.NIL.right = self.NIL
        self.NIL.parent = self.NIL
        self.root = self.NIL

    def search(self, key):
        """Search for a key in the tree. Returns True if found, False otherwise."""
        node = self.root
        while node != self.NIL:
            if key == node.key:
                return True
            elif key < node.key:
                node = node.left
            else:
                node = node.right
        return False

    def insert(self, key):
        """Insert a key into the tree. Duplicates are silently ignored."""
        # Check for duplicate
        if self.search(key):
            return
        
        # Create new node
        new_node = Node(key, RED)
        new_node.left = self.NIL
        new_node.right = self.NIL
        new_node.parent = self.NIL
        
        # BST insert
        parent = self.NIL
        current = self.root
        
        while current != self.NIL:
            parent = current
            if new_node.key < current.key:
                current = current.left
            else:
                current = current.right
        
        new_node.parent = parent
        
        if parent == self.NIL:
            self.root = new_node
        elif new_node.key < parent.key:
            parent.left = new_node
        else:
            parent.right = new_node
        
        # Fix RB properties
        self._insert_fixup(new_node)

    def _insert_fixup(self, node):
        """Fix Red-Black tree properties after insertion."""
        while node.parent.color == RED:
            if node.parent == node.parent.parent.left:
                uncle = node.parent.parent.right
                # Case 1: Uncle is RED
                if uncle.color == RED:
                    node.parent.color = BLACK
                    uncle.color = BLACK
                    node.parent.parent.color = RED
                    node = node.parent.parent
                else:
                    # Case 2: Uncle is BLACK and node is right child
                    if node == node.parent.right:
                        node = node.parent
                        self._left_rotate(node)
                    # Case 3: Uncle is BLACK and node is left child
                    node.parent.color = BLACK
                    node.parent.parent.color = RED
                    self._right_rotate(node.parent.parent)
            else:
                uncle = node.parent.parent.left
                # Case 1: Uncle is RED
                if uncle.color == RED:
                    node.parent.color = BLACK
                    uncle.color = BLACK
                    node.parent.parent.color = RED
                    node = node.parent.parent
                else:
                    # Case 2: Uncle is BLACK and node is left child
                    if node == node.parent.left:
                        node = node.parent
                        self._right_rotate(node)
                    # Case 3: Uncle is BLACK and node is right child
                    node.parent.color = BLACK
                    node.parent.parent.color = RED
                    self._left_rotate(node.parent.parent)
        
        # Property 2: Root must be BLACK
        self.root.color = BLACK

    def _left_rotate(self, x):
        """Perform left rotation on node x."""
        y = x.right
        x.right = y.left
        
        if y.left != self.NIL:
            y.left.parent = x
        
        y.parent = x.parent
        
        if x.parent == self.NIL:
            self.root = y
        elif x == x.parent.left:
            x.parent.left = y
        else:
            x.parent.right = y
        
        y.left = x
        x.parent = y

    def _right_rotate(self, y):
        """Perform right rotation on node y."""
        x = y.left
        y.left = x.right
        
        if x.right != self.NIL:
            x.right.parent = y
        
        x.parent = y.parent
        
        if y.parent == self.NIL:
            self.root = x
        elif y == y.parent.right:
            y.parent.right = x
        else:
            y.parent.left = x
        
        x.right = y
        y.parent = x

    def delete(self, key):
        """Delete a key from the tree. Silently ignores if key doesn't exist."""
        # Find the node to delete
        z = self.root
        while z != self.NIL:
            if key == z.key:
                break
            elif key < z.key:
                z = z.left
            else:
                z = z.right
        
        if z == self.NIL:
            return  # Key not found, no-op
        
        y = z
        y_original_color = y.color
        
        if z.left == self.NIL:
            # Case: z has no left child
            x = z.right
            self._transplant(z, z.right)
        elif z.right == self.NIL:
            # Case: z has left child but no right child
            x = z.left
            self._transplant(z, z.left)
        else:
            # Case: z has two children — find in-order successor y
            y = self._minimum(z.right)
            y_original_color = y.color   # reset: fixup depends on successor's original colour
            x = y.right

            if y.parent == z:
                # y is direct child of z — x stays in place, just update its parent
                x.parent = y   # always update, even when x is NIL (fixup needs NIL.parent)
                y.parent = z.parent
                if z.parent == self.NIL:
                    self.root = y
                elif z == z.parent.left:
                    z.parent.left = y
                else:
                    z.parent.right = y
                y.left = z.left
                y.left.parent = y
                y.color = z.color
            else:
                # y is deeper
                self._transplant(y, y.right)
                y.right = z.right
                y.right.parent = y
                self._transplant(z, y)
                y.left = z.left
                y.left.parent = y
                y.color = z.color
        
        # In the two-children case, we copy z's color to y.
        # If z was RED, we don't need fixup even if y (as successor) was BLACK.
        # Only run fixup if we actually deleted a BLACK node.
        if y_original_color == BLACK:
            self._delete_fixup(x)

    def _delete_fixup(self, node):
        """Fix Red-Black tree properties after deletion."""
        while node != self.root and node.color == BLACK:
            if node == node.parent.left:
                sibling = node.parent.right
                
                # Case 1: Sibling is RED
                if sibling.color == RED:
                    sibling.color = BLACK
                    node.parent.color = RED
                    self._left_rotate(node.parent)
                    sibling = node.parent.right
                
                # Case 2: Sibling is BLACK and both children are BLACK
                if sibling.left.color == BLACK and sibling.right.color == BLACK:
                    # Only set sibling color if sibling is not NIL
                    if sibling != self.NIL:
                        sibling.color = RED
                    node = node.parent
                else:
                    # Case 3: Sibling is BLACK, left child is RED, right child is BLACK
                    if sibling.right.color == BLACK:
                        # Only modify sibling if it's not NIL
                        if sibling.left != self.NIL:
                            sibling.left.color = BLACK
                        if sibling != self.NIL:
                            sibling.color = RED
                        self._right_rotate(sibling)
                        sibling = node.parent.right
                    
                    # Case 4: Sibling is BLACK and right child is RED
                    if sibling != self.NIL:
                        sibling.color = node.parent.color
                    node.parent.color = BLACK
                    if sibling.right != self.NIL:
                        sibling.right.color = BLACK
                    self._left_rotate(node.parent)
                    node = self.root
            else:
                sibling = node.parent.left
                
                # Case 1: Sibling is RED
                if sibling.color == RED:
                    sibling.color = BLACK
                    node.parent.color = RED
                    self._right_rotate(node.parent)
                    sibling = node.parent.left
                
                # Case 2: Sibling is BLACK and both children are BLACK
                if sibling.left.color == BLACK and sibling.right.color == BLACK:
                    # Only set sibling color if sibling is not NIL
                    if sibling != self.NIL:
                        sibling.color = RED
                    node = node.parent
                else:
                    # Case 3: Sibling is BLACK, right child is RED, left child is BLACK
                    if sibling.left.color == BLACK:
                        # Only modify sibling if it's not NIL
                        if sibling.right != self.NIL:
                            sibling.right.color = BLACK
                        if sibling != self.NIL:
                            sibling.color = RED
                        self._left_rotate(sibling)
                        sibling = node.parent.left
                    
                    # Case 4: Sibling is BLACK and left child is RED
                    if sibling != self.NIL:
                        sibling.color = node.parent.color
                    node.parent.color = BLACK
                    if sibling.left != self.NIL:
                        sibling.left.color = BLACK
                    self._right_rotate(node.parent)
                    node = self.root
        
        node.color = BLACK

    def _transplant(self, u, v):
        """Replace subtree rooted at u with subtree rooted at v."""
        if u.parent == self.NIL:
            self.root = v
        elif u == u.parent.left:
            u.parent.left = v
        else:
            u.parent.right = v
        
        v.parent = u.parent

    def _minimum(self, node):
        """Find the minimum node in the subtree rooted at node."""
        while node.left != self.NIL:
            node = node.left
        return node
