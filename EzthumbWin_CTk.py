import os
import sys
import json
import math
import shutil
import subprocess
import tempfile
import winreg
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk
from concurrent.futures import ThreadPoolExecutor
from pymediainfo import MediaInfo
from tkinterdnd2 import TkinterDnD, DND_FILES

# Safe CREATE_NO_WINDOW flag for Windows subprocesses
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# AppData Path for settings persistence
SETTINGS_DIR = os.path.join(os.environ.get("APPDATA", ""), "EzthumbModern")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

# Win32 Drag and Drop Constants & Subclassing helpers
WM_DROPFILES = 0x0233
GWL_WNDPROC = -4

if sys.platform == "win32":
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32

    shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
    shell32.DragAcceptFiles.restype = None

    shell32.DragQueryFileW.argtypes = [wintypes.WPARAM, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    shell32.DragQueryFileW.restype = wintypes.UINT

    shell32.DragFinish.argtypes = [wintypes.WPARAM]
    shell32.DragFinish.restype = None

    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallWindowProcW.restype = ctypes.c_int64

    if hasattr(user32, 'GetWindowLongPtrW'):
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongPtrW.restype = ctypes.c_void_p
        GetWindowLongPtr = user32.GetWindowLongPtrW
    else:
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = ctypes.c_void_p
        GetWindowLongPtr = user32.GetWindowLongW

    if hasattr(user32, 'SetWindowLongPtrW'):
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        SetWindowLongPtr = user32.SetWindowLongPtrW
    else:
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        user32.SetWindowLongW.restype = ctypes.c_void_p
        SetWindowLongPtr = user32.SetWindowLongW

    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_int64, ctypes.wintypes.HWND, ctypes.wintypes.UINT, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
else:
    CallWindowProc = None
    SetWindowLongPtr = None
    GetWindowLongPtr = None
    WNDPROC = None

# Custom CTkSpinbox Helper Class
class CTkSpinbox(ctk.CTkFrame):
    def __init__(self, parent, from_, to, width=50, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.from_ = from_
        self.to = to
        
        self.btn_minus = ctk.CTkButton(self, text="-", width=25, height=25, font=("Segoe UI", 12, "bold"), fg_color="#27272a", text_color="#fafafa", hover_color="#3f3f46")
        self.btn_minus.pack(side="left")
        self.btn_minus.configure(command=self.decrement)
        
        self.entry = ctk.CTkEntry(self, width=width, height=25, justify="center", font=("Segoe UI", 10), fg_color="#09090b", border_color="#27272a", text_color="#fafafa")
        self.entry.pack(side="left", padx=5)
        
        self.btn_plus = ctk.CTkButton(self, text="+", width=25, height=25, font=("Segoe UI", 12, "bold"), fg_color="#27272a", text_color="#fafafa", hover_color="#3f3f46")
        self.btn_plus.pack(side="left")
        self.btn_plus.configure(command=self.increment)
        
    def get(self):
        return self.entry.get()
        
    def delete(self, start, end):
        self.entry.delete(start, end)
        
    def insert(self, index, string):
        self.entry.insert(index, string)
        
    def decrement(self):
        try:
            val = int(self.entry.get())
            if val > self.from_:
                self.entry.delete(0, "end")
                self.entry.insert(0, str(val - 1))
        except ValueError:
            pass
            
    def increment(self):
        try:
            val = int(self.entry.get())
            if val < self.to:
                self.entry.delete(0, "end")
                self.entry.insert(0, str(val + 1))
        except ValueError:
            pass

class EzthumbCTkApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Ezthumb Modern (CustomTkinter)")
        self.geometry("917x617")
        
        # Style Properties
        self.bg_color = "#121214"
        self.widget_bg = "#09090b"
        self.text_color = "#fafafa"
        self.accent_color = "#38bdf8"
        self.border_color = "#27272a"
        
        self.configure(fg_color=self.bg_color)
        self.temp_dir = tempfile.mkdtemp(prefix="ezthumb_modern_")
        
        # State
        self.files_list = []
        self.custom_data = {}
        self.current_preview_video = ""
        self.preview_images = []
        self.copied_frames_layout = None

        # Load system fonts map from Windows registry
        self.fonts_map = self.load_system_fonts_map()
        self.system_font_names = self.get_sorted_system_fonts()

        # Bind close window
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.setup_ui()
        self.load_settings()

        # Drag and Drop native Windows handler setup
        if sys.platform == "win32":
            try:
                TkinterDnD.require(self)
                self.listbox_files.drop_target_register(DND_FILES)
                self.listbox_files.dnd_bind("<<Drop>>", self.handle_dropfiles_dnd)
            except Exception as e:
                print("Failed to setup tkinterdnd2:", e)

    def load_system_fonts_map(self):
        fonts = {}
        if sys.platform != "win32":
            return fonts
        try:
            reg_keys = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
            ]
            for root_hkey, path in reg_keys:
                try:
                    with winreg.OpenKey(root_hkey, path) as key:
                        info = winreg.QueryInfoKey(key)
                        for i in range(info[1]):
                            name, val, _ = winreg.EnumValue(key, i)
                            fam = name.split(" & ")[0].split(" (TrueType)")[0].strip().lower()
                            fonts[fam] = val
                except OSError:
                    pass
        except Exception:
            pass
        return fonts

    def get_sorted_system_fonts(self):
        standard = ["Arial", "Comic Sans MS", "Consolas", "Courier New", "Georgia", "Impact", "Lucida Console", "Segoe UI", "Tahoma", "Times New Roman", "Trebuchet MS", "Verdana"]
        found = []
        for name in standard:
            if name.lower() in self.fonts_map:
                found.append(name)
        if not found:
            found = ["Arial"]
        return sorted(found)

    def setup_ui(self):
        # Configure Tabview widget
        self.tabview = ctk.CTkTabview(
            self,
            segmented_button_selected_color=self.accent_color,
            segmented_button_selected_hover_color="#0ea5e9",
            segmented_button_unselected_color="#27272a",
            text_color=self.text_color
        )
        self.tabview.pack(fill="both", expand=True, padx=15, pady=15)
        
        self.tab_generate = self.tabview.add(" Generate ")
        self.tab_setup = self.tabview.add(" Setup ")
        self.tab_edit = self.tabview.add(" Edit Frames & Header ")
        self.tab_about = self.tabview.add(" About ")

        self.build_generate_tab()
        self.build_setup_tab()
        self.build_edit_tab()
        self.build_about_tab()

    # --- TAB 1: GENERATE (MEDIA LIST) ---
    def build_generate_tab(self):
        main_lbl = ctk.CTkLabel(self.tab_generate, text="Media Files:", font=("Segoe UI", 12, "bold"), text_color=self.text_color)
        main_lbl.pack(anchor="w", padx=15, pady=(15, 5))

        list_frame = ctk.CTkFrame(self.tab_generate, fg_color="transparent")
        list_frame.pack(fill="both", expand=True, padx=15, pady=5)

        self.listbox_files = tk.Listbox(
            list_frame,
            bg=self.widget_bg,
            fg=self.text_color,
            selectbackground=self.accent_color,
            selectforeground="black",
            font=("Segoe UI", 10),
            bd=1,
            relief="solid",
            highlightthickness=0
        )
        self.listbox_files.pack(side="left", fill="both", expand=True)

        list_scroll = ctk.CTkScrollbar(list_frame, command=self.listbox_files.yview)
        list_scroll.pack(side="left", fill="y", padx=(5, 0))
        self.listbox_files.configure(yscrollcommand=list_scroll.set)

        btn_frame = ctk.CTkFrame(list_frame, fg_color="transparent")
        btn_frame.pack(side="left", fill="y", padx=(15, 0))

        btn_add = ctk.CTkButton(btn_frame, text="Add Files...", command=self.add_media_files, font=("Segoe UI", 10, "bold"), fg_color="#27272a", text_color=self.text_color, hover_color="#3f3f46", width=120)
        btn_add.pack(pady=5)

        btn_remove = ctk.CTkButton(btn_frame, text="Remove", command=self.remove_media_file, font=("Segoe UI", 10, "bold"), fg_color="#ef4444", text_color="white", hover_color="#dc2626", width=120)
        btn_remove.pack(pady=5)

        btn_clear = ctk.CTkButton(btn_frame, text="Clear List", command=self.clear_media_list, font=("Segoe UI", 10, "bold"), fg_color="#27272a", text_color=self.text_color, hover_color="#3f3f46", width=120)
        btn_clear.pack(pady=5)

        # Output save directory
        odir_frame = ctk.CTkFrame(self.tab_generate, fg_color="#18181b", border_color=self.border_color, border_width=1)
        odir_frame.pack(fill="x", padx=15, pady=15)
        
        odir_title = ctk.CTkLabel(odir_frame, text=" Save To Directory ", font=("Segoe UI", 11, "bold"), text_color=self.accent_color)
        odir_title.pack(anchor="w", padx=15, pady=(10, 5))

        self.var_same_dir = tk.BooleanVar(value=True)
        chk_same = ctk.CTkCheckBox(odir_frame, text="Same directory as video file", variable=self.var_same_dir, command=self.toggle_output_dir_widgets, font=("Segoe UI", 10), text_color=self.text_color, fg_color=self.accent_color, hover_color="#0ea5e9")
        chk_same.pack(anchor="w", padx=15, pady=5)

        dir_sel_frame = ctk.CTkFrame(odir_frame, fg_color="transparent")
        dir_sel_frame.pack(fill="x", padx=15, pady=(5, 15))

        self.ent_output_dir = ctk.CTkEntry(dir_sel_frame, font=("Segoe UI", 10), fg_color=self.widget_bg, border_color=self.border_color, text_color=self.text_color)
        self.ent_output_dir.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.btn_browse_dir = ctk.CTkButton(dir_sel_frame, text="Browse...", command=self.browse_output_dir, font=("Segoe UI", 10, "bold"), fg_color="#27272a", text_color=self.text_color, hover_color="#3f3f46", width=100)
        self.btn_browse_dir.pack(side="left")

        self.btn_run = ctk.CTkButton(
            self.tab_generate,
            text="RUN (Generate Contact Sheets)",
            command=self.run_process_all,
            font=("Segoe UI", 13, "bold"),
            fg_color="#16a34a",
            hover_color="#15803d",
            text_color="white",
            height=45
        )
        self.btn_run.pack(fill="x", padx=15, pady=(0, 15))

    # --- TAB 2: SETUP (LAYOUT OPTIONS) ---
    def build_setup_tab(self):
        # Create a scrollable container for the entire setup tab to prevent layout cutting on small resolutions
        scroll_container = ctk.CTkScrollableFrame(self.tab_setup, fg_color="transparent")
        scroll_container.pack(fill="both", expand=True, padx=5, pady=5)

        settings_container = ctk.CTkFrame(scroll_container, fg_color="transparent")
        settings_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Panel Left: Dimensions & Grid
        p_left = ctk.CTkFrame(settings_container, fg_color="#18181b", border_color=self.border_color, border_width=1)
        p_left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        p_left_title = ctk.CTkLabel(p_left, text=" Dimensions & Grid ", font=("Segoe UI", 12, "bold"), text_color=self.accent_color)
        p_left_title.pack(anchor="w", padx=15, pady=(10, 5))
        
        grid_frame = ctk.CTkFrame(p_left, fg_color="transparent")
        grid_frame.pack(fill="both", expand=True, padx=15, pady=5)

        # Row 0: Cols
        lbl_cols = ctk.CTkLabel(grid_frame, text="Grid Columns:", font=("Segoe UI", 10), text_color=self.text_color)
        lbl_cols.grid(row=0, column=0, sticky="w", pady=8)
        self.spin_cols = CTkSpinbox(grid_frame, from_=1, to=30)
        self.spin_cols.grid(row=0, column=1, sticky="w", pady=8, padx=10)

        # Row 1: Rows
        lbl_rows = ctk.CTkLabel(grid_frame, text="Grid Rows:", font=("Segoe UI", 10), text_color=self.text_color)
        lbl_rows.grid(row=1, column=0, sticky="w", pady=8)
        self.spin_rows = CTkSpinbox(grid_frame, from_=1, to=50)
        self.spin_rows.grid(row=1, column=1, sticky="w", pady=8, padx=10)

        # Row 2: Auto size mode
        self.var_auto_size = tk.BooleanVar(value=True)
        chk_auto = ctk.CTkCheckBox(grid_frame, text="Auto Thumbnail Size", variable=self.var_auto_size, command=self.toggle_size_mode_fields, font=("Segoe UI", 10), text_color=self.text_color, fg_color=self.accent_color)
        chk_auto.grid(row=2, column=0, columnspan=2, sticky="w", pady=8)

        # Row 3: Canvas Profile
        self.profile_lbl_widget = ctk.CTkLabel(grid_frame, text="Canvas Profile:", font=("Segoe UI", 10), text_color=self.text_color)
        self.profile_lbl_widget.grid(row=3, column=0, sticky="w", pady=8)
        
        self.cb_profile = ctk.CTkComboBox(grid_frame, values=["Auto (Video size)", "HD 1080p (1920px)", "HD 720p (1280px)", "SD 480p (854px)", "Custom Width"], font=("Segoe UI", 10), command=self.toggle_profile_width_field, width=160)
        self.cb_profile.grid(row=3, column=1, columnspan=2, sticky="w", pady=8, padx=10)

        # Row 4: Custom Canvas Width
        self.width_lbl_widget = ctk.CTkLabel(grid_frame, text="Canvas Width (px):", font=("Segoe UI", 10), text_color=self.text_color)
        self.width_lbl_widget.grid(row=4, column=0, sticky="w", pady=8)
        
        self.ent_width = ctk.CTkEntry(grid_frame, width=100, font=("Segoe UI", 10), fg_color=self.widget_bg, border_color=self.border_color, text_color=self.text_color)
        self.ent_width.grid(row=4, column=1, columnspan=2, sticky="w", pady=8, padx=10)

        # Row 5: Fixed Thumbnail W
        self.lbl_thumb_w = ctk.CTkLabel(grid_frame, text="Thumb Width (px):", font=("Segoe UI", 10), text_color=self.text_color)
        self.lbl_thumb_w.grid(row=5, column=0, sticky="w", pady=8)
        self.ent_thumb_w = ctk.CTkEntry(grid_frame, width=80, font=("Segoe UI", 10), fg_color=self.widget_bg, border_color=self.border_color, text_color=self.text_color)
        self.ent_thumb_w.grid(row=5, column=1, sticky="w", pady=8, padx=10)

        # Row 6: Fixed Thumbnail H
        self.lbl_thumb_h = ctk.CTkLabel(grid_frame, text="Thumb Height (px):", font=("Segoe UI", 10), text_color=self.text_color)
        self.lbl_thumb_h.grid(row=6, column=0, sticky="w", pady=8)
        self.ent_thumb_h = ctk.CTkEntry(grid_frame, width=80, font=("Segoe UI", 10), fg_color=self.widget_bg, border_color=self.border_color, text_color=self.text_color)
        self.ent_thumb_h.grid(row=6, column=1, sticky="w", pady=8, padx=10)

        # Row 7: Gap size
        gap_lbl = ctk.CTkLabel(grid_frame, text="Grid Gap Size (px):", font=("Segoe UI", 10), text_color=self.text_color)
        gap_lbl.grid(row=7, column=0, sticky="w", pady=8)
        self.spin_gap = CTkSpinbox(grid_frame, from_=0, to=30)
        self.spin_gap.grid(row=7, column=1, sticky="w", pady=8, padx=10)

        # Row 8: Margin size
        margin_lbl = ctk.CTkLabel(grid_frame, text="Outer Margin (px):", font=("Segoe UI", 10), text_color=self.text_color)
        margin_lbl.grid(row=8, column=0, sticky="w", pady=8)
        self.spin_margin = CTkSpinbox(grid_frame, from_=0, to=50)
        self.spin_margin.grid(row=8, column=1, sticky="w", pady=8, padx=10)

        # Row 9: Suffix
        suf_lbl = ctk.CTkLabel(grid_frame, text="Output Suffix:", font=("Segoe UI", 10), text_color=self.text_color)
        suf_lbl.grid(row=9, column=0, sticky="w", pady=8)
        self.ent_suffix = ctk.CTkEntry(grid_frame, width=100, font=("Segoe UI", 10), fg_color=self.widget_bg, border_color=self.border_color, text_color=self.text_color)
        self.ent_suffix.grid(row=9, column=1, columnspan=2, sticky="w", pady=8, padx=10)

        # Panel Right: Fonts, Colors & Formats
        p_right = ctk.CTkFrame(settings_container, fg_color="#18181b", border_color=self.border_color, border_width=1)
        p_right.pack(side="left", fill="both", expand=True)
        
        p_right_title = ctk.CTkLabel(p_right, text=" Fonts, Colors & Formats ", font=("Segoe UI", 12, "bold"), text_color=self.accent_color)
        p_right_title.pack(anchor="w", padx=15, pady=(10, 5))
        
        fonts_frame = ctk.CTkFrame(p_right, fg_color="transparent")
        fonts_frame.pack(fill="both", expand=True, padx=15, pady=5)

        # Font Family
        font_lbl = ctk.CTkLabel(fonts_frame, text="Font Family:", font=("Segoe UI", 10), text_color=self.text_color)
        font_lbl.grid(row=0, column=0, sticky="w", pady=8)
        
        self.cb_font = ctk.CTkComboBox(fonts_frame, values=self.system_font_names, font=("Segoe UI", 10), width=180)
        self.cb_font.grid(row=0, column=1, sticky="w", pady=8, padx=10)

        # Font Style
        style_lbl = ctk.CTkLabel(fonts_frame, text="Font Style:", font=("Segoe UI", 10), text_color=self.text_color)
        style_lbl.grid(row=1, column=0, sticky="w", pady=8)
        self.cb_font_style = ctk.CTkComboBox(fonts_frame, values=["Regular", "Bold", "Italic", "Bold Italic"], font=("Segoe UI", 10), width=120)
        self.cb_font_style.grid(row=1, column=1, sticky="w", pady=8, padx=10)

        # Header Font Size
        size_lbl = ctk.CTkLabel(fonts_frame, text="Header Font Size:", font=("Segoe UI", 10), text_color=self.text_color)
        size_lbl.grid(row=2, column=0, sticky="w", pady=8)
        self.spin_font_size = CTkSpinbox(fonts_frame, from_=6, to=40)
        self.spin_font_size.grid(row=2, column=1, sticky="w", pady=8, padx=10)

        # Time Font Size
        time_size_lbl = ctk.CTkLabel(fonts_frame, text="Timestamp Font Size:", font=("Segoe UI", 10), text_color=self.text_color)
        time_size_lbl.grid(row=3, column=0, sticky="w", pady=8)
        self.spin_time_font_size = CTkSpinbox(fonts_frame, from_=6, to=40)
        self.spin_time_font_size.grid(row=3, column=1, sticky="w", pady=8, padx=10)

        # Output Format
        fmt_lbl = ctk.CTkLabel(fonts_frame, text="Output Format:", font=("Segoe UI", 10), text_color=self.text_color)
        fmt_lbl.grid(row=4, column=0, sticky="w", pady=8)
        self.cb_format = ctk.CTkComboBox(fonts_frame, values=["JPEG", "PNG"], font=("Segoe UI", 10), command=self.toggle_quality_widget, width=100)
        self.cb_format.grid(row=4, column=1, sticky="w", pady=8, padx=10)

        # Quality
        self.qual_lbl_widget = ctk.CTkLabel(fonts_frame, text="JPEG Quality (1-100):", font=("Segoe UI", 10), text_color=self.text_color)
        self.qual_lbl_widget.grid(row=5, column=0, sticky="w", pady=8)
        self.spin_quality = CTkSpinbox(fonts_frame, from_=1, to=100)
        self.spin_quality.grid(row=5, column=1, sticky="w", pady=8, padx=10)

        # Existing Files
        ex_lbl = ctk.CTkLabel(fonts_frame, text="If File Existed:", font=("Segoe UI", 10), text_color=self.text_color)
        ex_lbl.grid(row=6, column=0, sticky="w", pady=8)
        self.cb_exist = ctk.CTkComboBox(fonts_frame, values=["Create New (Append number)", "Skip Existed", "Overwrite"], font=("Segoe UI", 10), width=200)
        self.cb_exist.grid(row=6, column=1, sticky="w", pady=8, padx=10)

        # Theme selection
        theme_lbl = ctk.CTkLabel(fonts_frame, text="Contact Sheet Theme:", font=("Segoe UI", 10), text_color=self.text_color)
        theme_lbl.grid(row=7, column=0, sticky="w", pady=8)
        self.cb_theme = ctk.CTkComboBox(fonts_frame, values=["Light (White)", "Dark (Black)"], font=("Segoe UI", 10), width=140)
        self.cb_theme.grid(row=7, column=1, sticky="w", pady=8, padx=10)

        # Option checkboxes
        self.var_time = tk.BooleanVar(value=True)
        self.var_info = tk.BooleanVar(value=True)

        chk_time = ctk.CTkCheckBox(fonts_frame, text="Draw timestamps on thumbs", variable=self.var_time, font=("Segoe UI", 10), text_color=self.text_color, fg_color=self.accent_color)
        chk_time.grid(row=8, column=0, columnspan=2, sticky="w", pady=8)

        chk_info = ctk.CTkCheckBox(fonts_frame, text="Draw header info text", variable=self.var_info, font=("Segoe UI", 10), text_color=self.text_color, fg_color=self.accent_color)
        chk_info.grid(row=9, column=0, columnspan=2, sticky="w", pady=8)

        # Live Preview button
        btn_preview = ctk.CTkButton(
            fonts_frame,
            text="Generate Live Preview Sheet",
            command=self.show_live_preview,
            font=("Segoe UI", 11, "bold"),
            fg_color=self.accent_color,
            hover_color="#0ea5e9",
            text_color="black",
            height=32
        )
        btn_preview.grid(row=10, column=0, columnspan=2, sticky="we", pady=12)

        # Configuration Profiles Manager Frame (at the bottom of setup tab)
        profile_mgr_frame = ctk.CTkFrame(scroll_container, fg_color="#18181b", border_color=self.border_color, border_width=1)
        profile_mgr_frame.pack(fill="x", side="top", padx=15, pady=(15, 10))

        profile_mgr_title = ctk.CTkLabel(profile_mgr_frame, text=" Configuration Profiles Manager ", font=("Segoe UI", 11, "bold"), text_color=self.accent_color)
        profile_mgr_title.pack(anchor="w", padx=15, pady=(10, 5))

        mgr_control_frame = ctk.CTkFrame(profile_mgr_frame, fg_color="transparent")
        mgr_control_frame.pack(fill="x", padx=15, pady=(5, 15))

        lbl_prof = ctk.CTkLabel(mgr_control_frame, text="Active Profile:", font=("Segoe UI", 10, "bold"), text_color=self.text_color)
        lbl_prof.pack(side="left", padx=(0, 5))

        self.cb_config_profiles = ctk.CTkComboBox(mgr_control_frame, values=["Default"], font=("Segoe UI", 10), width=180, command=self.on_config_profile_selected)
        self.cb_config_profiles.pack(side="left", padx=(0, 15))

        btn_save_prof = ctk.CTkButton(mgr_control_frame, text="Save Current Setup as...", command=self.save_new_config_profile, font=("Segoe UI", 10, "bold"), fg_color="#27272a", hover_color="#3f3f46", text_color=self.accent_color, width=180)
        btn_save_prof.pack(side="left", padx=5)

        btn_delete_prof = ctk.CTkButton(mgr_control_frame, text="Delete Profile", command=self.delete_config_profile, font=("Segoe UI", 10, "bold"), fg_color="#27272a", hover_color="#3f3f46", text_color="#f87171", width=120)
        btn_delete_prof.pack(side="left", padx=5)

        # Apply / Cancel button frame at the bottom of setup tab
        setup_btn_frame = ctk.CTkFrame(scroll_container, fg_color="transparent")
        setup_btn_frame.pack(fill="x", side="top", padx=15, pady=15)

        self.lbl_setup_status = ctk.CTkLabel(setup_btn_frame, text="", font=("Segoe UI", 10, "bold"), text_color=self.accent_color)
        self.lbl_setup_status.pack(side="left", padx=10)

        btn_cancel = ctk.CTkButton(setup_btn_frame, text="Cancel / Revert", command=self.cancel_settings_changes, font=("Segoe UI", 11, "bold"), fg_color="#27272a", hover_color="#3f3f46", text_color=self.text_color, width=120, height=35)
        btn_cancel.pack(side="right", padx=10)

        btn_apply = ctk.CTkButton(setup_btn_frame, text="Apply Settings", command=self.apply_settings_changes, font=("Segoe UI", 11, "bold"), fg_color="#16a34a", hover_color="#15803d", text_color="white", width=120, height=35)
        btn_apply.pack(side="right", padx=10)

    # --- TAB 3: EDIT FRAMES & HEADER ---
    def build_edit_tab(self):
        # Row 1: Video selector
        sel_row1 = ctk.CTkFrame(self.tab_edit, fg_color="transparent")
        sel_row1.pack(fill="x", padx=15, pady=(10, 5))

        lbl_select = ctk.CTkLabel(sel_row1, text="Select Video to Edit/Preview:", font=("Segoe UI", 11, "bold"), text_color=self.text_color)
        lbl_select.pack(side="left", padx=(0, 10))

        self.cb_edit_select = ctk.CTkComboBox(sel_row1, values=[], font=("Segoe UI", 10), command=self.on_video_selected_to_edit)
        self.cb_edit_select.pack(side="left", fill="x", expand=True)
        self.cb_edit_select.set("No videos added...")

        # Row 2: Action buttons
        sel_row2 = ctk.CTkFrame(self.tab_edit, fg_color="transparent")
        sel_row2.pack(fill="x", padx=15, pady=(5, 10))

        # Loading status indicator text
        self.lbl_loading_status = ctk.CTkLabel(sel_row2, text="", font=("Segoe UI", 10, "bold"), text_color=self.accent_color)
        self.lbl_loading_status.pack(side="left", padx=10)

        # Restablecer / Reset Button on the Edit tab
        btn_reset_video = ctk.CTkButton(
            sel_row2,
            text="Restablecer Video",
            command=self.reset_current_video_data,
            fg_color="#27272a",
            text_color="#f87171",
            hover_color="#ef4444",
            font=("Segoe UI", 10, "bold"),
            width=130
        )
        btn_reset_video.pack(side="right", padx=5)

        # Copy / Paste Frames Buttons
        btn_paste_frames = ctk.CTkButton(
            sel_row2,
            text="Paste Frames Layout",
            command=self.paste_frames_layout,
            fg_color="#27272a",
            text_color=self.accent_color,
            hover_color="#0ea5e9",
            font=("Segoe UI", 10, "bold"),
            width=140
        )
        btn_paste_frames.pack(side="right", padx=5)

        btn_copy_frames = ctk.CTkButton(
            sel_row2,
            text="Copy Frames Layout",
            command=self.copy_frames_layout,
            fg_color="#27272a",
            text_color=self.accent_color,
            hover_color="#0ea5e9",
            font=("Segoe UI", 10, "bold"),
            width=140
        )
        btn_copy_frames.pack(side="right", padx=5)

        split_frame = ctk.CTkFrame(self.tab_edit, fg_color="transparent")
        split_frame.pack(fill="both", expand=True, padx=15, pady=5)

        # Header custom editor panel
        header_frame = ctk.CTkFrame(split_frame, fg_color="#18181b", border_color=self.border_color, border_width=1, width=280)
        header_frame.pack(side="left", fill="y", padx=(0, 10))
        header_frame.pack_propagate(False)

        header_lbl = ctk.CTkLabel(header_frame, text=" Custom Header Text ", font=("Segoe UI", 11, "bold"), text_color=self.accent_color)
        header_lbl.pack(anchor="w", padx=15, pady=(10, 5))

        self.txt_header = tk.Text(header_frame, bg=self.widget_bg, fg=self.text_color, font=("Consolas", 9), bd=0, insertbackground="white")
        self.txt_header.pack(fill="both", expand=True, padx=10, pady=(5, 10))
        self.txt_header.bind("<KeyRelease>", self.on_header_text_edited)

        # Frames list / Grid container using Scrollable Frame!
        preview_container = ctk.CTkFrame(split_frame, fg_color="#18181b", border_color=self.border_color, border_width=1)
        preview_container.pack(side="left", fill="both", expand=True)

        preview_title = ctk.CTkLabel(preview_container, text=" Frames Grid (Check to include, Set to seek) ", font=("Segoe UI", 11, "bold"), text_color=self.accent_color)
        preview_title.pack(anchor="w", padx=15, pady=(10, 5))

        self.edit_scroll_frame = ctk.CTkScrollableFrame(preview_container, fg_color="transparent")
        self.edit_scroll_frame.pack(fill="both", expand=True, padx=5, pady=(5, 10))

    # --- TAB 4: ABOUT ---
    def build_about_tab(self):
        about_frame = ctk.CTkFrame(self.tab_about, fg_color="transparent")
        about_frame.pack(expand=True)

        lbl_title = ctk.CTkLabel(about_frame, text="Ezthumb Modern (CustomTkinter)", font=("Segoe UI", 20, "bold"), text_color=self.accent_color)
        lbl_title.pack(pady=10)

        lbl_version = ctk.CTkLabel(about_frame, text="Version 4.0 (CustomTkinter Edition)", font=("Segoe UI", 10, "bold"), text_color="#a1a1aa")
        lbl_version.pack(pady=5)

        desc = (
            "A gorgeous CustomTkinter desktop interface for the classic Ezthumb contact sheet engine.\n"
            "Supports custom metadata editing, frames selection/regenerating, custom fonts, \n"
            "and silent modern FFmpeg 8.1.2 integration.\n\n"
            "Original concept and layout logic by C.S.C.\n"
            "UCRT Compatibility Bridge and CustomTkinter redesign by Google DeepMind (Antigravity)."
        )
        lbl_desc = ctk.CTkLabel(about_frame, text=desc, font=("Segoe UI", 10), text_color="#d4d4d8", justify="center")
        lbl_desc.pack(pady=15)

    # --- UI EVENT HANDLERS & HELPERS ---
    def add_media_files(self):
        self.config(cursor="watch")
        self.update()

        files = filedialog.askopenfilenames(
            filetypes=[("Video files", "*.mp4;*.mkv;*.avi;*.mov;*.flv;*.webm;*.ts;*.m4v")]
        )
        if files:
            for f in files:
                if f not in self.files_list:
                    self.files_list.append(f)
                    self.listbox_files.insert("end", os.path.basename(f))
            self.update_edit_combobox()

        self.config(cursor="")

    def remove_media_file(self):
        sel = self.listbox_files.curselection()
        if sel:
            idx = sel[0]
            video_path = self.files_list[idx]
            self.listbox_files.delete(idx)
            del self.files_list[idx]
            if video_path in self.custom_data:
                del self.custom_data[video_path]
            if self.current_preview_video == video_path:
                self.current_preview_video = ""
                self.txt_header.delete("1.0", "end")
                for child in self.edit_scroll_frame.winfo_children():
                    child.destroy()
            self.update_edit_combobox()

    def clear_media_list(self):
        self.listbox_files.delete(0, "end")
        self.files_list = []
        self.custom_data = {}
        self.current_preview_video = ""
        self.txt_header.delete("1.0", "end")
        for child in self.edit_scroll_frame.winfo_children():
            child.destroy()
        self.update_edit_combobox()

    def browse_output_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.ent_output_dir.configure(state="normal")
            self.ent_output_dir.delete(0, "end")
            self.ent_output_dir.insert(0, os.path.normpath(path))
            self.ent_output_dir.configure(state="disabled")

    def toggle_output_dir_widgets(self):
        if self.var_same_dir.get():
            self.ent_output_dir.configure(state="disabled")
            self.btn_browse_dir.configure(state="disabled")
        else:
            self.ent_output_dir.configure(state="normal")
            self.btn_browse_dir.configure(state="normal")

    def toggle_quality_widget(self, value=None):
        # Combobox command triggers this with select value
        fmt = self.cb_format.get()
        if fmt == "PNG":
            self.spin_quality.btn_minus.configure(state="disabled")
            self.spin_quality.btn_plus.configure(state="disabled")
            self.spin_quality.entry.configure(state="disabled")
            self.qual_lbl_widget.configure(text_color="gray")
        else:
            self.spin_quality.btn_minus.configure(state="normal")
            self.spin_quality.btn_plus.configure(state="normal")
            self.spin_quality.entry.configure(state="normal")
            self.qual_lbl_widget.configure(text_color=self.text_color)

    def toggle_size_mode_fields(self):
        if self.var_auto_size.get():
            self.ent_thumb_w.configure(state="disabled")
            self.ent_thumb_h.configure(state="disabled")
            self.lbl_thumb_w.configure(text_color="gray")
            self.lbl_thumb_h.configure(text_color="gray")
            self.cb_profile.configure(state="readonly")
            self.profile_lbl_widget.configure(text_color=self.text_color)
            self.toggle_profile_width_field(self.cb_profile.get())
        else:
            self.ent_thumb_w.configure(state="normal")
            self.ent_thumb_h.configure(state="normal")
            self.lbl_thumb_w.configure(text_color=self.text_color)
            self.lbl_thumb_h.configure(text_color=self.text_color)
            self.cb_profile.configure(state="disabled")
            self.profile_lbl_widget.configure(text_color="gray")
            self.ent_width.configure(state="disabled")
            self.width_lbl_widget.configure(text_color="gray")

    def toggle_profile_width_field(self, val):
        if "Custom" in val:
            self.ent_width.configure(state="normal")
            self.width_lbl_widget.configure(text_color=self.text_color)
        else:
            self.ent_width.configure(state="normal")
            if "1080p" in val:
                self.ent_width.delete(0, "end")
                self.ent_width.insert(0, "1920")
            elif "720p" in val:
                self.ent_width.delete(0, "end")
                self.ent_width.insert(0, "1280")
            elif "480p" in val:
                self.ent_width.delete(0, "end")
                self.ent_width.insert(0, "854")
            elif "Auto" in val:
                self.ent_width.delete(0, "end")
                self.ent_width.insert(0, "0")
            self.ent_width.configure(state="disabled")
            self.width_lbl_widget.configure(text_color="gray")

    def update_edit_combobox(self):
        names = [os.path.basename(f) for f in self.files_list]
        self.cb_edit_select.configure(values=names)
        if names:
            if not self.cb_edit_select.get() or self.cb_edit_select.get() not in names:
                self.cb_edit_select.set(names[0])
                self.on_video_selected_to_edit(names[0])
        else:
            self.cb_edit_select.set("")

    def on_config_profile_selected(self, val):
        self.current_profile_name = val
        self.apply_profile_values(val)

    def save_new_config_profile(self):
        from tkinter import simpledialog
        name = simpledialog.askstring("Save Profile", "Enter profile name:")
        if name:
            name = name.strip()
            if not name:
                return
            self.current_profile_name = name
            self.save_settings()
            
            self.cb_config_profiles.configure(values=list(self.profiles.keys()))
            self.cb_config_profiles.set(name)
            
            self.lbl_setup_status.configure(text=f"Profile '{name}' saved successfully!")
            self.after(3000, lambda: self.lbl_setup_status.configure(text=""))

    def delete_config_profile(self):
        profile_name = self.cb_config_profiles.get()
        if not profile_name:
            return
        if profile_name == "Default":
            messagebox.showwarning("Warning", "Cannot delete the Default profile.")
            return
            
        if messagebox.askyesno("Delete Profile", f"Are you sure you want to delete profile '{profile_name}'?"):
            if profile_name in self.profiles:
                del self.profiles[profile_name]
                
            self.current_profile_name = "Default"
            self.save_settings()
            
            self.cb_config_profiles.configure(values=list(self.profiles.keys()))
            self.cb_config_profiles.set("Default")
            self.apply_profile_values("Default")
            
            self.lbl_setup_status.configure(text=f"Profile '{profile_name}' deleted.")
            self.after(3000, lambda: self.lbl_setup_status.configure(text=""))

    def copy_frames_layout(self):
        if not self.current_preview_video or self.current_preview_video not in self.custom_data:
            messagebox.showwarning("Warning", "No video selected or frames loaded to copy.")
            return
        
        frames = self.custom_data[self.current_preview_video]["frames"]
        self.copied_frames_layout = [
            {"timestamp": f["timestamp"], "excluded": f["excluded"]} for f in frames
        ]
        messagebox.showinfo("Success", f"Copied layout of {len(frames)} frames to clipboard.")

    def paste_frames_layout(self):
        if not self.current_preview_video:
            messagebox.showwarning("Warning", "Please select a target video to paste frames layout.")
            return
            
        if not self.copied_frames_layout:
            messagebox.showwarning("Warning", "No copied frames layout found. Please Copy first.")
            return
            
        if self.current_preview_video not in self.custom_data:
            self.load_fresh_video_data(self.current_preview_video)
            
        target_data = self.custom_data[self.current_preview_video]
        target_frames = target_data["frames"]
        
        copied_len = len(self.copied_frames_layout)
        for i, f in enumerate(target_frames):
            if i < copied_len:
                f["timestamp"] = self.copied_frames_layout[i]["timestamp"]
                f["excluded"] = self.copied_frames_layout[i]["excluded"]
                
        self.lbl_loading_status.configure(text="Updating frames from clipboard...")
        self.config(cursor="watch")
        self.update()

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for f in target_frames:
                futures.append(executor.submit(self.extract_frame, self.current_preview_video, f["timestamp"], f["temp_path"], 160, 90))
            results = [f.result() for f in futures]

        self.render_edit_frames(target_frames)
        self.lbl_loading_status.configure(text="")
        self.config(cursor="")
        messagebox.showinfo("Success", "Pasted frames layout successfully!")

    def apply_settings_changes(self):
        self.save_settings()
        self.on_grid_size_changed()
        self.lbl_setup_status.configure(text="Settings applied successfully!")
        self.after(3000, lambda: self.lbl_setup_status.configure(text=""))

    def cancel_settings_changes(self):
        self.load_settings()
        self.lbl_setup_status.configure(text="Settings reverted to last saved.")
        self.after(3000, lambda: self.lbl_setup_status.configure(text=""))

    def on_grid_size_changed(self):
        try:
            cols = int(self.spin_cols.get())
            rows = int(self.spin_rows.get())
        except ValueError:
            return
            
        if self.current_preview_video:
            if self.current_preview_video in self.custom_data:
                saved_header = self.txt_header.get("1.0", "end-1c")
                del self.custom_data[self.current_preview_video]
                self.load_fresh_video_data(self.current_preview_video)
                self.custom_data[self.current_preview_video]["header"] = saved_header
                self.txt_header.delete("1.0", "end")
                self.txt_header.insert("1.0", saved_header)

    def reset_current_video_data(self):
        if not self.current_preview_video:
            return
        if messagebox.askyesno("Restablecer Video", "¿Está seguro de que desea restablecer los fotogramas y la cabecera a los valores predeterminados?"):
            if self.current_preview_video in self.custom_data:
                del self.custom_data[self.current_preview_video]
            
            self.lbl_loading_status.configure(text="Restoring defaults...")
            self.config(cursor="watch")
            self.update()
            self.load_fresh_video_data(self.current_preview_video)
            self.lbl_loading_status.configure(text="")
            self.config(cursor="")

    def on_video_selected_to_edit(self, val):
        # combobox trigger returns string value
        filename = self.cb_edit_select.get()
        matched = [f for f in self.files_list if os.path.basename(f) == filename]
        if not matched:
            return
            
        video_path = matched[0]
        self.current_preview_video = video_path

        self.lbl_loading_status.configure(text="Loading frames...")
        self.config(cursor="watch")
        self.update()

        if video_path in self.custom_data:
            data = self.custom_data[video_path]
            self.txt_header.delete("1.0", "end")
            self.txt_header.insert("1.0", data["header"])
            self.render_edit_frames(data["frames"])
        else:
            self.load_fresh_video_data(video_path)

        self.lbl_loading_status.configure(text="")
        self.config(cursor="")

    def load_fresh_video_data(self, video_path):
        info = self.get_video_info(video_path)
        if not info:
            messagebox.showerror("Error", f"Failed to extract info from:\n{os.path.basename(video_path)}")
            return

        header_text = (
            f"Name: {info['filename']}\n"
            f"Duration: {info['formatted_duration']} ({info['formatted_size']})  {info['bitrate_kbps']:.3f} kbps\n"
            f"{info['streams_formatted']}"
        )

        cols = int(self.spin_cols.get())
        rows = int(self.spin_rows.get())
        count = cols * rows

        duration = info["duration"]
        start_margin = duration * 0.05
        end_margin = duration * 0.95
        duration_active = end_margin - start_margin

        frames = []
        for i in range(count):
            ts = start_margin + (duration_active / (count - 1)) * i if count > 1 else duration / 2
            frames.append({
                "index": i,
                "timestamp": ts,
                "excluded": False,
                "temp_path": os.path.join(self.temp_dir, f"pre_{hash(video_path)}_{i}.png")
            })

        self.custom_data[video_path] = {
            "info": info,
            "header": header_text,
            "frames": frames
        }

        self.txt_header.delete("1.0", "end")
        self.txt_header.insert("1.0", header_text)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for f in frames:
                futures.append(executor.submit(self.extract_frame, video_path, f["timestamp"], f["temp_path"], 160, 90))
            results = [f.result() for f in futures]

        self.render_edit_frames(frames)

    def on_header_text_edited(self, event):
        if self.current_preview_video in self.custom_data:
            self.custom_data[self.current_preview_video]["header"] = self.txt_header.get("1.0", "end-1c")

    def render_edit_frames(self, frames):
        for child in self.edit_scroll_frame.winfo_children():
            child.destroy()
            
        self.preview_images = []
        cols = 2
        
        for idx, f in enumerate(frames):
            r = idx // cols
            c = idx % cols
            
            f_frame = ctk.CTkFrame(self.edit_scroll_frame, fg_color="#242427", border_color="#3f3f46", border_width=1)
            f_frame.grid(row=r, column=c, padx=8, pady=8)
            
            try:
                img = Image.open(f["temp_path"])
                photo = ImageTk.PhotoImage(img)
                self.preview_images.append(photo)
                
                lbl_img = tk.Label(f_frame, image=photo, bg="#242427")
                lbl_img.pack(padx=5, pady=5)
            except Exception:
                lbl_img = ctk.CTkLabel(f_frame, text="No Preview", fg_color="#242427", width=160, height=90)
                lbl_img.pack(padx=5, pady=5)

            var_ex = tk.BooleanVar(value=not f["excluded"])
            
            def make_toggle(index=idx, var=var_ex):
                frames[index]["excluded"] = not var.get()
                
            chk = ctk.CTkCheckBox(
                f_frame, 
                text="Include Frame", 
                variable=var_ex, 
                command=make_toggle, 
                font=("Segoe UI", 9),
                text_color=self.text_color,
                fg_color=self.accent_color
            )
            chk.pack(anchor="w", pady=(2, 5), padx=5)
            
            time_frame = ctk.CTkFrame(f_frame, fg_color="transparent")
            time_frame.pack(fill="x", padx=5, pady=(0, 5))
            
            lbl_ts = ctk.CTkLabel(time_frame, text="Time:", font=("Segoe UI", 9), text_color=self.text_color)
            lbl_ts.pack(side="left")
            
            ent_ts = ctk.CTkEntry(time_frame, font=("Segoe UI", 9), fg_color=self.widget_bg, border_color=self.border_color, text_color=self.text_color, width=60, height=22)
            ent_ts.insert(0, self.format_duration_ms(f["timestamp"]))
            ent_ts.pack(side="left", padx=2)
            
            def make_update(index=idx, entry=ent_ts):
                time_str = entry.get()
                try:
                    self.lbl_loading_status.configure(text=f"Seeking frame {index+1}...")
                    self.config(cursor="watch")
                    self.update()

                    ts = self.parse_time_str(time_str)
                    frames[index]["timestamp"] = ts
                    self.extract_frame(self.current_preview_video, ts, frames[index]["temp_path"], 160, 90)
                    self.render_edit_frames(frames)
                except Exception:
                    messagebox.showerror("Error", "Invalid timestamp format (use H:M:S,ms or Sec)")
                finally:
                    self.lbl_loading_status.configure(text="")
                    self.config(cursor="")

            def make_random(index=idx):
                try:
                    video_info = self.custom_data[self.current_preview_video]["info"]
                    duration = video_info["duration"]
                    
                    t_min = 0.0
                    if index > 0:
                        t_min = frames[index - 1]["timestamp"] + 0.1
                        
                    t_max = duration
                    if index < len(frames) - 1:
                        t_max = frames[index + 1]["timestamp"] - 0.1
                        
                    if t_max <= t_min:
                        messagebox.showwarning("Warning", "Cannot generate random frame: range between neighboring frames is too small.")
                        return
                        
                    import random
                    new_ts = random.uniform(t_min, t_max)
                    
                    self.lbl_loading_status.configure(text=f"Extracting random frame {index+1}...")
                    self.config(cursor="watch")
                    self.update()
                    
                    frames[index]["timestamp"] = new_ts
                    self.extract_frame(self.current_preview_video, new_ts, frames[index]["temp_path"], 160, 90)
                    self.render_edit_frames(frames)
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to generate random frame: {e}")
                finally:
                    self.lbl_loading_status.configure(text="")
                    self.config(cursor="")

            btn_up = ctk.CTkButton(time_frame, text="Set", command=make_update, font=("Segoe UI", 9, "bold"), fg_color="#27272a", text_color=self.text_color, hover_color="#3f3f46", width=32, height=22)
            btn_up.pack(side="left", padx=2)

            btn_rand = ctk.CTkButton(time_frame, text="Rnd", command=make_random, font=("Segoe UI", 9, "bold"), fg_color="#27272a", text_color=self.text_color, hover_color="#3f3f46", width=32, height=22)
            btn_rand.pack(side="left", padx=2)

    def parse_time_str(self, time_str):
        time_str = time_str.replace(",", ".")
        if ":" in time_str:
            parts = time_str.split(":")
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
        return float(time_str)

    # --- LIVE PREVIEW GENERATOR ---
    def show_live_preview(self):
        if not self.files_list:
            messagebox.showwarning("Warning", "Please add a video file first to preview the layout.")
            return

        video_path = self.current_preview_video
        if not video_path or video_path not in self.files_list:
            video_path = self.files_list[0]

        cols = int(self.spin_cols.get())
        rows = int(self.spin_rows.get())
        font_name = self.cb_font.get()
        font_style = self.cb_font_style.get()
        font_size = int(self.spin_font_size.get())
        time_font_size = int(self.spin_time_font_size.get())
        gap_size = int(self.spin_gap.get())
        margin_size = int(self.spin_margin.get())
        theme = self.cb_theme.get()
        
        auto_calc = self.var_auto_size.get()
        fixed_thumb_w = int(self.ent_thumb_w.get()) if self.ent_thumb_w.get() else 321
        fixed_thumb_h = int(self.ent_thumb_h.get()) if self.ent_thumb_h.get() else 162
        width_val = int(self.ent_width.get()) if self.ent_width.get() else 1280

        if video_path in self.custom_data:
            v_data = self.custom_data[video_path]
            info = v_data["info"]
            header_text = v_data["header"]
            active_frames = [f for f in v_data["frames"] if not f["excluded"]]
            timestamps = [f["timestamp"] for f in active_frames]
        else:
            info = self.get_video_info(video_path)
            if not info:
                messagebox.showerror("Error", "Failed to load video info for preview.")
                return
            header_text = (
                f"Name: {info['filename']}\n"
                f"Duration: {info['formatted_duration']} ({info['formatted_size']})  {info['bitrate_kbps']:.3f} kbps\n"
                f"{info['streams_formatted']}"
            )
            count = cols * rows
            duration = info["duration"]
            start_margin = duration * 0.05
            end_margin = duration * 0.95
            duration_active = end_margin - start_margin
            timestamps = [start_margin + (duration_active / (count - 1)) * i for i in range(count)] if count > 1 else [duration / 2]

            frames = []
            for i in range(count):
                ts = start_margin + (duration_active / (count - 1)) * i if count > 1 else duration / 2
                frames.append({
                    "index": i,
                    "timestamp": ts,
                    "excluded": False,
                    "temp_path": os.path.join(self.temp_dir, f"pre_{hash(video_path)}_{i}.png")
                })
            self.custom_data[video_path] = {
                "info": info,
                "header": header_text,
                "frames": frames
            }
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = []
                for f in frames:
                    futures.append(executor.submit(self.extract_frame, video_path, f["timestamp"], f["temp_path"], 160, 90))
                results = [f.result() for f in futures]

        if not auto_calc:
            thumb_width = fixed_thumb_w
            thumb_height = fixed_thumb_h
            final_width = (margin_size * 2) + (thumb_width * cols) + (gap_size * (cols - 1))
        else:
            final_width = width_val if width_val > 0 else info["width"]
            available_width = final_width - (margin_size * 2) - (gap_size * (cols - 1))
            thumb_width = int(available_width / cols)
            aspect_ratio = info["height"] / info["width"] if info["width"] > 0 else 0.75
            thumb_height = int(thumb_width * aspect_ratio)

        self.config(cursor="watch")
        self.update()

        temp_preview_path = os.path.join(self.temp_dir, "temp_preview.png")

        try:
            self.compile_contact_sheet(
                video_path,
                info,
                timestamps,
                (cols, rows),
                final_width,
                thumb_width,
                thumb_height,
                temp_preview_path,
                header_text,
                font_name,
                font_style,
                font_size,
                time_font_size,
                gap_size,
                margin_size,
                theme,
                95,
                "png"
            )

            # Top level preview window
            preview_win = ctk.CTkToplevel(self)
            preview_win.title("Contact Sheet Live Preview")
            preview_win.geometry("950x750")
            preview_win.configure(fg_color=self.bg_color)

            self.preview_pil_img = Image.open(temp_preview_path)

            tb = ctk.CTkFrame(preview_win, fg_color="#18181b", height=50)
            tb.pack(side="top", fill="x")

            lbl_zoom = ctk.CTkLabel(tb, text="Zoom Mode:", font=("Segoe UI", 10, "bold"), text_color=self.text_color)
            lbl_zoom.pack(side="left", padx=(20, 10), pady=12)

            zoom_var = tk.StringVar(value="Fit to Window")
            cb_zoom = ctk.CTkComboBox(tb, values=["Fit to Window", "Actual Size (100%)"], variable=zoom_var, font=("Segoe UI", 10), width=165)
            cb_zoom.pack(side="left", pady=12)

            main_frame = ctk.CTkFrame(preview_win, fg_color="transparent")
            main_frame.pack(fill="both", expand=True, padx=15, pady=15)
            
            main_frame.grid_rowconfigure(0, weight=1)
            main_frame.grid_columnconfigure(0, weight=1)

            pv_canvas = tk.Canvas(main_frame, bg="#09090b", borderwidth=0, highlightthickness=0)
            pv_canvas.grid(row=0, column=0, sticky="nsew")

            vbar = ctk.CTkScrollbar(main_frame, orientation="vertical", command=pv_canvas.yview)
            hbar = ctk.CTkScrollbar(main_frame, orientation="horizontal", command=pv_canvas.xview)
            
            pv_canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)

            def update_displayed_image():
                mode = zoom_var.get()
                if mode == "Fit to Window":
                    vbar.grid_forget()
                    hbar.grid_forget()
                    
                    # Read current window dimensions
                    win_w = pv_canvas.winfo_width()
                    win_h = pv_canvas.winfo_height()
                    if win_w < 50:
                        win_w = 900
                    if win_h < 50:
                        win_h = 600
                    
                    img_w, img_h = self.preview_pil_img.size
                    ratio = min(win_w / img_w, win_h / img_h)
                    new_w = max(10, int(img_w * ratio))
                    new_h = max(10, int(img_h * ratio))
                    
                    resized_pil = self.preview_pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    self.preview_tk_img = ImageTk.PhotoImage(resized_pil)
                    
                    pv_canvas.delete("all")
                    cx = win_w // 2
                    cy = win_h // 2
                    pv_canvas.create_image(cx, cy, image=self.preview_tk_img, anchor="center")
                    pv_canvas.configure(scrollregion=(0, 0, win_w, win_h))
                else:
                    vbar.grid(row=0, column=1, sticky="ns")
                    hbar.grid(row=1, column=0, sticky="ew")
                    
                    self.preview_tk_img = ImageTk.PhotoImage(self.preview_pil_img)
                    pv_canvas.delete("all")
                    pv_canvas.create_image(0, 0, image=self.preview_tk_img, anchor="nw")
                    pv_canvas.configure(scrollregion=(0, 0, self.preview_pil_img.width, self.preview_pil_img.height))

            # Trigger change in Zoom selection
            cb_zoom.configure(command=lambda v: update_displayed_image())

            def on_configure(event):
                if event.widget == pv_canvas:
                    if zoom_var.get() == "Fit to Window":
                        update_displayed_image()

            pv_canvas.bind("<Configure>", on_configure)
            preview_win.after(100, update_displayed_image)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate preview: {e}")
        finally:
            self.config(cursor="")

    # --- COMPILE PROCESS FOR ALL FILES ---
    def run_process_all(self):
        if not self.files_list:
            messagebox.showwarning("Warning", "Please add at least one video file first.")
            return

        self.save_settings()

        self.config(cursor="watch")
        self.btn_run.configure(text="PROCESSING... PLEASE WAIT", state="disabled")
        self.update()

        cols = int(self.spin_cols.get())
        rows = int(self.spin_rows.get())
        font_name = self.cb_font.get()
        font_style = self.cb_font_style.get()
        font_size = int(self.spin_font_size.get())
        time_font_size = int(self.spin_time_font_size.get())
        gap_size = int(self.spin_gap.get())
        margin_size = int(self.spin_margin.get())
        theme = self.cb_theme.get()
        quality = int(self.spin_quality.get())
        suffix = self.ent_suffix.get()
        out_fmt = self.cb_format.get().lower()
        exist_behavior = self.cb_exist.get()

        auto_calc = self.var_auto_size.get()
        fixed_thumb_w = int(self.ent_thumb_w.get()) if self.ent_thumb_w.get() else 321
        fixed_thumb_h = int(self.ent_thumb_h.get()) if self.ent_thumb_h.get() else 162
        width_val = int(self.ent_width.get()) if self.ent_width.get() else 1280

        success_count = 0
        error_files = []

        for video_path in self.files_list:
            if self.var_same_dir.get():
                out_dir = os.path.dirname(video_path)
            else:
                out_dir = self.ent_output_dir.get()
                if not out_dir:
                    out_dir = os.path.dirname(video_path)

            base_name, _ = os.path.splitext(os.path.basename(video_path))
            out_file = os.path.join(out_dir, base_name + f"{suffix}.{out_fmt}")

            if exist_behavior == "Create New (Append number)":
                counter = 0
                candidate = out_file
                while os.path.exists(candidate):
                    counter += 1
                    candidate = os.path.join(out_dir, base_name + f"{suffix}.{counter}.{out_fmt}")
                out_file = candidate
            elif exist_behavior == "Skip Existed":
                if os.path.exists(out_file):
                    success_count += 1
                    continue

            if video_path in self.custom_data:
                v_data = self.custom_data[video_path]
                info = v_data["info"]
                header_text = v_data["header"]
                active_frames = [f for f in v_data["frames"] if not f["excluded"]]
                timestamps = [f["timestamp"] for f in active_frames]
            else:
                info = self.get_video_info(video_path)
                if not info:
                    error_files.append(os.path.basename(video_path))
                    continue

                header_text = (
                    f"Name: {info['filename']}\n"
                    f"Duration: {info['formatted_duration']} ({info['formatted_size']})  {info['bitrate_kbps']:.3f} kbps\n"
                    f"{info['streams_formatted']}"
                )

                count = cols * rows
                duration = info["duration"]
                start_margin = duration * 0.05
                end_margin = duration * 0.95
                duration_active = end_margin - start_margin
                timestamps = [start_margin + (duration_active / (count - 1)) * i for i in range(count)] if count > 1 else [duration / 2]

            if not auto_calc:
                thumb_width = fixed_thumb_w
                thumb_height = fixed_thumb_h
                final_width = (margin_size * 2) + (thumb_width * cols) + (gap_size * (cols - 1))
            else:
                final_width = width_val if width_val > 0 else info["width"]
                available_width = final_width - (margin_size * 2) - (gap_size * (cols - 1))
                thumb_width = int(available_width / cols)
                aspect_ratio = info["height"] / info["width"] if info["width"] > 0 else 0.75
                thumb_height = int(thumb_width * aspect_ratio)

            try:
                self.compile_contact_sheet(
                    video_path,
                    info,
                    timestamps,
                    (cols, rows),
                    final_width,
                    thumb_width,
                    thumb_height,
                    out_file,
                    header_text,
                    font_name,
                    font_style,
                    font_size,
                    time_font_size,
                    gap_size,
                    margin_size,
                    theme,
                    quality,
                    out_fmt
                )
                success_count += 1
            except Exception as e:
                print(f"Error processing {video_path}: {e}")
                error_files.append(os.path.basename(video_path))

        self.config(cursor="")
        self.btn_run.configure(text="RUN (Generate Contact Sheets)", state="normal")
        self.update()

        if error_files:
            messagebox.showerror(
                "Process Completed",
                f"Generated {success_count} sheets successfully.\n"
                f"Failed files:\n" + "\n".join(error_files)
            )
        else:
            messagebox.showinfo(
                "Process Completed",
                f"Successfully generated {success_count} contact sheets!"
            )

    def compile_contact_sheet(self, video_path, info, timestamps, grid, sheet_width, thumb_width, thumb_height, output_path, header_text, font_name, font_style, font_size, time_font_size, gap_size, margin_size, theme, quality, out_fmt):
        cols, rows = grid
        font_header = self.get_best_font(font_name, font_size, font_style)
        
        header_lines = header_text.splitlines()
        line_height = font_size + 4
        header_h = len(header_lines) * line_height + 10 if self.var_info.get() else 0

        canvas_h = margin_size
        if self.var_info.get():
            canvas_h += header_h + margin_size
        canvas_h += (thumb_height * rows) + (gap_size * (rows - 1)) + margin_size

        is_dark = "Dark" in theme
        bg_color = (0, 0, 0) if is_dark else (255, 255, 255)
        text_color = (255, 255, 255) if is_dark else (0, 0, 0)
        border_color = (64, 64, 64) if is_dark else (240, 240, 240)

        canvas = Image.new("RGB", (sheet_width, canvas_h), bg_color)
        draw = ImageDraw.Draw(canvas)

        if self.var_info.get():
            meta_y = margin_size
            for line in header_lines:
                if line.strip():
                    draw.text((margin_size + 4, meta_y), line, fill=text_color, font=font_header)
                meta_y += line_height

        start_y = margin_size
        if self.var_info.get():
            start_y += header_h + margin_size

        with tempfile.TemporaryDirectory() as tmpdir:
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = []
                for idx, ts in enumerate(timestamps):
                    if idx >= cols * rows:
                        break
                    tmp_img_path = os.path.join(tmpdir, f"frame_{idx}.png")
                    futures.append(executor.submit(self.extract_frame, video_path, ts, tmp_img_path, thumb_width, thumb_height))
                results = [f.result() for f in futures]

            for idx, ts in enumerate(timestamps):
                if idx >= cols * rows:
                    break
                tmp_img_path = os.path.join(tmpdir, f"frame_{idx}.png")
                if os.path.exists(tmp_img_path):
                    img = Image.open(tmp_img_path)
                    
                    r = idx // cols
                    c = idx % cols
                    
                    px = margin_size + c * (thumb_width + gap_size)
                    py = start_y + r * (thumb_height + gap_size)
                    
                    draw.rectangle([px - 1, py - 1, px + thumb_width, py + thumb_height], outline=border_color, width=1)
                    canvas.paste(img, (px, py))
                    
                    if self.var_time.get():
                        time_str = self.format_thumbnail_time(ts)
                        font_time = self.get_best_font(font_name, time_font_size, font_style)
                        
                        try:
                            bbox = draw.textbbox((0, 0), time_str, font=font_time)
                            tw = bbox[2] - bbox[0]
                            th = bbox[3] - bbox[1]
                        except AttributeError:
                            tw, th = draw.textsize(time_str, font=font_time)
                            
                        tx = px + (thumb_width - tw) // 2
                        ty = py + thumb_height - th - 6
                        
                        for dx, dy in [(-1,-1), (1,-1), (-1,1), (1,1)]:
                            draw.text((tx+dx, ty+dy), time_str, fill=(0, 0, 0), font=font_time)
                        draw.text((tx, ty), time_str, fill=(255, 255, 255), font=font_time)

        if out_fmt == "png":
            canvas.save(output_path, "PNG")
        else:
            canvas.save(output_path, "JPEG", quality=quality, subsampling=0)

    # --- SETTINGS PERSISTENCE ---
    def save_settings(self):
        current_data = {
            "cols": self.spin_cols.get(),
            "rows": self.spin_rows.get(),
            "auto_size": self.var_auto_size.get(),
            "profile": self.cb_profile.get(),
            "width": self.ent_width.get(),
            "thumb_w": self.ent_thumb_w.get(),
            "thumb_h": self.ent_thumb_h.get(),
            "gap": self.spin_gap.get(),
            "margin": self.spin_margin.get(),
            "suffix": self.ent_suffix.get(),
            "font_face": self.cb_font.get(),
            "font_style": self.cb_font_style.get(),
            "font_size": self.spin_font_size.get(),
            "time_font_size": self.spin_time_font_size.get(),
            "format": self.cb_format.get(),
            "quality": self.spin_quality.get(),
            "exist": self.cb_exist.get(),
            "theme": self.cb_theme.get(),
            "show_time": self.var_time.get(),
            "show_info": self.var_info.get(),
            "same_dir": self.var_same_dir.get(),
            "output_dir": self.ent_output_dir.get()
        }

        if not hasattr(self, 'profiles') or not self.profiles:
            self.profiles = {"Default": current_data}
        if not hasattr(self, 'current_profile_name') or not self.current_profile_name:
            self.current_profile_name = "Default"

        self.profiles[self.current_profile_name] = current_data

        payload = {
            "current_profile": self.current_profile_name,
            "profiles": self.profiles
        }

        if not os.path.exists(SETTINGS_DIR):
            os.makedirs(SETTINGS_DIR, exist_ok=True)
            
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(payload, f, indent=4)
        except Exception:
            pass

    def load_settings(self):
        defaults = {
            "cols": "4",
            "rows": "3",
            "auto_size": True,
            "profile": "Auto (Video size)",
            "width": "0",
            "thumb_w": "321",
            "thumb_h": "162",
            "gap": "4",
            "margin": "6",
            "suffix": "_thumb",
            "font_face": "Comic Sans MS",
            "font_style": "Italic",
            "font_size": "12",
            "time_font_size": "10",
            "format": "JPEG",
            "quality": "92",
            "exist": "Create New (Append number)",
            "theme": "Light (White)",
            "show_time": True,
            "show_info": True,
            "same_dir": True,
            "output_dir": ""
        }
        
        self.profiles = {"Default": dict(defaults)}
        self.current_profile_name = "Default"

        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    saved = json.load(f)
                    if "profiles" in saved and "current_profile" in saved:
                        self.profiles = saved["profiles"]
                        self.current_profile_name = saved["current_profile"]
                    else:
                        legacy_data = dict(defaults)
                        legacy_data.update(saved)
                        self.profiles = {"Default": legacy_data}
                        self.current_profile_name = "Default"
            except Exception:
                pass

        if hasattr(self, 'cb_config_profiles'):
            self.cb_config_profiles.configure(values=list(self.profiles.keys()))
            self.cb_config_profiles.set(self.current_profile_name)

        self.apply_profile_values(self.current_profile_name)

    def apply_profile_values(self, profile_name):
        if profile_name not in self.profiles:
            return
        data = self.profiles[profile_name]
        
        self.spin_cols.delete(0, "end")
        self.spin_cols.insert(0, data.get("cols", "4"))
        self.spin_rows.delete(0, "end")
        self.spin_rows.insert(0, data.get("rows", "3"))
        
        self.var_auto_size.set(data.get("auto_size", True))
        self.cb_profile.set(data.get("profile", "Auto (Video size)"))
        
        self.ent_width.delete(0, "end")
        self.ent_width.insert(0, data.get("width", "0"))

        self.ent_thumb_w.delete(0, "end")
        self.ent_thumb_w.insert(0, data.get("thumb_w", "321"))
        self.ent_thumb_h.delete(0, "end")
        self.ent_thumb_h.insert(0, data.get("thumb_h", "162"))
        
        self.spin_gap.delete(0, "end")
        self.spin_gap.insert(0, data.get("gap", "4"))
        self.spin_margin.delete(0, "end")
        self.spin_margin.insert(0, data.get("margin", "6"))
        
        self.ent_suffix.delete(0, "end")
        self.ent_suffix.insert(0, data.get("suffix", "_thumb"))
        
        self.cb_font.set(data.get("font_face", "Comic Sans MS"))
        self.cb_font_style.set(data.get("font_style", "Italic"))
        
        self.spin_font_size.delete(0, "end")
        self.spin_font_size.insert(0, data.get("font_size", "12"))

        self.spin_time_font_size.delete(0, "end")
        self.spin_time_font_size.insert(0, data.get("time_font_size", "10"))
        
        self.cb_format.set(data.get("format", "JPEG"))
        self.spin_quality.delete(0, "end")
        self.spin_quality.insert(0, data.get("quality", "92"))
        
        self.cb_exist.set(data.get("exist", "Create New (Append number)"))
        self.cb_theme.set(data.get("theme", "Light (White)"))
        
        self.var_time.set(data.get("show_time", True))
        self.var_info.set(data.get("show_info", True))
        self.var_same_dir.set(data.get("same_dir", True))
        
        self.ent_output_dir.configure(state="normal")
        self.ent_output_dir.delete(0, "end")
        self.ent_output_dir.insert(0, data.get("output_dir", ""))
        
        self.toggle_output_dir_widgets()
        self.toggle_quality_widget(None)
        self.toggle_size_mode_fields()

    def on_close(self):
        self.save_settings()
        self.destroy()

    # --- VIDEO UTILITIES & CACHED FRAME EXTRACTION ---
    def get_video_info(self, video_path):
        return self.get_video_info_ffprobe(video_path)

    def get_video_info_ffprobe(self, video_path):
        # Retrieve bitrates from pymediainfo first if possible
        mi_video_bitrates = []
        mi_audio_bitrates = []
        if MediaInfo.can_parse():
            try:
                mi = MediaInfo.parse(video_path)
                mi_video_bitrates = [t.bit_rate for t in mi.tracks if t.track_type == "Video"]
                mi_audio_bitrates = [t.bit_rate for t in mi.tracks if t.track_type == "Audio"]
            except Exception:
                pass

        cmd = [
            self.get_bin_path("ffprobe"),
            "-v", "error",
            "-show_format",
            "-show_streams",
            "-of", "json",
            video_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, check=True, creationflags=CREATE_NO_WINDOW)
            stdout_str = result.stdout.decode("utf-8", errors="ignore")
            data = json.loads(stdout_str)
            
            video_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
            format_info = data.get("format", {})
            
            duration = float(format_info.get("duration", 0))
            if duration == 0 and video_streams:
                duration = float(video_streams[0].get("duration", 0))
                
            width = int(video_streams[0].get("width", 0)) if video_streams else 0
            height = int(video_streams[0].get("height", 0)) if video_streams else 0
            size_bytes = int(format_info.get("size", 0))
            
            fps_eval = video_streams[0].get("avg_frame_rate", "0/0") if video_streams else "0/0"
            if "/" in fps_eval:
                try:
                    num, den = map(int, fps_eval.split("/"))
                    fps = round(num / den, 3) if den != 0 else 0
                except ValueError:
                    fps = 0
            else:
                fps = float(fps_eval) if fps_eval else 0
                
            all_streams = []
            v_idx = -1
            a_idx = -1
            
            for s in data.get("streams", []):
                ctype = s.get("codec_type")
                cname = s.get("codec_name", "unknown").upper()
                
                # Skip embedded covers / attachment images completely
                if ctype == "video" and cname in ["PNG", "MJPEG", "BMP", "TIFF"]:
                    continue

                if ctype == "video":
                    v_idx += 1
                elif ctype == "audio":
                    a_idx += 1

                # Extract stream bitrate
                bit_rate_raw = s.get("bit_rate")
                if not bit_rate_raw:
                    tags = s.get("tags", {})
                    for k, v in tags.items():
                        if "BPS" in k.upper():
                            bit_rate_raw = v
                            break
                            
                if not bit_rate_raw:
                    if ctype == "video" and v_idx < len(mi_video_bitrates):
                        bit_rate_raw = mi_video_bitrates[v_idx]
                    elif ctype == "audio" and a_idx < len(mi_audio_bitrates):
                        bit_rate_raw = mi_audio_bitrates[a_idx]

                bitrate_str = ""
                if bit_rate_raw:
                    try:
                        br = float(bit_rate_raw) / 1000.0
                        bitrate_str = f"  {br:.3f} kbps"
                    except ValueError:
                        pass

                if ctype == "video":
                    w = s.get("width", 0)
                    h = s.get("height", 0)
                    dar = s.get("display_aspect_ratio", "")
                    dar_str = f" DAR {dar}" if dar else ""
                    # Keep identical to classic video output (no bitrate at end of video stream)
                    all_streams.append(f"Video: {s.get('codec_long_name', cname)} (Resolution: {w}x{h}){dar_str}   {fps:.3f} FPS")
                elif ctype == "audio":
                    a_name = s.get("codec_long_name", cname)
                    a_ch = s.get("channels")
                    if not a_ch:
                        ch_layout = s.get("ch_layout")
                        if isinstance(ch_layout, dict):
                            a_ch = ch_layout.get("nb_channels", 2)
                        elif isinstance(ch_layout, str):
                            if "5.1" in ch_layout:
                                a_ch = 6
                            elif "7.1" in ch_layout:
                                a_ch = 8
                            elif "stereo" in ch_layout:
                                a_ch = 2
                            elif "mono" in ch_layout:
                                a_ch = 1
                            else:
                                a_ch = 2
                        else:
                            a_ch = 2
                    a_rt = s.get("sample_rate", 48000)
                    a_lg = s.get("tags", {}).get("language", "")
                    lg_part = f": {a_lg}" if a_lg else ""
                    all_streams.append(f"Audio: {a_name}{lg_part} {a_ch}-CH  {a_rt}Hz{bitrate_str}")
                elif ctype == "subtitle":
                    lg = s.get("tags", {}).get("language", "unknown")
                    sub_title = s.get("tags", {}).get("title", "")
                    title_part = f" ({sub_title})" if sub_title else ""
                    all_streams.append(f"Subtitle: {lg}{title_part}")

            return {
                "filename": os.path.basename(video_path),
                "duration": duration,
                "formatted_duration": self.format_duration_hhmmss(duration),
                "width": width,
                "height": height,
                "size": size_bytes,
                "formatted_size": self.format_size(size_bytes),
                "fps": fps,
                "bitrate_kbps": float(format_info.get("bit_rate", 0)) / 1000.0 if format_info.get("bit_rate") else 0,
                "streams_formatted": "\n".join(all_streams)
            }
        except Exception as e:
            import traceback
            err_msg = "".join(traceback.format_exception(*sys.exc_info()))
            messagebox.showerror("ffprobe parse error", f"Error details:\n{err_msg}")
            return None

    def format_duration_ms(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        ms = int(round((seconds - int(seconds)) * 1000))
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d},{ms:03d}"
        return f"{minutes:02d}:{secs:02d},{ms:03d}"

    def format_duration_hhmmss(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def format_thumbnail_time(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def format_size(self, bytes_size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} TB"

    def extract_frame(self, video_path, time_seconds, output_path, width, height):
        time_seconds = round(time_seconds, 3)
        cache_filename = f"cache_{hash(video_path)}_{time_seconds}_{width}_{height}.png"
        cached_file = os.path.join(self.temp_dir, cache_filename)
        
        if os.path.exists(cached_file):
            if cached_file != output_path:
                try:
                    shutil.copy2(cached_file, output_path)
                    return True
                except Exception:
                    pass
            else:
                return True
                
        cmd = [
            self.get_bin_path("ffmpeg"),
            "-y",
            "-ss", f"{time_seconds:.3f}",
            "-i", video_path,
            "-vframes", "1",
            "-s", f"{width}x{height}",
            "-f", "image2",
            cached_file
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, creationflags=CREATE_NO_WINDOW)
            if os.path.exists(cached_file) and cached_file != output_path:
                shutil.copy2(cached_file, output_path)
            return True
        except Exception:
            return False

    def get_bin_path(self, name):
        if getattr(sys, 'frozen', False):
            base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            local_path = os.path.join(base_dir, name + ".exe")
            if os.path.exists(local_path):
                return local_path
            
            local_path_sibling = os.path.join(os.path.dirname(sys.executable), name + ".exe")
            if os.path.exists(local_path_sibling):
                return local_path_sibling

            local_path_internal = os.path.join(os.path.dirname(sys.executable), "_internal", name + ".exe")
            if os.path.exists(local_path_internal):
                return local_path_internal
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            local_path = os.path.join(base_dir, name + ".exe")
            if os.path.exists(local_path):
                return local_path

        fallback = os.path.join("C:\\Program Files (x86)\\Ezthumb", name + ".exe")
        if os.path.exists(fallback):
            return fallback

        return name

    def get_best_font(self, font_name, size, style="Regular"):
        fam_lower = font_name.lower()
        candidates = []
        if style == "Bold Italic":
            candidates.append(f"{fam_lower} bold italic")
            candidates.append(f"{fam_lower} bolditalic")
        elif style == "Bold":
            candidates.append(f"{fam_lower} bold")
        elif style == "Italic":
            candidates.append(f"{fam_lower} italic")
            candidates.append(f"{fam_lower} oblique")
        candidates.append(fam_lower)

        for cand in candidates:
            if cand in self.fonts_map:
                filename = self.fonts_map[cand]
                if os.path.isabs(filename):
                    if os.path.exists(filename):
                        try:
                            return ImageFont.truetype(filename, size)
                        except Exception:
                            pass
                else:
                    windir = os.environ.get("WINDIR", "C:\\Windows")
                    path = os.path.join(windir, "Fonts", filename)
                    if os.path.exists(path):
                        try:
                            return ImageFont.truetype(path, size)
                        except Exception:
                            pass

        return ImageFont.load_default()

    def handle_dropfiles_dnd(self, event):
        try:
            files = self.tk.splitlist(event.data)
            if files:
                self.add_dropped_files(files)
        except Exception as e:
            print("Error handling dropped files:", e)

    def add_dropped_files(self, files):
        valid_extensions = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".ts", ".m4v")
        added_any = False
        
        self.config(cursor="watch")
        self.update()

        for f in files:
            f = os.path.abspath(f)
            if os.path.isdir(f):
                for root_dir, _, subfiles in os.walk(f):
                    for sf in subfiles:
                        ext = os.path.splitext(sf)[1].lower()
                        if ext in valid_extensions:
                            fullpath = os.path.join(root_dir, sf)
                            if fullpath not in self.files_list:
                                self.files_list.append(fullpath)
                                self.listbox_files.insert("end", os.path.basename(fullpath))
                                added_any = True
            else:
                ext = os.path.splitext(f)[1].lower()
                if ext in valid_extensions:
                    if f not in self.files_list:
                        self.files_list.append(f)
                        self.listbox_files.insert("end", os.path.basename(f))
                        added_any = True
                        
        if added_any:
            self.update_edit_combobox()
            
        self.config(cursor="")

if __name__ == "__main__":
    app = EzthumbCTkApp()
    app.mainloop()
