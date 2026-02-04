import tkinter as tk
from tkinter import messagebox, filedialog
from PIL import Image, ImageTk
import subprocess
import threading
import multiprocessing
import time
import os
import io
import customtkinter as ctk
import queue
import random
import concurrent.futures
import requests
import json
from pathlib import Path
import re
import sys
import shutil
import tempfile
import hashlib
import uuid
import xml.etree.ElementTree as ET

# --- App Version and Update URL ---
__version__ = "20"  # Updated version number for increace logout scroll
UPDATE_URL = "https://raw.githubusercontent.com/versozadarwin23/adbtool/refs/heads/main/main.py"
VERSION_CHECK_URL = "https://raw.githubusercontent.com/versozadarwin23/adbtool/refs/heads/main/version.txt"

# --- Global Flag for Stopping Commands ---
is_stop_requested = threading.Event()

# --- NEW: Global Variable for Account Directory ---
ACCOUNT_DIR = None
CONFIG_FILE = "config.json"  # New: Configuration file name


def run_adb_command(command, serial, delay_after=0):
    """
    Executes a single ADB command for a specific device with a timeout, checking for a stop signal.
    Added delay_after parameter for timing control.
    """
    if is_stop_requested.is_set():
        return False, "Stop requested."

    try:
        process = subprocess.Popen(['adb', '-s', serial] + command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        timeout_seconds = 60
        start_time = time.time()
        while process.poll() is None and (time.time() - start_time < timeout_seconds):
            if is_stop_requested.is_set():
                process.terminate()
                return False, "Terminated due to stop request."

        if process.poll() is None:
            process.terminate()
            raise subprocess.TimeoutExpired(cmd=['adb', '-s', serial] + command, timeout=timeout_seconds)

        stdout, stderr = process.communicate()

        # Add delay after command execution if specified
        if delay_after > 0 and not is_stop_requested.is_set():
            time.sleep(delay_after)

        if process.returncode != 0:
            return False, stderr.decode()
        else:
            return True, stdout.decode()

    except subprocess.CalledProcessError as e:
        return False, e.stderr.decode()
    except FileNotFoundError:
        return False, "ADB not found. Please install it and add to PATH."
    except subprocess.TimeoutExpired:
        return False, "Command timed out."
    except Exception as e:
        return False, str(e)


def run_tap_command(serial, x, y, delay_before=0, delay_after=0):
    """
    Executes a tap command with configurable delays.
    """
    if is_stop_requested.is_set():
        return False, "Stop requested."

    try:
        # Wait before tap if specified
        if delay_before > 0:
            time.sleep(delay_before)

        # Execute tap command
        tap_cmd = ['shell', 'input', 'tap', str(x), str(y)]
        success, output = run_adb_command(tap_cmd, serial, delay_after)

        return success, output
    except Exception as e:
        return False, str(e)


def run_swipe_command(serial, x1, y1, x2, y2, duration=500, delay_before=0, delay_after=0):
    """
    Executes a swipe command with configurable delays.
    """
    if is_stop_requested.is_set():
        return False, "Stop requested."

    try:
        # Wait before swipe if specified
        if delay_before > 0:
            time.sleep(delay_before)

        # Execute swipe command
        swipe_cmd = ['shell', 'input', 'swipe', str(x1), str(y1), str(x2), str(y2), str(duration)]
        success, output = run_adb_command(swipe_cmd, serial, delay_after)

        return success, output
    except Exception as e:
        return False, str(e)


def run_text_command(text_to_send, serial, typing_delay=20, post_delay=20, tap_delay=20):
    """
    Sends text AND taps the post button with configurable delays.
    """
    if is_stop_requested.is_set():
        return

    if not text_to_send:
        return

    adb_text = text_to_send.replace(' ', '%s')

    try:
        # 1. Input Text
        command_args = ['shell', 'input', 'text', adb_text]
        subprocess.run(['adb', '-s', serial] + command_args,
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,
                       check=True,
                       timeout=5)

        # 2. Wait after typing (Typing Delay)
        time.sleep(float(typing_delay))

        if is_stop_requested.is_set():
            return

        # 3. Wait before clicking Post (Post Delay)
        time.sleep(float(post_delay))

        # 4. Tap command for Post button (Coordinates: 638, 83)
        # Use the new run_tap_command function
        run_tap_command(serial, 638, 83, 0, tap_delay)

    except Exception as e:
        pass


def run_post_only(serial, post_delay=3.0, tap_delay=1.0):
    """
    Executes ONLY the tap command for the Post button with delay.
    """
    if is_stop_requested.is_set():
        return

    try:
        # Wait before clicking Post (Post Delay)
        time.sleep(float(post_delay))

        # Tap command for Post button (Coordinates: 638, 83)
        # Use the new run_tap_command function
        run_tap_command(serial, 638, 83, 0, tap_delay)
    except Exception:
        pass


def create_and_run_updater_script(new_file_path, old_file_path):
    """Handles the file replacement and app restart for updates."""
    try:
        time.sleep(2)
        shutil.move(str(new_file_path), str(old_file_path))

        if sys.platform.startswith('win'):
            os.startfile(str(old_file_path))
        else:
            subprocess.Popen(['python3', str(old_file_path)])

        os._exit(0)
    except Exception as e:
        messagebox.showerror("Update Error", f"Failed to replace file: {e}")


def read_accounts_for_device(serial):
    """
    Reads and returns a list of account names from a file named f'{serial}.txt'
    inside the global ACCOUNT_DIR.
    """
    if not ACCOUNT_DIR:
        return []

    file_path = Path(ACCOUNT_DIR) / f"{serial}.txt"

    if not file_path.is_file():
        return []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines()]
            return [line for line in lines if line]
    except Exception:
        return []


# --- AdbControllerApp Class ---
class AdbControllerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Configuration ---
        self.title(f"ADB Commander By Dars: V{__version__}")
        self.geometry("1400x900")

        # --- FIX: Platform-safe maximize ---
        self.after(100, self.maximize_window)

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # --- Color Palette ---
        self.COLOR_BACKGROUND = "#0D1117"
        self.COLOR_FRAME = "#161B22"
        self.COLOR_BORDER = "#30363D"
        self.COLOR_ACCENT = "#58A6FF"
        self.COLOR_ACCENT_HOVER = "#79B8FF"
        self.COLOR_SUCCESS = "#238636"
        self.COLOR_SUCCESS_HOVER = "#26A641"
        self.COLOR_DANGER = "#DA3633"
        self.COLOR_DANGER_HOVER = "#F85149"
        self.COLOR_WARNING = "#E6C200"
        self.COLOR_TEXT_PRIMARY = "#C9D1D9"
        self.COLOR_TEXT_SECONDARY = "#8B949E"

        # --- Fonts ---
        self.FONT_TITLE = ctk.CTkFont(family="Consolas", size=32, weight="bold")
        self.FONT_HEADING = ctk.CTkFont(family="Consolas", size=18, weight="bold")
        self.FONT_SUBHEADING = ctk.CTkFont(family="Consolas", size=16, weight="bold")
        self.FONT_BODY = ctk.CTkFont(family="Consolas", size=14)
        self.FONT_BUTTON = ctk.CTkFont(family="Consolas", size=14, weight="bold")
        self.FONT_MONO = ctk.CTkFont(family="Consolas", size=14)
        self.FONT_STATUS = ctk.CTkFont(family="Consolas", size=12, weight="normal")

        # --- App State Variables ---
        self.device_frames = {}
        self.device_canvases = {}
        self.device_images = {}
        self.press_start_coords = {}
        self.press_time = {}
        self.selected_device_serial = None
        self.devices = []
        self.long_press_duration = 0.5
        self.drag_threshold = 20
        self.capture_running = {}
        self.screenshot_queue = queue.Queue()
        self.capture_thread = None
        self.update_image_id = None
        self.is_capturing = False
        self.apk_path = None
        self.is_muted = False
        self.update_check_job = None
        self.is_update_prompt_showing = False
        self.share_pairs = []
        self.share_pair_frame = None
        self.is_auto_typing = threading.Event()
        self.is_logging_enabled = tk.BooleanVar(value=False)
        self.account_dir_path = ""
        self.device_account_cycle = {}

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count() * 4)

        # --- Main Window Grid ---
        self.grid_columnconfigure(0, weight=1, minsize=680)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.configure(fg_color=self.COLOR_BACKGROUND)

        # --- [LEFT] Control Panel ---
        self.control_panel = ctk.CTkFrame(self, corner_radius=0, fg_color=self.COLOR_FRAME)
        self.control_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 1), pady=0)

        self.control_panel.grid_columnconfigure(0, weight=1)
        self.control_panel.grid_rowconfigure(4, weight=1)
        self.control_panel.grid_rowconfigure(5, weight=0)

        # Row 0: Title
        ctk.CTkLabel(self.control_panel, text=f"ADB COMMANDER V{__version__}",
                     font=self.FONT_TITLE,
                     text_color=self.COLOR_ACCENT).grid(
            row=0, column=0, pady=(20, 10), padx=20, sticky='w')

        # Row 1: Stop All
        self.stop_all_button = ctk.CTkButton(self.control_panel, text="🛑 TERMINATE ALL OPERATIONS 🛑",
                                             command=self.stop_all_commands,
                                             fg_color=self.COLOR_DANGER,
                                             hover_color=self.COLOR_DANGER_HOVER,
                                             text_color=self.COLOR_TEXT_PRIMARY,
                                             corner_radius=8,
                                             font=self.FONT_HEADING, height=50)
        self.stop_all_button.grid(row=1, column=0, sticky='ew', padx=20, pady=10)

        # Row 2: Device Mgmt
        device_mgmt_frame = ctk.CTkFrame(self.control_panel, fg_color="transparent")
        device_mgmt_frame.grid(row=2, column=0, sticky='ew', padx=20, pady=(10, 5))
        device_mgmt_frame.grid_columnconfigure(1, weight=1)

        self.device_count_label = ctk.CTkLabel(device_mgmt_frame, text="DEVICES: 0",
                                               font=self.FONT_SUBHEADING, text_color=self.COLOR_TEXT_SECONDARY)
        self.device_count_label.grid(row=0, column=0, sticky='w', padx=(0, 10))

        self.detect_button = ctk.CTkButton(device_mgmt_frame, text="REFRESH", command=self.detect_devices,
                                           width=120, corner_radius=8,
                                           fg_color=self.COLOR_ACCENT,
                                           hover_color=self.COLOR_ACCENT_HOVER,
                                           font=self.FONT_BUTTON, height=40, text_color=self.COLOR_BACKGROUND)
        self.detect_button.grid(row=0, column=2, sticky='e', padx=(5, 0))

        self.update_button = ctk.CTkButton(device_mgmt_frame, text=f"UPDATE (V{__version__})",
                                           command=self.update_app,
                                           fg_color="transparent", hover_color=self.COLOR_BORDER, corner_radius=8,
                                           font=self.FONT_BUTTON, height=40,
                                           text_color=self.COLOR_ACCENT, border_color=self.COLOR_ACCENT, border_width=2)
        self.update_button.grid(row=0, column=3, sticky='e', padx=(5, 0))

        # Row 3: Device Select
        device_select_frame = ctk.CTkFrame(self.control_panel, fg_color="transparent")
        device_select_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=5)
        device_select_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(device_select_frame, text="LIVE VIEW:",
                     font=self.FONT_BUTTON, text_color=self.COLOR_TEXT_SECONDARY).grid(row=0, column=0, sticky='w')

        self.device_selector_var = ctk.StringVar(value="No devices found")
        self.device_option_menu = ctk.CTkOptionMenu(device_select_frame,
                                                    variable=self.device_selector_var,
                                                    command=self.on_device_select_menu,
                                                    values=["No devices found"],
                                                    state="disabled",
                                                    font=self.FONT_MONO,
                                                    dropdown_font=self.FONT_MONO,
                                                    fg_color=self.COLOR_FRAME,
                                                    button_color=self.COLOR_BORDER,
                                                    button_hover_color=self.COLOR_ACCENT,
                                                    dropdown_fg_color=self.COLOR_FRAME,
                                                    dropdown_hover_color=self.COLOR_BORDER,
                                                    corner_radius=8,
                                                    height=40)
        self.device_option_menu.grid(row=0, column=1, sticky='ew', padx=(10, 0))

        # Row 4: Tabs
        self.tab_view = ctk.CTkTabview(self.control_panel,
                                       fg_color=self.COLOR_FRAME,
                                       segmented_button_selected_color=self.COLOR_ACCENT,
                                       segmented_button_selected_hover_color=self.COLOR_ACCENT_HOVER,
                                       segmented_button_unselected_hover_color=self.COLOR_BORDER,
                                       segmented_button_unselected_color=self.COLOR_FRAME,
                                       text_color=self.COLOR_TEXT_PRIMARY,
                                       border_color=self.COLOR_BORDER,
                                       border_width=2,
                                       corner_radius=8)
        self.tab_view.grid(row=4, column=0, sticky="nsew", padx=20, pady=10)

        self.tab_view.add("Facebook Automation")
        self.tab_view.add("Utilities")
        self.tab_view.set("Facebook Automation")

        self._load_config()
        self._configure_tab_layouts()

        # Row 5: Status Bar
        self.status_label = ctk.CTkLabel(self.control_panel, text="Awaiting Command...", anchor='w',
                                         font=self.FONT_STATUS, text_color=self.COLOR_TEXT_SECONDARY, height=30,
                                         fg_color=self.COLOR_FRAME)
        self.status_label.grid(row=5, column=0, sticky='sew', padx=20, pady=(5, 10))

        # --- [RIGHT] Device View Panel ---
        self.device_view_panel = ctk.CTkFrame(self, fg_color=self.COLOR_BACKGROUND, corner_radius=0)
        self.device_view_panel.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.device_view_panel.grid_columnconfigure(0, weight=1)
        self.device_view_panel.grid_rowconfigure(0, weight=1)

        # --- Initial Setup ---
        self.detect_devices()
        self.check_for_updates()
        self.start_periodic_update_check()

    def maximize_window(self):
        """Safely maximize window based on OS"""
        try:
            if sys.platform.startswith("win"):
                self.state('zoomed')
            elif sys.platform.startswith("linux"):
                self.attributes('-zoomed', True)
            else:
                self.attributes('-fullscreen', True)
        except Exception:
            # Fallback if maximization attributes are rejected
            try:
                self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
            except Exception:
                pass

    def _update_status_if_enabled(self, text, color):
        if self.is_logging_enabled.get():
            self.after(0, lambda: self.status_label.configure(text=text, text_color=color))

    # --- Config Methods ---
    def _load_config(self):
        global ACCOUNT_DIR
        try:
            if getattr(sys, 'frozen', False):
                base_path = Path(sys.executable).parent
            else:
                base_path = Path(sys.argv[0]).parent

            config_path = base_path / CONFIG_FILE

            if config_path.is_file():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    loaded_path = config.get("account_dir")
                    if loaded_path and Path(loaded_path).is_dir():
                        self.account_dir_path = loaded_path
                        ACCOUNT_DIR = loaded_path
                        self._update_status_if_enabled(
                            text=f"✅ Loaded account folder: {os.path.basename(loaded_path)}",
                            color=self.COLOR_TEXT_SECONDARY)
                        return
        except Exception:
            pass
        self.account_dir_path = ""
        ACCOUNT_DIR = None

    def _save_config(self, path):
        try:
            if getattr(sys, 'frozen', False):
                base_path = Path(sys.executable).parent
            else:
                base_path = Path(sys.argv[0]).parent

            config_path = base_path / CONFIG_FILE

            config = {"account_dir": path}
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
        except Exception:
            self._update_status_if_enabled(
                text="❌ Failed to save configuration file.",
                color=self.COLOR_DANGER)

    def _create_section_header(self, parent, text, row):
        ctk.CTkLabel(parent, text=text,
                     font=self.FONT_HEADING, text_color=self.COLOR_ACCENT).grid(
            row=row, column=0, sticky='w', padx=15, pady=(15, 5))

    def _create_section_frame(self, parent, row):
        frame = ctk.CTkFrame(parent, fg_color=self.COLOR_FRAME, corner_radius=8,
                             border_width=1, border_color=self.COLOR_BORDER)
        frame.grid(row=row, column=0, sticky='ew', padx=15, pady=5)
        frame.grid_columnconfigure(0, weight=1)
        return frame

    def start_periodic_update_check(self):
        self.update_check_job = self.after(60000, self._periodic_check_updates)

    def _periodic_check_updates(self):
        threading.Thread(target=self._check_and_reschedule, daemon=True).start()

    def _check_and_reschedule(self):
        try:
            response = requests.get(VERSION_CHECK_URL, timeout=10)
            response.raise_for_status()
            latest_version = response.text.strip()
            try:
                local_v = float(__version__)
                remote_v = float(latest_version)
                if remote_v > local_v:
                    self.after(0, self.ask_for_update, latest_version)
            except ValueError:
                if latest_version > __version__:
                    self.after(0, self.ask_for_update, latest_version)
        except Exception:
            pass
        finally:
            self.update_check_job = self.after(60000, self._periodic_check_updates)

    def check_for_updates(self):
        def _check_in_thread():
            try:
                response = requests.get(VERSION_CHECK_URL, timeout=10)
                response.raise_for_status()
                latest_version = response.text.strip()
                try:
                    local_v = float(__version__)
                    remote_v = float(latest_version)
                    if remote_v > local_v:
                        self.after(0, self.ask_for_update, latest_version)
                except ValueError:
                    if latest_version > __version__:
                        self.after(0, self.ask_for_update, latest_version)
            except Exception:
                pass

        update_thread = threading.Thread(target=_check_in_thread, daemon=True)
        update_thread.start()

    def ask_for_update(self, latest_version):
        if self.is_update_prompt_showing:
            return

        try:
            self.is_update_prompt_showing = True
            title = "New ADB Commander Update!"
            message = (
                f"An improved version ({latest_version}) is now available!\n\n"
                "New increace logout scroll This update contains the latest upgrades and performance improvements for faster and more reliable control of your devices.\n\n"
                "The app will close and restart to complete the update. Would you like to update now?"
            )
            response = messagebox.askyesno(title, message)
            if response:
                self.update_app()
        finally:
            self.is_update_prompt_showing = False

    def on_closing(self):
        if self.update_check_job:
            self.after_cancel(self.update_check_job)
        self.is_auto_typing.clear()
        is_stop_requested.set()
        self.stop_capture()
        self.executor.shutdown(wait=False)
        self.destroy()

    def _configure_tab_layouts(self):
        # --- Facebook Automation Tab ---
        fb_tab_container = self.tab_view.tab("Facebook Automation")
        # FIX: Removed fg_color="transparent" to avoid ValueError on some systems
        fb_frame = ctk.CTkScrollableFrame(fb_tab_container, fg_color=None)
        fb_frame.pack(fill="both", expand=True, padx=0, pady=0)
        fb_frame.columnconfigure(0, weight=1)

        # Account Management
        self._create_section_header(fb_frame, "Account Management", 0)
        acc_mgmt_frame = self._create_section_frame(fb_frame, 1)

        initial_acc_dir_text = os.path.basename(
            self.account_dir_path) if self.account_dir_path else "Path: Select account folder..."
        self.acc_dir_entry = ctk.CTkEntry(acc_mgmt_frame, placeholder_text="Path: Select account folder...", height=40,
                                          corner_radius=8, font=self.FONT_BODY)
        self.acc_dir_entry.grid(row=0, column=0, sticky='ew', padx=10, pady=(10, 5))
        self.acc_dir_entry.delete(0, tk.END)
        self.acc_dir_entry.insert(0, initial_acc_dir_text)

        acc_button_frame = ctk.CTkFrame(acc_mgmt_frame, fg_color="transparent")
        acc_button_frame.grid(row=1, column=0, sticky='ew', padx=10, pady=(5, 10))
        acc_button_frame.columnconfigure(0, weight=1)
        acc_button_frame.columnconfigure(1, weight=1)

        browse_acc_button = ctk.CTkButton(acc_button_frame, text="BROWSE DIR", command=self.browse_account_directory,
                                          fg_color=self.COLOR_BORDER, hover_color=self.COLOR_TEXT_SECONDARY,
                                          corner_radius=8, height=40, font=self.FONT_BUTTON)
        browse_acc_button.grid(row=0, column=0, sticky='ew', padx=(0, 5))

        acc_status_text = f"Folder: {os.path.basename(self.account_dir_path)}" if self.account_dir_path else "No folder selected."
        self.acc_status_label = ctk.CTkLabel(acc_button_frame, text=acc_status_text, anchor='e',
                                             font=self.FONT_BODY, text_color=self.COLOR_TEXT_SECONDARY)
        self.acc_status_label.grid(row=0, column=1, sticky='ew', padx=(5, 0))

        # App Control
        self._create_section_header(fb_frame, "App Control", 2)
        fb_app_frame = self._create_section_frame(fb_frame, 3)
        fb_app_frame.columnconfigure(0, weight=1)
        fb_app_frame.columnconfigure(1, weight=1)
        fb_app_frame.columnconfigure(2, weight=1)
        fb_app_frame.columnconfigure(3, weight=0)

        self.launch_fb_lite_button = ctk.CTkButton(fb_app_frame, text="Launch FB Lite",
                                                   command=self.launch_fb_lite,
                                                   corner_radius=8, fg_color=self.COLOR_BORDER,
                                                   hover_color=self.COLOR_TEXT_SECONDARY,
                                                   height=40, font=self.FONT_BUTTON, text_color=self.COLOR_TEXT_PRIMARY)
        self.launch_fb_lite_button.grid(row=0, column=0, sticky='ew', padx=(10, 5), pady=10)

        self.force_stop_fb_lite_button = ctk.CTkButton(fb_app_frame, text="Force Stop",
                                                       command=self.force_stop_fb_lite,
                                                       fg_color=self.COLOR_DANGER,
                                                       hover_color=self.COLOR_DANGER_HOVER, corner_radius=8,
                                                       text_color=self.COLOR_TEXT_PRIMARY, height=40,
                                                       font=self.FONT_BUTTON)
        self.force_stop_fb_lite_button.grid(row=0, column=1, sticky='ew', padx=(5, 5), pady=10)

        self.switch_acc_button = ctk.CTkButton(fb_app_frame, text="SWITCH ACC 🔄",
                                               command=lambda: threading.Thread(
                                                   target=self._threaded_run_switch_account_sequence,
                                                   daemon=True).start(),
                                               corner_radius=8, fg_color=self.COLOR_ACCENT,
                                               hover_color=self.COLOR_ACCENT_HOVER,
                                               height=40, font=self.FONT_BUTTON, text_color=self.COLOR_BACKGROUND)
        self.switch_acc_button.grid(row=0, column=2, sticky='ew', padx=(5, 5), pady=10)

        self.switch_acc_tip_button = ctk.CTkButton(fb_app_frame, text="❓",
                                                   command=self.show_switch_account_tips,
                                                   corner_radius=8, fg_color=self.COLOR_FRAME,
                                                   hover_color=self.COLOR_BORDER,
                                                   height=40, width=40, font=self.FONT_BUTTON,
                                                   text_color=self.COLOR_TEXT_PRIMARY)
        self.switch_acc_tip_button.grid(row=0, column=3, sticky='e', padx=(5, 10), pady=10)

        # Single Post
        self._create_section_header(fb_frame, "Single Post Visit", 4)
        fb_single_frame = self._create_section_frame(fb_frame, 5)

        self.fb_url_entry = ctk.CTkEntry(fb_single_frame, placeholder_text="Enter Facebook URL...", height=40,
                                         corner_radius=8, font=self.FONT_BODY)
        self.fb_url_entry.grid(row=0, column=0, sticky='ew', padx=10, pady=(10, 5))

        self.fb_button = ctk.CTkButton(fb_single_frame, text="VISIT POST", command=self.open_fb_lite_deeplink,
                                       fg_color="#1877f2", hover_color="#1651b7", height=40,
                                       font=self.FONT_BUTTON, corner_radius=8)
        self.fb_button.grid(row=1, column=0, sticky='ew', padx=10, pady=(5, 10))

        # Multi-Post Automation
        self._create_section_header(fb_frame, "Multi-Link & Caption Automation", 6)
        self.share_pair_frame = ctk.CTkScrollableFrame(fb_frame, fg_color=self.COLOR_FRAME, height=200,
                                                       corner_radius=8, border_color=self.COLOR_BORDER, border_width=1)
        self.share_pair_frame.grid(row=7, column=0, sticky='ew', padx=15, pady=5)
        self.share_pair_frame.columnconfigure(0, weight=1)

        add_link_button = ctk.CTkButton(fb_frame, text="➕ ADD LINK / CAPTION PAIR", command=self.add_share_pair,
                                        fg_color=self.COLOR_SUCCESS, hover_color=self.COLOR_SUCCESS_HOVER, height=40,
                                        font=self.FONT_BUTTON, corner_radius=8,
                                        text_color=self.COLOR_BACKGROUND)
        add_link_button.grid(row=8, column=0, sticky='ew', padx=15, pady=(5, 10))

        self.add_share_pair(is_initial=True)

        # --- NEW: Timing Settings ---
        self._create_section_header(fb_frame, "Timing Control", 9)
        timing_frame = self._create_section_frame(fb_frame, 10)
        timing_frame.columnconfigure(0, weight=1)
        timing_frame.columnconfigure(1, weight=1)
        timing_frame.columnconfigure(2, weight=1)
        timing_frame.columnconfigure(3, weight=1)

        # Label 1
        ctk.CTkLabel(timing_frame, text="After Typing Delay (s):", font=self.FONT_BODY).grid(row=0, column=0,
                                                                                             padx=(10, 5), pady=10)
        # Input 1
        self.typing_delay_entry = ctk.CTkEntry(timing_frame, placeholder_text="20", width=60, font=self.FONT_BODY)
        self.typing_delay_entry.insert(0, "20")
        self.typing_delay_entry.grid(row=0, column=1, padx=(0, 10), pady=10, sticky='w')

        # Label 2
        ctk.CTkLabel(timing_frame, text="Before Post Click Delay (s):", font=self.FONT_BODY).grid(row=0, column=2,
                                                                                                  padx=(10, 5), pady=10)
        # Input 2
        self.post_delay_entry = ctk.CTkEntry(timing_frame, placeholder_text="20", width=60, font=self.FONT_BODY)
        self.post_delay_entry.insert(0, "20")
        self.post_delay_entry.grid(row=0, column=3, padx=(0, 10), pady=10, sticky='w')

        # NEW: Additional timing controls
        # Label 3
        ctk.CTkLabel(timing_frame, text="Tap Delay (s):", font=self.FONT_BODY).grid(row=1, column=0,
                                                                                    padx=(10, 5), pady=10)
        # Input 3
        self.tap_delay_entry = ctk.CTkEntry(timing_frame, placeholder_text="20", width=60, font=self.FONT_BODY)
        self.tap_delay_entry.insert(0, "20")
        self.tap_delay_entry.grid(row=1, column=1, padx=(0, 10), pady=10, sticky='w')

        # Label 4
        ctk.CTkLabel(timing_frame, text="Swipe Delay (s):", font=self.FONT_BODY).grid(row=1, column=2,
                                                                                      padx=(10, 5), pady=10)
        # Input 4
        self.swipe_delay_entry = ctk.CTkEntry(timing_frame, placeholder_text="20", width=60, font=self.FONT_BODY)
        self.swipe_delay_entry.insert(0, "20")
        self.swipe_delay_entry.grid(row=1, column=3, padx=(0, 10), pady=10, sticky='w')

        # Automation Actions
        self._create_section_header(fb_frame, "Automation Actions", 11)
        action_frame = self._create_section_frame(fb_frame, 12)
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)

        self.send_button = ctk.CTkButton(action_frame, text="SEND RANDOM TEXT ✉️",
                                         command=self.send_text_to_devices,
                                         fg_color=self.COLOR_SUCCESS, hover_color=self.COLOR_SUCCESS_HOVER, height=40,
                                         font=self.FONT_BUTTON, text_color=self.COLOR_BACKGROUND,
                                         corner_radius=8)
        self.send_button.grid(row=0, column=0, sticky='ew', padx=(10, 5), pady=10)

        self.remove_emoji_button = ctk.CTkButton(action_frame, text="REMOVE EMOJIS 🚫",
                                                 command=self.remove_emojis_from_file,
                                                 fg_color=self.COLOR_WARNING, hover_color="#C9A800", height=40,
                                                 font=self.FONT_BUTTON,
                                                 text_color=self.COLOR_BACKGROUND, corner_radius=8)
        self.remove_emoji_button.grid(row=0, column=1, sticky='ew', padx=(5, 10), pady=10)

        self.find_click_type_button = ctk.CTkButton(fb_frame, text="START AUTO-TYPE ⌨️",
                                                    command=self.toggle_auto_type_loop,
                                                    fg_color=self.COLOR_ACCENT, hover_color=self.COLOR_ACCENT_HOVER,
                                                    height=50, font=self.FONT_SUBHEADING,
                                                    text_color=self.COLOR_BACKGROUND, corner_radius=8)
        self.find_click_type_button.grid(row=13, column=0, sticky='ew', padx=15, pady=(15, 15))

        # --- Utilities Tab ---
        utility_tab_container = self.tab_view.tab("Utilities")
        # FIX: Removed fg_color="transparent"
        utility_frame = ctk.CTkScrollableFrame(utility_tab_container, fg_color=None)
        utility_frame.pack(fill="both", expand=True, padx=0, pady=0)
        utility_frame.columnconfigure(0, weight=1)

        # App Management
        self._create_section_header(utility_frame, "App Management", 0)
        apk_frame = self._create_section_frame(utility_frame, 1)

        self.apk_path_entry = ctk.CTkEntry(apk_frame, placeholder_text="Path: No APK selected...", height=40,
                                           corner_radius=8, font=self.FONT_BODY)
        self.apk_path_entry.grid(row=0, column=0, sticky='ew', padx=10, pady=(10, 5))

        apk_button_frame = ctk.CTkFrame(apk_frame, fg_color="transparent")
        apk_button_frame.grid(row=1, column=0, sticky='ew', padx=10, pady=(5, 10))
        apk_button_frame.columnconfigure(0, weight=1)
        apk_button_frame.columnconfigure(1, weight=1)

        browse_apk_button = ctk.CTkButton(apk_button_frame, text="BROWSE", command=self.browse_apk_file,
                                          fg_color=self.COLOR_BORDER, hover_color=self.COLOR_TEXT_SECONDARY,
                                          corner_radius=8, height=40, font=self.FONT_BUTTON)
        browse_apk_button.grid(row=0, column=0, sticky='ew', padx=(0, 5))

        install_apk_button = ctk.CTkButton(apk_button_frame, text="INSTALL APK ⬇️", command=self.install_apk_to_devices,
                                           fg_color=self.COLOR_ACCENT, hover_color=self.COLOR_ACCENT_HOVER,
                                           corner_radius=8, height=40, font=self.FONT_BUTTON,
                                           text_color=self.COLOR_BACKGROUND)
        install_apk_button.grid(row=0, column=1, sticky='ew', padx=(5, 0))

        # Device Control
        self._create_section_header(utility_frame, "Device Control", 2)
        device_control_frame = self._create_section_frame(utility_frame, 3)
        device_control_frame.columnconfigure(0, weight=1)
        device_control_frame.columnconfigure(1, weight=1)

        enable_airplane_button = ctk.CTkButton(device_control_frame, text="ENABLE AIRPLANE ✈️",
                                               command=self.enable_airplane_mode,
                                               fg_color=self.COLOR_BORDER, hover_color=self.COLOR_TEXT_SECONDARY,
                                               corner_radius=8, height=40, font=self.FONT_BUTTON)
        enable_airplane_button.grid(row=0, column=0, sticky='ew', padx=(10, 5), pady=10)

        disable_airplane_button = ctk.CTkButton(device_control_frame, text="DISABLE AIRPLANE 📶",
                                                command=self.disable_airplane_mode,
                                                fg_color=self.COLOR_SUCCESS, hover_color=self.COLOR_SUCCESS_HOVER,
                                                corner_radius=8, height=40, text_color=self.COLOR_BACKGROUND,
                                                font=self.FONT_BUTTON)
        disable_airplane_button.grid(row=0, column=1, sticky='ew', padx=(5, 10), pady=10)

        # Image Sharing
        self._create_section_header(utility_frame, "Share Image to FB Lite", 4)
        image_frame = self._create_section_frame(utility_frame, 5)

        self.image_file_name_entry = ctk.CTkEntry(image_frame,
                                                  placeholder_text="Enter image name in /sdcard/Download...",
                                                  height=40,
                                                  corner_radius=8, font=self.FONT_BODY)
        self.image_file_name_entry.grid(row=0, column=0, sticky='ew', padx=10, pady=(10, 5))

        self.share_image_button = ctk.CTkButton(image_frame, text="SHARE IMAGE",
                                                command=self.share_image_to_fb_lite,
                                                fg_color=self.COLOR_ACCENT, hover_color=self.COLOR_ACCENT_HOVER,
                                                height=40, font=self.FONT_BUTTON, corner_radius=8,
                                                text_color=self.COLOR_BACKGROUND)
        self.share_image_button.grid(row=1, column=0, sticky='ew', padx=10, pady=(5, 10))

        # Logging Control
        self._create_section_header(utility_frame, "Logging Control", 6)
        log_frame = self._create_section_frame(utility_frame, 7)
        log_frame.columnconfigure(0, weight=1)

        ctk.CTkCheckBox(log_frame,
                        text="Enable Status Messages / Logging",
                        variable=self.is_logging_enabled,
                        onvalue=True, offvalue=False,
                        height=40,
                        font=self.FONT_BUTTON,
                        text_color=self.COLOR_TEXT_PRIMARY).grid(row=0, column=0, sticky='ew', padx=10, pady=10)

    def show_switch_account_tips(self):
        tip_title = "ADB Commander: Switch Account Tips"
        tip_message = (
            "The 'SWITCH ACC 🔄' feature automates the process of changing the logged-in Facebook account on all connected devices.\n\n"
            "**⚠️ Requirements for Success:**\n"
            "1. **Account Directory:** You MUST first select an 'Account Directory' using the 'BROWSE DIR' button in the 'Account Management' section.\n"
            "2. **Account Files:** This directory must contain a text file named after each device's serial number (e.g., `device_serial_1.txt`).\n"
            "3. **Account Names in Files:** Each text file must contain a list of the *FULL ACCOUNT NAMES* (as they appear on the FB Lite switch screen), one per line.\n"
            "4. **FB Lite State:** All devices must be logged into Facebook Lite and be on the 'Select Account' screen (or at least have multiple accounts stored). The app will attempt to log out the current account to reach this screen.\n\n"
            "**How it Works:**\n"
            "The app reads the accounts from the device's file, randomly selects a name, and attempts to find and tap that name on the screen. The auto-type loop cycles through these names one by one."
        )
        messagebox.showinfo(tip_title, tip_message)

    def browse_account_directory(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            global ACCOUNT_DIR
            ACCOUNT_DIR = folder_path
            self.account_dir_path = folder_path
            self._save_config(folder_path)
            self.acc_dir_entry.delete(0, tk.END)
            self.acc_dir_entry.insert(0, os.path.basename(folder_path))
            self._update_status_if_enabled(text=f"✅ ACCOUNT FOLDER SELECTED: {os.path.basename(folder_path)}",
                                           color=self.COLOR_SUCCESS)
            self.acc_status_label.configure(text=f"Folder: {os.path.basename(folder_path)}",
                                            text_color=self.COLOR_TEXT_SECONDARY)
        else:
            self.acc_status_label.configure(text=f"No folder selected.", text_color=self.COLOR_TEXT_SECONDARY)

    def _run_dynamic_tap_by_content_desc(self, serial, content_desc, tap_timeout=5, delay_before=0, delay_after=0):
        if is_stop_requested.is_set():
            return False, "Stop requested."

        local_xml_file = f"ui_dump_{serial}_{uuid.uuid4()}.xml"
        try:
            dump_cmd = ['shell', 'uiautomator', 'dump', '/data/local/tmp/ui.xml']
            success, out = run_adb_command(dump_cmd, serial)
            if not success:
                return False, "Failed to dump UI"

            pull_cmd = ['pull', '/data/local/tmp/ui.xml', local_xml_file]
            success, out = run_adb_command(pull_cmd, serial)
            if not success:
                return False, "Failed to pull UI XML"

            if not os.path.exists(local_xml_file):
                return False, "XML file not found"

            tree = ET.parse(local_xml_file)
            root = tree.getroot()

            xpath_query = f".//node[@content-desc='{content_desc}']"
            xpath_query_fallback = f".//node[@text='{content_desc}']"

            node = root.find(xpath_query)
            if node is None:
                node = root.find(xpath_query_fallback)

            if node is None:
                return False, f"Node with text/desc '{content_desc}' not found in UI dump."

            bounds_str = node.get('bounds')
            if not bounds_str:
                return False, "Found node but bounds are missing."

            coords = re.findall(r'\d+', bounds_str)
            if len(coords) < 4:
                return False, "Invalid bounds string."

            x1, y1, x2, y2 = map(int, coords[:4])
            tap_x = (x1 + x2) // 2
            tap_y = (y1 + y2) // 2

            # Use the new run_tap_command function with delays
            return run_tap_command(serial, tap_x, tap_y, delay_before, delay_after)

        except Exception as e:
            return False, f"Error in dynamic tap: {e}"
        finally:
            if os.path.exists(local_xml_file):
                os.remove(local_xml_file)

    def _run_switch_account_by_name(self, serial, target_account_name):
        if is_stop_requested.is_set():
            return False, "Stop requested"

        # Get timing values from UI
        try:
            tap_delay = float(self.tap_delay_entry.get())
        except ValueError:
            tap_delay = 1.0  # Default if invalid

        try:
            swipe_delay = float(self.swipe_delay_entry.get())
        except ValueError:
            swipe_delay = 1.0  # Default if invalid

        try:
            post_delay = float(self.post_delay_entry.get())
        except ValueError:
            post_delay = 5.0  # Default if invalid

        try:
            # Use the new run_tap_command function
            run_tap_command(serial, 658, 85, 0, tap_delay)
        except:
            pass

        # Use the new run_swipe_command function
        for x in range(3):
            try:
                run_swipe_command(serial, 359, 1233, 372, 176, 500, 0, swipe_delay)
            except:
                pass

        try:
            # Use the new run_tap_command function
            run_tap_command(serial, 172, 1231, 0, tap_delay)

            run_tap_command(serial, 221, 720, 0, tap_delay)

            # Try to find the account
            success, message = self._run_dynamic_tap_by_content_desc(serial, target_account_name, 0, tap_delay)

            # IF ACCOUNT NOT FOUND, SCROLL DOWN 3 TIMES
            if not success:
                self._update_status_if_enabled(
                    text=f"[SWITCH] Account '{target_account_name}' not found. Scrolling down 3 times...",
                    color=self.COLOR_WARNING)

                # Scroll down 3 times using the coordinates you provided
                for i in range(3):
                    if is_stop_requested.is_set():
                        return False, "Stop requested"

                    # Use the new run_swipe_command function
                    success, _ = run_swipe_command(serial, 369, 956, 364, 759, 1000, 0, swipe_delay)

                    # Try to find the account again after each scroll
                    success, message = self._run_dynamic_tap_by_content_desc(serial, target_account_name, 0, tap_delay)
                    if success:
                        break

            if success:
                time.sleep(post_delay)
                return True, f"Successfully switched to '{target_account_name}'"
            else:
                return False, f"Failed to tap account '{target_account_name}' after scrolling. Reason: {message}"

        except Exception as e:
            return False, f"Error during switch sequence on {serial}: {e}"

    def _run_switch_account_adb_commands(self, serial, account_names):
        if is_stop_requested.is_set():
            return False, "Stop requested"

        if not account_names:
            return False, f"No accounts found for device {serial}."

        target_account_name = random.choice(account_names)
        self._update_status_if_enabled(
            text=f"[CMD] Device {serial}: Attempting random switch to '{target_account_name}'...",
            color=self.COLOR_ACCENT)

        return self._run_switch_account_by_name(serial, target_account_name)

    def _threaded_run_switch_account_sequence(self):
        """
        MODIFIED: Now cycles through ALL accounts in the file for each device,
        instead of picking one random account.
        """
        if not self.devices:
            self._update_status_if_enabled(text="⚠️ No devices detected.", color=self.COLOR_WARNING)
            return

        if not self.account_dir_path:
            self._update_status_if_enabled(text="⚠️ Select Account Directory first.", color=self.COLOR_WARNING)
            return

        self._update_status_if_enabled(
            text="[CMD] Starting CYCLICAL SWITCH ACCOUNT sequence on all devices...", color=self.COLOR_ACCENT)

        # Get timing value for the delay between switches. We'll reuse the post_delay.
        try:
            switch_cycle_delay = float(self.post_delay_entry.get())
        except (ValueError, AttributeError):
            switch_cycle_delay = 20  # Default delay of 5 seconds if not set or invalid

        # Loop through each connected device
        for serial in self.devices:
            if is_stop_requested.is_set():
                self._update_status_if_enabled(text="🛑 Account switching stopped by user.", color=self.COLOR_WARNING)
                break

            account_names = read_accounts_for_device(serial)
            if not account_names:
                self._update_status_if_enabled(
                    text=f"❌ Device {serial}: No account file found or file is empty.", color=self.COLOR_DANGER)
                continue

            self._update_status_if_enabled(
                text=f"[CMD] --- Starting cycle for {serial} ({len(account_names)} accounts) ---",
                color=self.COLOR_TEXT_PRIMARY)

            # Loop through EACH account name for the current device
            for i, account_name in enumerate(account_names):
                if is_stop_requested.is_set():
                    self._update_status_if_enabled(text=f"🛑 Stopping cycle for device {serial}.",
                                                   color=self.COLOR_WARNING)
                    break

                self._update_status_if_enabled(
                    text=f"[CMD] {serial} ({i + 1}/{len(account_names)}): Attempting switch to '{account_name}'...",
                    color=self.COLOR_ACCENT)

                # Perform the switch for the specific account
                success, message = self._run_switch_account_by_name(serial, account_name)

                if success:
                    self._update_status_if_enabled(
                        text=f"✅ {serial}: Successfully switched to '{account_name}'.", color=self.COLOR_SUCCESS)
                else:
                    self._update_status_if_enabled(
                        text=f"❌ {serial}: Failed to switch to '{account_name}'. Reason: {message}",
                        color=self.COLOR_DANGER)

                # IMPORTANT: Wait before attempting the next switch for the same device
                # This gives the app time to load and prevents spamming commands.
                if i < len(account_names) - 1:  # No need to wait after the very last account
                    self._update_status_if_enabled(
                        text=f"[SYS] {serial}: Waiting {switch_cycle_delay}s before next switch...",
                        color=self.COLOR_TEXT_SECONDARY)
                    time.sleep(switch_cycle_delay)

        self._update_status_if_enabled(
            text="✅ Account switching cycle completed for all devices.", color=self.COLOR_SUCCESS)

    def _threaded_find_click_type_LOOP(self, valid_pairs):
        try:
            if not self.devices:
                self._update_status_if_enabled(text="⚠️ No devices, stopping loop.", color=self.COLOR_WARNING)
                return

            self.device_account_cycle = {}
            max_accounts = 0
            for serial in self.devices:
                account_names = read_accounts_for_device(serial)
                if account_names:
                    self.device_account_cycle[serial] = {'names': account_names}
                    max_accounts = max(max_accounts, len(account_names))

            if max_accounts == 0 and not valid_pairs:
                self._update_status_if_enabled(text="⚠️ No links or accounts found. Stopping loop.",
                                               color=self.COLOR_WARNING)
                return

            total_successful_posts = 0

            if valid_pairs:
                self._update_status_if_enabled(
                    text="[PHASE 0] Starting INITIAL POST/SHARE with CURRENT accounts...", color=self.COLOR_ACCENT)
                initial_post_success = self._execute_link_posting_phase(self.devices, valid_pairs,
                                                                        is_initial_phase=True)
                if initial_post_success:
                    self._update_status_if_enabled(
                        text=f"✅ PHASE 0 COMPLETE. Initial share successful.", color=self.COLOR_SUCCESS)
                    total_successful_posts += 1
                else:
                    self._update_status_if_enabled(
                        text=f"⚠️ PHASE 0 COMPLETE. No successful posts detected.", color=self.COLOR_WARNING)
                time.sleep(3)

            for cycle_index in range(max_accounts):
                if not self.is_auto_typing.is_set() or is_stop_requested.is_set():
                    self._update_status_if_enabled(text="[SYS] Automation stopped by user.", color=self.COLOR_WARNING)
                    return

                self._update_status_if_enabled(
                    text=f"[CYCLE] Starting Account Set {cycle_index + 1}/{max_accounts}...", color=self.COLOR_ACCENT)

                switch_futures = []
                devices_to_post = []

                for serial, data in self.device_account_cycle.items():
                    if cycle_index < len(data['names']):
                        target_name = data['names'][cycle_index]
                        self._update_status_if_enabled(
                            text=f"[CMD] Device {serial}: Switching to {target_name}...", color=self.COLOR_ACCENT)
                        switch_futures.append(
                            self.executor.submit(self._run_switch_account_by_name, serial, target_name))
                        devices_to_post.append(serial)
                    else:
                        self._update_status_if_enabled(
                            text=f"[CMD] Device {serial}: All accounts processed. Skipping post.",
                            color=self.COLOR_TEXT_SECONDARY)

                concurrent.futures.wait(switch_futures)

                if not devices_to_post:
                    self._update_status_if_enabled(
                        text="[INFO] No active devices with remaining accounts. Ending automation.",
                        color=self.COLOR_WARNING)
                    break

                self._update_status_if_enabled(
                    text=f"[POST] {len(devices_to_post)} devices active. Starting link shares...",
                    color=self.COLOR_ACCENT)

                current_cycle_success = self._execute_link_posting_phase(devices_to_post, valid_pairs,
                                                                         is_initial_phase=False)

                if current_cycle_success:
                    total_successful_posts += 1
                    self._update_status_if_enabled(
                        text=f"✅ Account Set {cycle_index + 1} finished (Success detected). Moving to next.",
                        color=self.COLOR_SUCCESS)
                else:
                    self._update_status_if_enabled(
                        text=f"⚠️ Account Set {cycle_index + 1} finished (No success detected). Moving to next.",
                        color=self.COLOR_WARNING)

                time.sleep(3)

            self._update_status_if_enabled(
                text=f"✅ AUTOMATION COMPLETE. {total_successful_posts} successful post/share runs detected.",
                color=self.COLOR_SUCCESS)

        except Exception as e:
            print(f"Error in auto-type loop: {e}")
            self._update_status_if_enabled(text=f"❌ CRITICAL ERROR: {e}", color=self.COLOR_DANGER)
        finally:
            self.after(0, self.stop_auto_type_loop)

    def _run_task_with_retry(self, serial, text, pair_index, typing_delay, post_delay, tap_delay):
        """
        Helper function to run the text posting task with retry logic.
        """
        if is_stop_requested.is_set():
            return False, "Stop requested"

        try:
            # Use the updated run_text_command with all timing controls
            run_text_command(text, serial, typing_delay, post_delay, tap_delay)
            return True, f"Successfully posted text for pair {pair_index}"
        except Exception as e:
            return False, f"Failed to post text for pair {pair_index}: {str(e)}"

    # --- MODIFIED: Execute Link Posting Phase (Allow No-Caption success AND Tap Post) ---
    def _execute_link_posting_phase(self, devices_to_post, valid_pairs, is_initial_phase=False):
        """
        Runs link sharing.
        MODIFIED: If caption is unchecked, it runs 'run_post_only' which taps the post button.
        """
        current_cycle_success = False

        # --- GET TIMING SETTINGS ---
        try:
            typing_delay = float(self.typing_delay_entry.get())
        except ValueError:
            typing_delay = 20  # Default if invalid

        try:
            post_delay = float(self.post_delay_entry.get())
        except ValueError:
            post_delay = 20  # Default if invalid

        try:
            tap_delay = float(self.tap_delay_entry.get())
        except ValueError:
            tap_delay = 20  # Default if invalid

        for index, selected_pair in enumerate(valid_pairs):
            if not self.is_auto_typing.is_set() or is_stop_requested.is_set():
                return current_cycle_success

            share_url = selected_pair['url']
            file_path = selected_pair['file']
            # FORCE CAPTION CHECK: If file_path is None (checkbox unchecked), has_caption is False.
            has_caption = False
            clean_lines = []

            if file_path and os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    clean_lines = [line.strip() for line in lines if line.strip()]
                    if clean_lines:
                        has_caption = True
                except Exception:
                    pass

            pair_index = index + 1
            total_pairs = len(valid_pairs)

            msg = f"[POST] Pair {pair_index}/{total_pairs}: Sharing {share_url[:20]}..."
            if not has_caption:
                msg += " (No Caption)"

            self._update_status_if_enabled(text=msg, color=self.COLOR_TEXT_PRIMARY)

            # 1. Share URL (MANDATORY)
            share_command = [
                'shell', 'am', 'start',
                '-a', 'android.intent.action.SEND',
                '-t', 'text/plain',
                '--es', 'android.intent.extra.TEXT', f'"{share_url}"',
                'com.facebook.lite'
            ]

            share_futures = []
            for serial in devices_to_post:
                if not self.is_auto_typing.is_set() or is_stop_requested.is_set():
                    break
                share_futures.append(self.executor.submit(run_adb_command, share_command, serial))

            concurrent.futures.wait(share_futures)
            time.sleep(5)  # Wait for share dialogue

            if not self.is_auto_typing.is_set() or is_stop_requested.is_set():
                return current_cycle_success

            # 2. Type Caption (OPTIONAL) OR Just Post
            if has_caption:
                typing_futures = []
                for serial in devices_to_post:
                    if not self.is_auto_typing.is_set() or is_stop_requested.is_set():
                        break
                    random_text = random.choice(clean_lines)
                    # PASS ALL DELAYS HERE
                    typing_futures.append(
                        self.executor.submit(self._run_task_with_retry, serial, random_text, pair_index,
                                             typing_delay, post_delay, tap_delay))

                concurrent.futures.wait(typing_futures)

                # If ANY typing succeeded, mark as success
                if any(f.result()[0] for f in typing_futures if f.exception() is None):
                    current_cycle_success = True
            else:
                # NEW LOGIC: Just Tap Post Button (638, 83)
                self._update_status_if_enabled(
                    text=f"[POST] Pair {pair_index}: No caption needed. Tapping POST button...",
                    color=self.COLOR_ACCENT)

                post_futures = []
                for serial in devices_to_post:
                    if not self.is_auto_typing.is_set() or is_stop_requested.is_set():
                        break
                    # PASS ALL DELAYS HERE
                    post_futures.append(self.executor.submit(run_post_only, serial, post_delay, tap_delay))

                concurrent.futures.wait(post_futures)

                current_cycle_success = True
                self._update_status_if_enabled(
                    text=f"✅ Pair {pair_index}: Posted successfully (Shared + Tapped Post).",
                    color=self.COLOR_SUCCESS)

            # COOLDOWN
            COOLDOWN = 10
            self._update_status_if_enabled(
                text=f"[SYS] Pair {pair_index} processed. Waiting {COOLDOWN}s...",
                color=self.COLOR_TEXT_SECONDARY)

            for _ in range(COOLDOWN):
                if not self.is_auto_typing.is_set() or is_stop_requested.is_set():
                    return current_cycle_success
                time.sleep(1)

        return current_cycle_success

    def enable_airplane_mode(self):
        """Enable airplane mode on all connected devices with timing control."""
        if not self.devices:
            self._update_status_if_enabled(text="⚠️ No devices detected.", color=self.COLOR_WARNING)
            return

        # Get timing values from UI
        try:
            tap_delay = float(self.tap_delay_entry.get())
        except ValueError:
            tap_delay = 20  # Default if invalid

        self._update_status_if_enabled(text="Enabling airplane mode...", color=self.COLOR_ACCENT)

        futures = []
        for serial in self.devices:
            futures.append(self.executor.submit(run_tap_command, serial, 540, 1215, 0, tap_delay))

        concurrent.futures.wait(futures)

        self._update_status_if_enabled(text="✅ Airplane mode enabled.", color=self.COLOR_SUCCESS)

    def disable_airplane_mode(self):
        """Disable airplane mode on all connected devices with timing control."""
        if not self.devices:
            self._update_status_if_enabled(text="⚠️ No devices detected.", color=self.COLOR_WARNING)
            return

        # Get timing values from UI
        try:
            tap_delay = float(self.tap_delay_entry.get())
        except ValueError:
            tap_delay = 20  # Default if invalid

        self._update_status_if_enabled(text="Disabling airplane mode...", color=self.COLOR_ACCENT)

        futures = []
        for serial in self.devices:
            futures.append(self.executor.submit(run_tap_command, serial, 540, 1215, 0, tap_delay))

        concurrent.futures.wait(futures)

        self._update_status_if_enabled(text="✅ Airplane mode disabled.", color=self.COLOR_SUCCESS)

    # ==============================================================================
    # === FUNCTIONAL METHODS (SOME ARE PLACEHOLDERS) ===
    # ==============================================================================

    def stop_all_commands(self):
        self._update_status_if_enabled(text="⚠️ TERMINATING ALL ACTIVE COMMANDS...", color=self.COLOR_WARNING)
        is_stop_requested.set()
        self.stop_auto_type_loop()
        self.executor.shutdown(wait=True)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count() * 4)
        is_stop_requested.clear()
        self._update_status_if_enabled(text="✅ ALL OPERATIONS TERMINATED. Ready.", color=self.COLOR_SUCCESS)

    def detect_devices(self):
        """Detects connected ADB devices and updates the UI."""
        try:
            # Clear current device list
            self.devices.clear()

            # Run 'adb devices' command
            result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, check=True)
            lines = result.stdout.splitlines()

            # Parse the output to get device serial numbers
            for line in lines[1:]:  # Skip the first line ("List of devices attached")
                if '\tdevice' in line:
                    serial_number = line.split('\t')[0]
                    self.devices.append(serial_number)

            # Update UI
            if self.devices:
                self.device_option_menu.configure(values=self.devices)
                self.device_option_menu.set(self.devices[0])
                self.device_option_menu.configure(state="normal")
                self.device_count_label.configure(text=f"DEVICES: {len(self.devices)}")
                self._update_status_if_enabled(text=f"✅ Found {len(self.devices)} device(s).", color=self.COLOR_SUCCESS)
            else:
                self.device_option_menu.configure(values=["No devices found"])
                self.device_option_menu.set("No devices found")
                self.device_option_menu.configure(state="disabled")
                self.device_count_label.configure(text="DEVICES: 0")
                self._update_status_if_enabled(text="⚠️ No devices found. Please check connections and USB debugging.",
                                               color=self.COLOR_WARNING)

        except FileNotFoundError:
            self._update_status_if_enabled(text="❌ ADB not found. Please install it and add to PATH.",
                                           color=self.COLOR_DANGER)
            messagebox.showerror("ADB Error",
                                 "ADB command not found.\nPlease install Android SDK Platform-Tools and ensure 'adb' is in your system's PATH.")
        except subprocess.CalledProcessError as e:
            self._update_status_if_enabled(text=f"❌ Error running adb devices: {e.stderr}", color=self.COLOR_DANGER)
        except Exception as e:
            self._update_status_if_enabled(text=f"❌ An unknown error occurred: {e}", color=self.COLOR_DANGER)

    def on_device_select_menu(self, choice):
        """Handles device selection from the dropdown menu."""
        if choice and choice != "No devices found":
            self.selected_device_serial = choice
            self._update_status_if_enabled(text=f"Selected device: {choice}", color=self.COLOR_ACCENT)
            # Here you would typically start the screen capture for the selected device
            # self.start_capture_for_device(choice)
        else:
            self.selected_device_serial = None
            self.stop_capture()

    def update_app(self):
        def _update_in_thread():
            try:
                self._update_status_if_enabled(text="[SYS] Downloading latest version...", color=self.COLOR_ACCENT)
                response = requests.get(UPDATE_URL)
                response.raise_for_status()
                desktop_path = Path.home() / "Desktop"
                old_file_path = Path(sys.executable) if getattr(sys, 'frozen', False) else Path(sys.argv[0])
                if not old_file_path.is_file():
                    new_file_path = desktop_path / "adb_tool_by_dars.py"
                elif old_file_path.suffix == '.py':
                    new_file_path = old_file_path.parent / old_file_path.name
                else:
                    new_file_path = desktop_path / old_file_path.name
                with open(new_file_path, 'wb') as f:
                    f.write(response.content)
                messagebox.showinfo("Update Complete",
                                    "The new version has been downloaded. The application will now close and update.")
                create_and_run_updater_script(new_file_path, old_file_path)
                self.destroy()
            except Exception as e:
                self._update_status_if_enabled(text=f"❌ ERROR: Update failed: {e}", color=self.COLOR_DANGER)

        threading.Thread(target=_update_in_thread, daemon=True).start()

    def launch_fb_lite(self):
        if not self.devices:
            self._update_status_if_enabled(text="⚠️ No devices detected.", color=self.COLOR_WARNING)
            return
        self._update_status_if_enabled(text=f"[CMD] Launching Facebook Lite...", color=self.COLOR_ACCENT)
        command = ['shell', 'am', 'start', '-n', 'com.facebook.lite/com.facebook.lite.MainActivity']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self._update_status_if_enabled(text="✅ Launched Facebook Lite on all devices.", color=self.COLOR_SUCCESS)

    def force_stop_fb_lite(self):
        if not self.devices:
            self._update_status_if_enabled(text="⚠️ No devices detected.", color=self.COLOR_WARNING)
            return
        self._update_status_if_enabled(text=f"[CMD] Force stopping Facebook Lite...", color=self.COLOR_DANGER)
        command = ['shell', 'am', 'force-stop', 'com.facebook.lite']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self._update_status_if_enabled(text="✅ Force stopped Facebook Lite on all devices.", color=self.COLOR_SUCCESS)

    def open_fb_lite_deeplink(self):
        post_url = self.fb_url_entry.get()
        if not post_url or not self.devices:
            self._update_status_if_enabled(text="⚠️ Check URL and devices.", color=self.COLOR_WARNING)
            return
        self._update_status_if_enabled(text=f"[CMD] Opening FB post URL...", color=self.COLOR_ACCENT)
        command = ['shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', f'"{post_url}"',
                   'com.facebook.lite']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self._update_status_if_enabled(text="✅ Visited FB post on all devices.", color=self.COLOR_SUCCESS)

    def add_share_pair(self, is_initial=False):
        """Adds a new row for a share URL and its corresponding caption file + Checkbox."""
        frame = ctk.CTkFrame(self.share_pair_frame, fg_color=self.COLOR_BACKGROUND, corner_radius=8)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=0)

        # Link Frame
        link_frame = ctk.CTkFrame(frame, fg_color="transparent")
        link_frame.grid(row=0, column=0, columnspan=2, sticky='ew', padx=10, pady=(10, 5))
        link_frame.columnconfigure(0, weight=1)
        link_frame.columnconfigure(1, weight=0)

        share_url_entry = ctk.CTkEntry(link_frame,
                                       placeholder_text=f"Link #{len(self.share_pairs) + 1}: Enter link to share...",
                                       height=35, corner_radius=8, font=self.FONT_BODY)
        share_url_entry.grid(row=0, column=0, sticky='ew', padx=(0, 5))

        if not is_initial:
            remove_button = ctk.CTkButton(link_frame, text="✖️", width=35, height=35, corner_radius=8,
                                          fg_color=self.COLOR_DANGER, hover_color=self.COLOR_DANGER_HOVER,
                                          command=lambda: self.remove_share_pair(frame))
            remove_button.grid(row=0, column=1, sticky='e')

        # Caption Frame
        caption_frame = ctk.CTkFrame(frame, fg_color="transparent")
        caption_frame.grid(row=1, column=0, columnspan=2, sticky='ew', padx=10, pady=(0, 10))
        caption_frame.columnconfigure(0, weight=0)  # Checkbox
        caption_frame.columnconfigure(1, weight=1)  # Entry
        caption_frame.columnconfigure(2, weight=0)  # Browse

        # NEW: Checkbox Variable
        use_caption_var = ctk.BooleanVar(value=True)

        # File Entry
        file_path_entry = ctk.CTkEntry(caption_frame, placeholder_text="Caption File Path: Select a text file...",
                                       height=35, corner_radius=8, font=self.FONT_BODY)

        # Browse Button
        browse_button = ctk.CTkButton(caption_frame, text="BROWSE TXT", corner_radius=8, width=100, height=35,
                                      fg_color=self.COLOR_BORDER, hover_color=self.COLOR_TEXT_SECONDARY,
                                      font=self.FONT_BUTTON,
                                      command=lambda: self.browse_share_pair_file(target_entry=file_path_entry))

        # Function to toggle entry state
        def toggle_caption_state():
            if use_caption_var.get():
                file_path_entry.configure(state="normal", fg_color=["#F9F9FA", "#343638"])  # Standard colors
                browse_button.configure(state="normal", fg_color=self.COLOR_BORDER)
            else:
                # FIX: CTkEntry cannot be "transparent". Use self.COLOR_FRAME (background color) instead.
                file_path_entry.configure(state="disabled", fg_color=self.COLOR_FRAME)
                browse_button.configure(state="disabled", fg_color="transparent")

        # Checkbox
        checkbox = ctk.CTkCheckBox(caption_frame, text="With Caption?", variable=use_caption_var,
                                   command=toggle_caption_state, font=self.FONT_BODY, width=120)
        checkbox.grid(row=0, column=0, sticky='w', padx=(0, 10))

        file_path_entry.grid(row=0, column=1, sticky='ew', padx=(0, 5))
        browse_button.grid(row=0, column=2, sticky='e')

        self.share_pairs.append({
            'frame': frame,
            'url_entry': share_url_entry,
            'file_entry': file_path_entry,
            'use_caption_var': use_caption_var  # Store the var
        })
        frame.pack(fill='x', padx=5, pady=5)
        self.share_pair_frame.update_idletasks()

    def _threaded_send_text(self):
        file_paths = []
        for pair in self.share_pairs:
            # Only include enabled captions
            if pair['use_caption_var'].get():
                file_path = pair['file_entry'].get()
                if file_path and os.path.exists(file_path):
                    file_paths.append(file_path)

        if not file_paths:
            self._update_status_if_enabled(text="⚠️ No valid text files found (check if 'With Caption' is checked).",
                                           color=self.COLOR_WARNING)
            return

        if not self.devices:
            self._update_status_if_enabled(text="⚠️ No devices detected.", color=self.COLOR_WARNING)
            return

        random_file_path = random.choice(file_paths)
        try:
            with open(random_file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            clean_lines = [line.strip() for line in lines if line.strip()]

            if not clean_lines:
                return

            self._update_status_if_enabled(
                text=f"[CMD] Sending random text from '{os.path.basename(random_file_path)}'...",
                color=self.COLOR_ACCENT)

            for device_serial in self.devices:
                random_text = random.choice(clean_lines)
                self.executor.submit(run_text_command, random_text, device_serial)
            self._update_status_if_enabled(text=f"✅ Text commands submitted.", color=self.COLOR_SUCCESS)
        except Exception as e:
            self._update_status_if_enabled(text=f"❌ ERROR: {e}", color=self.COLOR_DANGER)

    def send_text_to_devices(self):
        threading.Thread(target=self._threaded_send_text, daemon=True).start()

    def remove_emojis_from_file(self):
        if not self.share_pairs:
            self._update_status_if_enabled(text="⚠️ Please add a Link/Caption Pair first.", color=self.COLOR_WARNING)
            return

        file_path = self.share_pairs[0]['file_entry'].get()
        if not file_path:
            self._update_status_if_enabled(text="⚠️ Please select a text file for the first pair.",
                                           color=self.COLOR_WARNING)
            return

        try:
            emoji_pattern = re.compile("["
                                       "\U0001F600-\U0001F64F"
                                       "\U0001F300-\U0001F5FF"
                                       "\U0001F680-\U0001F6FF"
                                       "\U0001F700-\U0001F77F"
                                       "\U0001F780-\U0001F7FF"
                                       "\U0001F800-\U0001F8FF"
                                       "\U0001F900-\U0001F9FF"
                                       "\U0001FA00-\U0001FA6F"
                                       "\U0001FA70-\U0001FAFF"
                                       "\U00002702-\U000027B0"
                                       "\U00002600-\U000026FF"
                                       "\U000025A0-\U000025FF"
                                       "]+", flags=re.UNICODE)

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            cleaned_content = emoji_pattern.sub(r'', content)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(cleaned_content)

            self._update_status_if_enabled(text=f"✅ EMOJIS REMOVED from file: {os.path.basename(file_path)}.",
                                           color=self.COLOR_SUCCESS)

        except FileNotFoundError:
            self._update_status_if_enabled(text="❌ ERROR: File not found.", color=self.COLOR_DANGER)
        except Exception as e:
            self._update_status_if_enabled(text=f"❌ ERROR: An error occurred: {e}", color=self.COLOR_DANGER)

    def detect_devices(self):
        self.stop_capture()
        for widget in self.device_view_panel.winfo_children():
            widget.destroy()

        self.device_frames = {}
        self.device_canvases = {}
        self.device_images = {}
        self.press_start_coords = {}
        self.press_time = {}
        self.selected_device_serial = None
        self.devices = []
        self._update_status_if_enabled(text="[SYS] Detecting devices...", color=self.COLOR_ACCENT)

        try:
            result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, check=True, timeout=10)
            devices_output = result.stdout.strip().split('\n')[1:]
            self.devices = [line.split('\t')[0] for line in devices_output if line.strip() and 'device' in line]
        except Exception:
            self.device_count_label.configure(text="DEVICES: 0")
            self.device_option_menu.configure(values=["No devices found"], state="disabled")
            self.device_selector_var.set("No devices found")
            return

        self.device_count_label.configure(text=f"DEVICES: {len(self.devices)}")

        if not self.devices:
            no_devices_label = ctk.CTkLabel(self.device_view_panel,
                                            text="NO DEVICES FOUND.\nEnsure USB debugging is enabled.",
                                            font=self.FONT_HEADING, text_color=self.COLOR_TEXT_SECONDARY)
            no_devices_label.pack(expand=True)
            self._update_status_if_enabled(text="⚠️ No devices detected.", color=self.COLOR_WARNING)
            self.device_option_menu.configure(values=["No devices found"], state="disabled")
            self.device_selector_var.set("No devices found")
        else:
            self._update_status_if_enabled(text=f"✅ {len(self.devices)} devices connected.", color=self.COLOR_SUCCESS)
            self.device_option_menu.configure(values=self.devices, state="normal")
            self.device_selector_var.set(self.devices[0])
            self.on_device_select_menu(self.devices[0])

    def on_device_select_menu(self, selected_serial):
        if not selected_serial or selected_serial == "No devices found":
            return
        self.stop_capture()
        self.selected_device_serial = selected_serial
        for widget in self.device_view_panel.winfo_children():
            widget.destroy()
        self.device_frames = {}
        self.device_canvases = {}
        self.device_images = {}
        self.press_start_coords = {}
        self.press_time = {}
        self.create_device_frame(self.selected_device_serial)
        self.start_capture_process()

    def stop_capture(self):
        self.is_capturing = False
        if self.update_image_id:
            self.after_cancel(self.update_image_id)
            self.update_image_id = None
        self.screenshot_queue.queue.clear()

    def start_capture_process(self):
        if self.is_capturing:
            return
        self.is_capturing = True
        self.capture_thread = threading.Thread(target=self.capture_screen_loop, daemon=True)
        self.capture_thread.start()
        self.update_image_id = self.after(100, self.update_image)

    def capture_screen_loop(self):
        while self.is_capturing:
            try:
                if not self.selected_device_serial:
                    self.is_capturing = False
                    break
                process = subprocess.run(['adb', '-s', self.selected_device_serial, 'exec-out', 'screencap', '-p'],
                                         capture_output=True, check=True, timeout=5)
                self.screenshot_queue.put(process.stdout)
            except Exception:
                self.is_capturing = False

    def update_image(self):
        try:
            if not self.selected_device_serial or not self.is_capturing:
                return
            canvas = self.device_canvases.get(self.selected_device_serial)
            if not canvas or not canvas.winfo_exists():
                return
            if not self.screenshot_queue.empty():
                image_data = self.screenshot_queue.get()
                pil_image = Image.open(io.BytesIO(image_data))
                canvas_width = canvas.winfo_width()
                canvas_height = canvas.winfo_height()
                if canvas_width > 0 and canvas_height > 0:
                    img_width, img_height = pil_image.size
                    aspect_ratio = img_width / img_height
                    if canvas_width / canvas_height > aspect_ratio:
                        new_height = canvas_height
                        new_width = int(new_height * aspect_ratio)
                    else:
                        new_width = canvas_width
                        new_height = int(new_width / aspect_ratio)
                    if new_width > 0 and new_height > 0:
                        resized_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                        tk_image = ImageTk.PhotoImage(resized_image)
                        self.device_images[self.selected_device_serial] = {'pil_image': pil_image, 'tk_image': tk_image}
                        x_pos = canvas_width / 2
                        y_pos = canvas_height / 2
                        if 'item_id' in self.device_images.get(self.selected_device_serial, {}):
                            image_item_id = self.device_images[self.selected_device_serial]['item_id']
                            canvas.coords(image_item_id, x_pos, y_pos)
                            canvas.itemconfig(image_item_id, image=tk_image)
                        else:
                            image_item_id = canvas.create_image(x_pos, y_pos, image=tk_image)
                            self.device_images[self.selected_device_serial]['item_id'] = image_item_id
                            canvas.itemconfig(image_item_id, anchor=tk.CENTER)
            if self.is_capturing:
                self.update_image_id = self.after(100, self.update_image)
        except Exception:
            self.stop_capture()

    def create_device_frame(self, serial):
        device_frame = ctk.CTkFrame(self.device_view_panel, fg_color="transparent")
        device_frame.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)
        self.device_frames[serial] = device_frame

        title = ctk.CTkLabel(device_frame, text=f"LIVE CONTROL: {serial}", font=self.FONT_HEADING,
                             text_color=self.COLOR_ACCENT)
        title.pack(pady=(0, 10))

        canvas_container = ctk.CTkFrame(device_frame, fg_color=self.COLOR_FRAME, corner_radius=8,
                                        border_width=1, border_color=self.COLOR_BORDER)
        canvas_container.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        canvas_container.bind("<Configure>", self.on_canvas_container_resize)

        canvas = tk.Canvas(canvas_container, bg=self.COLOR_FRAME, highlightthickness=0)
        canvas.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self.device_canvases[serial] = canvas

        canvas.bind("<ButtonPress-1>", lambda event: self.start_press(event, serial))
        canvas.bind("<ButtonRelease-1>", lambda event: self.handle_release(event, serial))

        button_frame = ctk.CTkFrame(device_frame, fg_color="transparent")
        button_frame.pack(pady=(15, 0), fill="x")
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        button_frame.columnconfigure(2, weight=1)
        button_frame.columnconfigure(3, weight=1)
        button_frame.columnconfigure(4, weight=1)
        button_frame.columnconfigure(5, weight=1)

        button_style = {'corner_radius': 8, 'width': 100,
                        'fg_color': self.COLOR_FRAME,
                        'hover_color': self.COLOR_BORDER,
                        'text_color': self.COLOR_TEXT_PRIMARY,
                        'border_color': self.COLOR_BORDER, 'border_width': 1,
                        'height': 40, 'font': self.FONT_BUTTON}
        button_padx = 4

        ctk.CTkButton(button_frame, text="HOME 🏠", command=lambda: self.send_adb_keyevent(3),
                      **button_style).grid(row=0, column=0, padx=button_padx, sticky="ew")
        ctk.CTkButton(button_frame, text="BACK ↩️", command=lambda: self.send_adb_keyevent(4),
                      **button_style).grid(row=0, column=1, padx=button_padx, sticky="ew")
        ctk.CTkButton(button_frame, text="RECENTS", command=lambda: self.send_adb_keyevent(187),
                      **button_style).grid(row=0, column=2, padx=button_padx, sticky="ew")
        ctk.CTkButton(button_frame, text="SCROLL DOWN",
                      command=lambda: self.send_adb_swipe(serial, 'up'), **button_style).grid(row=0, column=3,
                                                                                              padx=button_padx,
                                                                                              sticky="ew")
        ctk.CTkButton(button_frame, text="SCROLL UP",
                      command=lambda: self.send_adb_swipe(serial, 'down'), **button_style).grid(row=0, column=4,
                                                                                                padx=button_padx,
                                                                                                sticky="ew")
        ctk.CTkButton(button_frame, text="SCREEN OFF 💡", command=lambda: self.send_adb_keyevent(26),
                      corner_radius=8, width=100, fg_color=self.COLOR_DANGER,
                      hover_color=self.COLOR_DANGER_HOVER,
                      text_color=self.COLOR_TEXT_PRIMARY, height=40, font=self.FONT_BUTTON).grid(row=0, column=5,
                                                                                                 padx=button_padx,
                                                                                                 sticky="ew")

    def on_canvas_container_resize(self, event):
        if not self.selected_device_serial:
            return
        canvas = self.device_canvases.get(self.selected_device_serial)
        if not canvas:
            return
        container_width = event.width
        container_height = event.height
        aspect_ratio = 9 / 16
        if container_width / container_height > aspect_ratio:
            new_height = container_height
            new_width = int(new_height * aspect_ratio)
        else:
            new_width = container_width
            new_height = int(new_width / aspect_ratio)
        canvas.configure(width=new_width, height=new_height)
        canvas.place(relx=0.5, rely=0.5, anchor=tk.CENTER, width=new_width, height=new_height)
        self.after(10, self.update_image)

    def start_press(self, event, serial):
        self.press_time[serial] = time.time()
        self.press_start_coords[serial] = (event.x, event.y)

    def handle_release(self, event, serial):
        end_time = time.time()
        start_time = self.press_time.get(serial)
        if not start_time:
            return
        duration = end_time - start_time
        start_x, start_y = self.press_start_coords.get(serial, (event.x, event.y))
        end_x, end_y = (event.x, event.y)
        distance = ((end_x - start_x) ** 2 + (end_y - start_y) ** 2) ** 0.5
        if distance > self.drag_threshold:
            self.send_adb_swipe_command(start_x, start_y, end_x, end_y, serial)
        elif duration > self.long_press_duration:
            self.send_adb_long_press(event, serial)
        else:
            self.send_adb_tap(event, serial)
        self.press_time.pop(serial, None)
        self.press_start_coords.pop(serial, None)

    def _get_scaled_coords(self, canvas_x, canvas_y, serial):
        pil_image_info = self.device_images.get(self.selected_device_serial, {})
        pil_image = pil_image_info.get('pil_image')
        if not pil_image:
            return None, None
        img_width, img_height = pil_image.size
        canvas = self.device_canvases[serial]
        canvas_width = canvas.winfo_width()
        canvas_height = canvas.winfo_height()
        canvas_aspect = canvas_width / canvas_height
        image_aspect = img_width / img_height
        if canvas_aspect > image_aspect:
            effective_height = canvas_height
            effective_width = int(effective_height * image_aspect)
        else:
            effective_width = canvas_width
            effective_height = int(effective_width / image_aspect)
        image_x_offset = (canvas_width - effective_width) // 2
        image_y_offset = (canvas_height - effective_height) // 2
        click_x = canvas_x - image_x_offset
        click_y = canvas_y - image_y_offset
        if not (0 <= click_x < effective_width and 0 <= click_y < effective_height):
            return None, None
        try:
            adb_size_output = subprocess.run(['adb', '-s', serial, 'shell', 'wm', 'size'], capture_output=True,
                                             text=True, check=True, timeout=5).stdout.strip()
            adb_width, adb_height = map(int, adb_size_output.split()[-1].split('x'))
        except Exception:
            return None, None
        scaled_x = int(click_x * adb_width / effective_width)
        scaled_y = int(click_y * adb_height / effective_height)
        return scaled_x, scaled_y

    def send_adb_tap(self, event, serial):
        scaled_x, scaled_y = self._get_scaled_coords(event.x, event.y, serial)
        if scaled_x is None:
            return
        command = ['shell', 'input', 'tap', str(scaled_x), str(scaled_y)]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)

    def send_adb_long_press(self, event, serial):
        scaled_x, scaled_y = self._get_scaled_coords(event.x, event.y, serial)
        if scaled_x is None:
            return
        command = ['shell', 'input', 'swipe', str(scaled_x), str(scaled_y), str(scaled_x), str(scaled_y), '1000']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)

    def send_adb_swipe_command(self, start_x, start_y, end_x, end_y, serial):
        scaled_start_x, scaled_start_y = self._get_scaled_coords(start_x, start_y, serial)
        scaled_end_x, scaled_end_y = self._get_scaled_coords(end_x, end_y, serial)
        if scaled_start_x is None or scaled_end_x is None:
            return
        command = ['shell', 'input', 'swipe', str(scaled_start_x), str(scaled_start_y), str(scaled_end_x),
                   str(scaled_end_y), '300']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)

    def send_adb_swipe(self, serial, direction):
        try:
            adb_width_str = subprocess.run(['adb', '-s', serial, 'shell', 'wm', 'size'], capture_output=True, text=True,
                                           check=True).stdout.strip().split()[-1]
            adb_width, adb_height = map(int, adb_width_str.split('x'))
            if direction == 'down':
                start_x, start_y = adb_width // 2, adb_height // 4 * 3
                end_x, end_y = start_x, adb_height // 4
            elif direction == 'up':
                start_x, start_y = adb_width // 2, adb_height // 4
                end_x, end_y = start_x, adb_height // 4 * 3
            command = ['shell', 'input', 'swipe', str(start_x), str(start_y), str(end_x), str(end_y), '300']
            for device_serial in self.devices:
                self.executor.submit(run_adb_command, command, device_serial)
        except Exception:
            pass

    def send_adb_keyevent(self, keycode):
        command = ['shell', 'input', 'keyevent', str(keycode)]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)

    def start_auto_type_loop(self):
        if self.is_auto_typing.is_set():
            return

        valid_pairs = []
        for pair in self.share_pairs:
            share_url = pair['url_entry'].get()

            # Check the Checkbox state!
            use_caption = pair['use_caption_var'].get()
            file_path = pair['file_entry'].get()

            if share_url:
                # If unchecked, set file to None so logic knows not to look for it
                final_file_path = file_path if use_caption else None
                valid_pairs.append({'url': share_url, 'file': final_file_path, 'use_caption': use_caption})

        if not valid_pairs:
            self._update_status_if_enabled(text="⚠️ No valid Links found.", color=self.COLOR_WARNING)
            return

        if not self.devices:
            self._update_status_if_enabled(text="⚠️ No devices detected.", color=self.COLOR_WARNING)
            return

        self.is_auto_typing.set()
        self.find_click_type_button.configure(text="STOP AUTO-TYPE 🛑",
                                              fg_color=self.COLOR_DANGER,
                                              hover_color=self.COLOR_DANGER_HOVER,
                                              text_color=self.COLOR_TEXT_PRIMARY)
        self._update_status_if_enabled(text="[CMD] Auto-type loop STARTED.", color=self.COLOR_SUCCESS)
        threading.Thread(target=self._threaded_find_click_type_LOOP, args=(valid_pairs,), daemon=True).start()

    def stop_auto_type_loop(self):
        self.is_auto_typing.clear()
        if hasattr(self, 'find_click_type_button') and self.find_click_type_button.winfo_exists():
            self.find_click_type_button.configure(text="START AUTO-TYPE ⌨️",
                                                  fg_color=self.COLOR_ACCENT,
                                                  hover_color=self.COLOR_ACCENT_HOVER,
                                                  text_color=self.COLOR_BACKGROUND)
    def toggle_auto_type_loop(self):
        if self.is_auto_typing.is_set():
            self.stop_auto_type_loop()
        else:
            self.start_auto_type_loop()

    def browse_apk_file(self):
        file_path = filedialog.askopenfilename(defaultextension=".apk", filetypes=[("APK files", "*.apk")])
        if file_path:
            self.apk_path = file_path
            self.apk_path_entry.delete(0, tk.END)
            self.apk_path_entry.insert(0, os.path.basename(file_path))
            self._update_status_if_enabled(text=f"✅ APK SELECTED: {os.path.basename(file_path)}",
                                           color=self.COLOR_SUCCESS)

    def install_apk_to_devices(self):
        if not self.apk_path or not os.path.exists(self.apk_path):
            self._update_status_if_enabled(text="⚠️ Please select a valid APK file first.", color=self.COLOR_WARNING)
            return
        if not self.devices:
            self._update_status_if_enabled(text="⚠️ No devices detected.", color=self.COLOR_WARNING)
            return
        self._update_status_if_enabled(text=f"[CMD] Installing {os.path.basename(self.apk_path)}...",
                                       color=self.COLOR_ACCENT)
        command = ['install', '-r', self.apk_path]

        def _install_task(serial):
            return run_adb_command(command, serial)

        futures = [self.executor.submit(_install_task, serial) for serial in self.devices]
        concurrent.futures.wait(futures)
        if all(f.result()[0] for f in futures):
            self._update_status_if_enabled(text="✅ APK INSTALL SUCCESSFUL.", color=self.COLOR_SUCCESS)
        else:
            self._update_status_if_enabled(text=f"❌ INSTALLATION FAILED on some devices.", color=self.COLOR_DANGER)

    def share_image_to_fb_lite(self):
        file_name = self.image_file_name_entry.get()
        if not file_name or not self.devices:
            self._update_status_if_enabled(text="⚠️ Check image filename and devices.", color=self.COLOR_WARNING)
            return
        self._update_status_if_enabled(text=f"[CMD] Sending sharing intent for '{file_name}'...",
                                       color=self.COLOR_ACCENT)
        device_path = f'/sdcard/Download/{file_name}'
        command = ['shell', 'am', 'start', '-a', 'android.intent.action.SEND', '-t', 'image/jpeg',
                   '--eu', 'android.intent.extra.STREAM', f'file://{device_path}', 'com.facebook.lite']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self._update_status_if_enabled(text="✅ Image sharing command sent to all devices.", color=self.COLOR_SUCCESS)

    def stop_capture(self):
        self.is_capturing = False
        if self.update_image_id:
            self.after_cancel(self.update_image_id)
            self.update_image_id = None
        self.screenshot_queue.queue.clear()

if __name__ == "__main__":
    app = AdbControllerApp()
    app.mainloop()
