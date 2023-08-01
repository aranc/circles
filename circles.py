import tkinter as tk
import tkinter.filedialog
import re, os, sys, json
from copy import deepcopy

FILEOPENOPTIONS = dict(defaultextension='.json',
                  filetypes=[('Bin file','*.json')])

RADIUS = 10

class GraphState:
    def __init__(self):
        self.nodes = []
        self.edges = []
        self.states = {}

    def to_json(self):
        return json.dumps({
            'nodes': list(self.nodes),
            'edges': list(self.edges),
            'states': list(self.states.items())
        })

    def from_json(self, json_string):
        data = json.loads(json_string)
        self.nodes = [tuple(node) for node in data['nodes']]
        self.edges = [tuple([tuple(edge[0]), tuple(edge[1])]) for edge in data['edges']]
        self.states = dict({tuple(node): state for node, state in data['states']})

    def get_node(self, x, y):
        for node in self.nodes:
            nx, ny = node
            if (x-nx)**2 + (y-ny)**2 <= RADIUS**2:
                return node
        return None

    def is_clear(self, x, y):
        for node in self.nodes:
            nx, ny = node
            # x, y is a circle with radius RADIUS
            # nx, ny is circle with radius RADIUS
            # Do they intersect?
            if (x-nx)**2 + (y-ny)**2 <= 4*RADIUS**2:
                return False
        return True

    def update_node(self, x_old, y_old, x_new, y_new):
        if (x_old, y_old) not in self.nodes:
            return False

        self.nodes.remove((x_old, y_old))
        self.nodes.append((x_new, y_new))
        self.states[(x_new, y_new)] = self.states[(x_old, y_old)]
        del self.states[(x_old, y_old)]
        for idx, edge in enumerate(self.edges):
            if (x_old, y_old) == edge[0]:
                self.edges[idx] = ((x_new, y_new), edge[1])
            if (x_old, y_old) == edge[1]:
                self.edges[idx] = (edge[0], (x_new, y_new))
        return True
    
    def remove_node(self, x, y):
        if (x, y) not in self.nodes:
            return False

        self.nodes.remove((x, y))
        del self.states[(x, y)]
        for edge in deepcopy(self.edges):
            if (x, y) == edge[0] or (x, y) == edge[1]:
                self.edges.remove(edge)
        return True

    def add_edge(self, x1, y1, x2, y2):
        if (x1, y1) not in self.nodes or (x2, y2) not in self.nodes:
            return False

        self.edges.append(((x1, y1), (x2, y2)))
        return True

    def remove_edge(self, x1, y1, x2, y2):
        if ((x1, y1), (x2, y2)) in self.edges:
            self.edges.remove(((x1, y1), (x2, y2)))

        if ((x2, y2), (x1, y1)) in self.edges:
            self.edges.remove(((x2, y2), (x1, y1)))

    def is_edge(self, x1, y1, x2, y2):
        return ((x1, y1), (x2, y2)) in self.edges or ((x2, y2), (x1, y1)) in self.edges

    def is_point_near_this_edge(self, x, y, x1, y1, x2, y2):
        # x1, y1 is the start of the edge
        # x2, y2 is the end of the edge
        # x, y is the point

        # calc the distance of the point from the edge
        # https://en.wikipedia.org/wiki/Distance_from_a_point_to_a_line
        #d = |(x2-x1)(y1-y)-(x1-x)(y2-y1)| / sqrt((x2-x1)^2 + (y2-y1)^2)
        d = abs((x2-x1)*(y1-y)-(x1-x)*(y2-y1)) / ((x2-x1)**2 + (y2-y1)**2)**0.5
        return d <= RADIUS

    def remove_unconnected_edges(self):
        # Sort and remove duplicates
        edges = []
        for edge in self.edges:
            edge = sorted(edge)
            if edge not in edges:
                edges.append(edge)

        self.edges = list(sorted(edges))

        for edge in deepcopy(self.edges):
            if edge[0] not in self.nodes or edge[1] not in self.nodes:
                self.edges.remove(edge)

class GraphTool:
    def __init__(self, master):
        self.master = master
        self.canvas = tk.Canvas(self.master, width=800, height=600)
        self.canvas.pack()

        self.circles = []
        self.edges = []
        self.current_circle_to_move = None
        self.dragging = False

        self.canvas.bind("<Button-1>", self.click)

        self.graph = GraphState()
        self.last_good_known_state = deepcopy(self.graph)
        self.current_circle_to_move = None
        self.current_circle_to_connect = None
        self.last_connection_candidate_for_dest = None

        # Add a save / load / clear buttons
        self.save_button = tk.Button(self.master, text="Save", command=self.save)
        self.save_button.pack(side=tk.LEFT)
        self.load_button = tk.Button(self.master, text="Load", command=self.load)
        self.load_button.pack(side=tk.LEFT)
        self.remove_all_button = tk.Button(self.master, text="Remove All", command=self.remove_all)
        self.remove_all_button.pack(side=tk.LEFT)
        self.reset_button = tk.Button(self.master, text="Reset", command=self.reset_states)
        self.reset_button.pack(side=tk.LEFT)

        # Toggalable edit mode
        self.edit_mode = True
        # Add a checkbox to toggle edit mode
        # Also allow to toggle edit mode with the 'E' key
        self.edit_mode_var = tk.IntVar()
        self.edit_mode_var.set(1)
        self.edit_mode_checkbox = tk.Checkbutton(self.master, text="[E]dit Mode", variable=self.edit_mode_var, command=self.toggle_edit_mode)
        self.edit_mode_checkbox.pack(side=tk.LEFT)
        self.master.bind("e", lambda event: self.toggle_edit_mode_keyboard())

        self.update_bindings()

    def bind_double_click_and_drag_and_right_click(self):
        self.canvas.bind("<B1-Motion>", self.move)
        self.canvas.bind("<Double-Button-1>", self.double_click)
        self.canvas.bind("<Button-3>", self.right_click)
        self.canvas.bind("<ButtonRelease-1>", self.release)

    def unbind_double_click_and_drag_and_right_click(self):
        self.canvas.unbind("<B1-Motion>")
        self.canvas.unbind("<Double-Button-1>")
        self.canvas.unbind("<Button-3>")
        self.canvas.unbind("<ButtonRelease-1>")

    def update_bindings(self):
        if self.edit_mode:
            self.bind_double_click_and_drag_and_right_click()
        else:
            self.unbind_double_click_and_drag_and_right_click()

    def toggle_edit_mode(self):
        self.edit_mode = self.edit_mode_var.get()
        self.update_bindings()

    def toggle_edit_mode_keyboard(self):
        self.edit_mode = not self.edit_mode
        self.edit_mode_var.set(int(self.edit_mode))
        self.update_bindings()

    def remove_all(self):
        self.graph = GraphState()
        self.draw_graph()

    def reset_states(self):
        all_are_reset = True
        for node in self.graph.nodes:
            if self.graph.states[node]:
                all_are_reset = False
                break

        if not all_are_reset:
            for node in self.graph.nodes:
                self.graph.states[node] = False
        else:
            for node in self.graph.nodes:
                self.graph.states[node] = True

        self.draw_graph()

    def draw_graph(self):
        self.graph.remove_unconnected_edges()
        try:
            self.canvas.delete("all")
            for node in self.graph.nodes:
                x, y = node
                fill = "black" if self.graph.states[node] else "white"
                circle = self.canvas.create_oval(x-RADIUS, y-RADIUS, x+RADIUS, y+RADIUS, fill=fill)
                self.circles.append(circle)
            for edge in self.graph.edges:
                self.canvas.create_line(*edge, fill="black", width=1)
        except:
            self.graph = deepcopy(self.last_good_known_state)
            self.draw_graph()

    def save(self):
        # Open a dialog box asking for the filename to save
        filename = tk.filedialog.asksaveasfilename(**FILEOPENOPTIONS)
        # Save the graph to the file
        print("Saving to", filename)
        with open(filename, 'w') as f:
            f.write(self.graph.to_json())
        print("json:", self.graph.to_json())
    
    def load(self):
        # Open a dialog box asking for the filename to load
        filename = tk.filedialog.askopenfilename(**FILEOPENOPTIONS)
        # Load the graph from the file
        with open(filename, 'r') as f:
            self.graph.from_json(f.read())
        self.draw_graph()

    def click(self, event):
        self.current_circle_to_move = None
        self.current_circle_to_connect = None
        self.last_connection_candidate_for_dest = None

        x, y = event.x, event.y

        if not self.edit_mode:
            node = self.graph.get_node(x, y)
            if node:
                self.graph.states[node] = not self.graph.states[node]
                for edge in self.graph.edges:
                    if node == edge[0]:
                        self.graph.states[edge[1]] = not self.graph.states[edge[1]]
                    elif node == edge[1]:
                        self.graph.states[edge[0]] = not self.graph.states[edge[0]]
                        
                self.draw_graph()
            return

        node = self.graph.get_node(x, y)
        if node:
            self.current_circle_to_connect = node
            return

        if not self.graph.is_clear(x, y):
            return

        self.graph.nodes.append((x, y))
        self.graph.states[(x, y)] = False
        self.draw_graph()

    def move(self, event):
        if self.current_circle_to_move is not None:
            self.current_circle_to_connect = None
            self.last_connection_candidate_for_dest = None
            return self.move_circle(event)

        if self.current_circle_to_connect is not None:
            return self.connect_circle(event)

    def move_circle(self, event):
        self.last_good_known_state = deepcopy(self.graph)

        ok = self.graph.update_node(self.current_circle_to_move[0], self.current_circle_to_move[1], event.x, event.y)
        if not ok:
            self.current_circle_to_move = None
        else:
            self.current_circle_to_move = (event.x, event.y)

        self.draw_graph()

    def connect_circle(self, event):
        self.draw_graph()
        # Draw an additional line to show the connection
        self.canvas.create_line(self.current_circle_to_connect[0], self.current_circle_to_connect[1], event.x, event.y, fill="black")
        self.last_connection_candidate_for_dest = (event.x, event.y)

    def double_click(self, event):
        self.current_circle_to_move = None
        self.current_circle_to_connect = None
        self.last_connection_candidate_for_dest = None

        node = self.graph.get_node(event.x, event.y)
        if node:
            self.current_circle_to_move = node

    def release(self, event):
        if self.current_circle_to_connect is not None and self.last_connection_candidate_for_dest is not None:
            node = self.graph.get_node(*self.last_connection_candidate_for_dest)
            self.last_connection_candidate_for_dest = None
            if node is None:
                self.draw_graph()
                return
            self.graph.add_edge(*self.current_circle_to_connect, *node)
            self.draw_graph()

    def right_click(self, event):
        node = self.graph.get_node(event.x, event.y)
        if node:
            self.graph.remove_node(*node)
            self.draw_graph()
            return

        for edge in self.graph.edges:
            if self.graph.is_point_near_this_edge(event.x, event.y, edge[0][0], edge[0][1], edge[1][0], edge[1][1]):
                self.graph.remove_edge(edge[0][0], edge[0][1], edge[1][0], edge[1][1])
                self.draw_graph()
                return

print("Click to add a node, drag to connect it")
print("Double click on a node to drag and move it.")
print("Right click on a node or an edge to remove it.")
print("Press 'E' to toggle edit mode.")
root = tk.Tk()
app = GraphTool(root)
root.mainloop()
