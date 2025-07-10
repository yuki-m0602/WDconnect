import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from logic import CompactWirelessDebugTool

def run_app():
    root = tk.Tk()
    app = CompactWirelessDebugTool(root)
    root.mainloop() 