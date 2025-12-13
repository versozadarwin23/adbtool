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
__version__ = "9"  # Updated version number
UPDATE_URL = "https://raw.githubusercontent.com/versozadarwin23/adbtool/refs/heads/main/main.py"
VERSION_CHECK_URL = "https://raw.githubusercontent.com/versozadarwin23/adbtool/refs/heads/main/version.txt"

# --- Global Flag for Stopping Commands ---
is_stop_requested = threading.Event()


def run_adb_command(command, serial):
    """
    Executes a single ADB command for a specific device with a timeout, checking for a stop signal.

    Returns: (bool success, str output_or_error)
    """
    if is_stop_requested.is_set():
        # print(f"🛑 Stop signal received. Aborting command on device {serial}.")
        return False, "Stop requested."

    try:
        # Popen is used to allow non-blocking check for stop signal
        process = subprocess.Popen(['adb', '-s', serial] + command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Wait for the command to finish or for a stop signal
        timeout_seconds = 60
        start_time = time.time()
        while process.poll() is None and (time.time() - start_time < timeout_seconds):
            if is_stop_requested.is_set():
                process.terminate()  # Use terminate to kill the process
                # print(f"🛑 Terminated ADB command on device {serial}.")
                return False, "Terminated due to stop request."
            # time.sleep(0.1)  # Small delay to reduce CPU usage

        if process.poll() is None:
            process.terminate()
            # Terminate the process if it timed out and raise the error
            raise subprocess.TimeoutExpired(cmd=['adb', '-s', serial] + command, timeout=timeout_seconds)

        stdout, stderr = process.communicate()

        if process.returncode != 0:
            # print(f"❌ Error executing command on device {serial}: {stderr.decode()}")
            return False, stderr.decode()
        else:
            # print(f"✅ Command executed on device {serial}: {' '.join(command)}")
            return True, stdout.decode()

    except subprocess.CalledProcessError as e:
        # print(f"❌ Error executing command on device {serial}: {e.stderr.decode()}")
        return False, e.stderr.decode()
    except FileNotFoundError:
        # print(f"❌ ADB not found. Please install it and add to PATH.")
        return False, "ADB not found. Please install it and add to PATH."
    except subprocess.TimeoutExpired:
        # print(f"❌ Command timed out on device {serial}")
        return False, "Command timed out."
    except Exception as e:
        # print(f"❌ General error on device {serial}: {e}")
        return False, str(e)


def run_text_command(text_to_send, serial):
    """
    Sends a specific text string character-by-character with delay and proper space escaping.
    MODIFIED: Removed initial string pre-escaping; now escapes only spaces inside the loop.
    """
    if is_stop_requested.is_set():
        # print(f"🛑 Stop signal received. Aborting text command on device {serial}.")
        return

    if not text_to_send:
        # print(f"Text is empty. Cannot send command to {serial}.")
        return

    # --- SIMULA NG FIX: Gamitin ang orihinal na text para sa iteration ---
    formatted_text = text_to_send  # Ito ang orihinal na text (e.g., "salamat doc")
    DELAY_PER_CHAR = 0.02

    try:
        # Ulitin ang bawat letra sa formatted_text
        for char in formatted_text:
            if is_stop_requested.is_set():
                # print(f"🛑 Stop signal received. Aborting text command on device {serial}.")
                return

            # I-escape ang space character lang sa loob ng loop (space -> %s)
            adb_char = char.replace(' ', '%s')

            # 1. Mag-type ng isang letra gamit ang bagong istraktura
            command_args = ['shell', 'input', 'text', adb_char]

            # Synchronous execution with reduced timeout (5 seconds)
            subprocess.run(['adb', '-s', serial] + command_args,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           check=True,
                           timeout=5)

            # 2. Maghintay (Delay) bago i-type ang susunod na letra
            time.sleep(DELAY_PER_CHAR)

        # --- WAKAS NG FIX ---

        # --- MGA SUMUSUNOD NA COMMAND (CLICK) ---

        # Hihintay ng isang segundo para masigurong tapos na ang pag-type (optional, but safer)
        time.sleep(1.0)

        if is_stop_requested.is_set():
            # print(f"🛑 Stop signal received. Aborting tap command on device {serial}.")
            return

        # Mga coordinate mula sa iyong request: [592,61][685,106]
        x1, y1 = 592, 61
        x2, y2 = 685, 106

        # Kalkulahin ang gitna
        tap_x = (x1 + x2) // 2  # Resulta: 638
        tap_y = (y1 + y2) // 2  # Resulta: 83

        # Ipadala ang tap command
        tap_cmd = ['shell', 'input', 'tap', str(tap_x), str(tap_y)]
        subprocess.run(['adb', '-s', serial] + tap_cmd,
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,
                       check=True,
                       timeout=60)
        # print(f"✅ Clicked post button on device {serial}.")

    except Exception as e:
        # print(f"An error occurred on device {serial}: {e}")
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


# --- AdbControllerApp Class ---
class AdbControllerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Configuration ---
        self.title(f"ADB Commander By Dars: V{__version__}")
        self.geometry("1400x900")
        self.state('zoomed')
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # --- NEW Professional Color Palette (GitHub-inspired) ---
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

        # --- NEW Standardized Fonts ---
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

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count() * 4)

        # --- Main Window Grid Configuration ---
        # Column 0: Control Panel (Fixed min-width, weight 1)
        # Column 1: Device View (Expands, weight 3)
        self.grid_columnconfigure(0, weight=1, minsize=480)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.configure(fg_color=self.COLOR_BACKGROUND)

        # --- [LEFT] Control Panel Setup ---
        self.control_panel = ctk.CTkFrame(self, corner_radius=0, fg_color=self.COLOR_FRAME)
        self.control_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 1), pady=0)

        # Configure Control Panel Grid (Tabs expand, Status Bar docks bottom)
        self.control_panel.grid_columnconfigure(0, weight=1)
        self.control_panel.grid_rowconfigure(4, weight=1)  # Tab view row
        self.control_panel.grid_rowconfigure(5, weight=0)  # Status bar row

        # --- Row 0: Title ---
        ctk.CTkLabel(self.control_panel, text=f"ADB COMMANDER V{__version__}",
                     font=self.FONT_TITLE,
                     text_color=self.COLOR_ACCENT).grid(
            row=0, column=0, pady=(20, 10), padx=20, sticky='w')

        # --- Row 1: Global Stop Button ---
        self.stop_all_button = ctk.CTkButton(self.control_panel, text="🛑 TERMINATE ALL OPERATIONS 🛑",
                                             command=self.stop_all_commands,
                                             fg_color=self.COLOR_DANGER,
                                             hover_color=self.COLOR_DANGER_HOVER,
                                             text_color=self.COLOR_TEXT_PRIMARY,
                                             corner_radius=8,
                                             font=self.FONT_HEADING, height=50)
        self.stop_all_button.grid(row=1, column=0, sticky='ew', padx=20, pady=10)

        # --- Row 2: Device Management Frame ---
        device_mgmt_frame = ctk.CTkFrame(self.control_panel, fg_color="transparent")
        device_mgmt_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(10, 5))
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

        # --- Row 3: Device Selection (Replaces Listbox) ---
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

        # --- Row 4: Tab View ---
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

        # --- MODIFIED TABS ---
        self.tab_view.add("Facebook Automation")
        self.tab_view.add("Utilities")
        self.tab_view.set("Facebook Automation")  # Start on the main tab
        # --- END MODIFIED TABS ---

        self._configure_tab_layouts()

        # --- Row 5: Status Bar (Docked Bottom) ---
        self.status_label = ctk.CTkLabel(self.control_panel, text="Awaiting Command...", anchor='w',
                                         font=self.FONT_STATUS, text_color=self.COLOR_TEXT_SECONDARY, height=30,
                                         fg_color=self.COLOR_FRAME)
        self.status_label.grid(row=5, column=0, sticky='sew', padx=20, pady=(5, 10))

        # --- [RIGHT] Device View Panel Setup ---
        self.device_view_panel = ctk.CTkFrame(self, fg_color=self.COLOR_BACKGROUND, corner_radius=0)
        self.device_view_panel.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.device_view_panel.grid_columnconfigure(0, weight=1)
        self.device_view_panel.grid_rowconfigure(0, weight=1)

        # --- Initial Setup ---
        self.detect_devices()
        self.check_for_updates()
        self.start_periodic_update_check()

    # --- Section Helper for Professional Look ---
    def _create_section_header(self, parent, text, row):
        """Creates a standardized, styled section header."""
        ctk.CTkLabel(parent, text=text,
                     font=self.FONT_HEADING, text_color=self.COLOR_ACCENT).grid(
            row=row, column=0, sticky='w', padx=15, pady=(15, 5))

    def _create_section_frame(self, parent, row):
        """Creates a standardized frame for grouping widgets."""
        frame = ctk.CTkFrame(parent, fg_color=self.COLOR_FRAME, corner_radius=8,
                             border_width=1, border_color=self.COLOR_BORDER)
        frame.grid(row=row, column=0, sticky='ew', padx=15, pady=5)
        frame.grid_columnconfigure(0, weight=1)
        return frame

    # --- NEW METHOD: Setup periodic update check
    def start_periodic_update_check(self):
        """Starts a recurring, silent update check every 60 seconds (60000 ms)."""
        # 60000 milliseconds = 1 minute
        self.update_check_job = self.after(60000, self._periodic_check_updates)

    def _periodic_check_updates(self):
        """Internal method called periodically to silently check for updates."""
        # We run the check in a thread to keep the GUI responsive
        threading.Thread(target=self._check_and_reschedule, daemon=True).start()

    def _check_and_reschedule(self):
        """Internal method called periodically to check for updates and reschedules the next check."""
        try:
            # Only perform the actual network check. Do not update the status label unless an error occurs or an update is found.
            response = requests.get(VERSION_CHECK_URL, timeout=10)
            response.raise_for_status()

            latest_version = response.text.strip()

            # --- Gumamit ng numeric comparison para maiwasan ang recurring popup bug ---
            try:
                # Convert to float for robust numeric comparison (handles 1.0 vs 1.1 safely)
                local_v = float(__version__)
                remote_v = float(latest_version)

                if remote_v > local_v:
                    # Only show prompt if a new version is available
                    self.after(0, self.ask_for_update, latest_version)
            except ValueError:
                # Fallback to string comparison if version contains non-numeric chars (e.g., '1-beta')
                if latest_version > __version__:
                    # Only show prompt if a new version is available
                    self.after(0, self.ask_for_update, latest_version)
            # --- WAKAS NG FIX ---

        except requests.exceptions.RequestException:
            # Errors are expected occasionally (e.g., no internet/server down).
            pass
        except Exception:
            pass
        finally:
            # Reschedule itself regardless of success or failure
            self.update_check_job = self.after(60000, self._periodic_check_updates)

    def check_for_updates(self):
        """
        Modified existing check_for_updates to only run once on startup
        and handle errors/messages explicitly.
        """

        def _check_in_thread():
            try:
                # Use a slightly longer timeout for version check
                response = requests.get(VERSION_CHECK_URL, timeout=10)
                response.raise_for_status()  # Raise HTTPError for bad status codes (4xx or 5xx)

                latest_version = response.text.strip()

                # --- Gumamit ng numeric comparison para maiwasan ang recurring popup bug ---
                try:
                    # Convert to float for robust numeric comparison (handles 1.0 vs 1.1 safely)
                    local_v = float(__version__)
                    remote_v = float(latest_version)

                    if remote_v > local_v:
                        self.after(0, self.ask_for_update, latest_version)
                except ValueError:
                    # Fallback to string comparison if version contains non-numeric chars (e.g., '1-beta')
                    if latest_version > __version__:
                        self.after(0, self.ask_for_update, latest_version)
                # --- WAKAS NG FIX ---

            except requests.exceptions.HTTPError as http_err:
                status_code = http_err.response.status_code
                self.after(0, lambda: self.status_label.configure(
                    text=f"❌ ERROR: Failed to check for update. HTTP Status: {status_code}",
                    text_color=self.COLOR_DANGER))
                self.after(0, lambda: messagebox.showwarning(
                    "Update Check Failed",
                    f"Unable to reach the update server (HTTP Error {status_code}). Check your network or firewall settings."))
            except requests.exceptions.ConnectionError:
                self.after(0, lambda: self.status_label.configure(
                    text="❌ ERROR: Failed to check for update. Connection Refused.",
                    text_color=self.COLOR_DANGER))
                self.after(0, lambda: messagebox.showwarning(
                    "Update Check Failed",
                    "Cannot connect to the update server. Check your internet connection, firewall, or proxy."))
            except requests.exceptions.Timeout:
                self.after(0, lambda: self.status_label.configure(
                    text="❌ ERROR: Failed to check for update. Connection Timed Out.",
                    text_color=self.COLOR_DANGER))
                self.after(0, lambda: messagebox.showwarning(
                    "Update Check Failed",
                    "The connection timed out while checking for updates. Your network might be slow or unstable."))
            except requests.exceptions.RequestException as e:
                self.after(0, lambda: self.status_label.configure(
                    text=f"❌ ERROR: Failed to check for update. Details: {e.__class__.__name__}",
                    text_color=self.COLOR_DANGER))
                self.after(0, lambda: messagebox.showwarning(
                    "Update Check Failed",
                    f"An error occurred during update check: {e.__class__.__name__}. Check logs for details."))
            except Exception:
                # Catch all other unexpected errors
                self.after(0, lambda: self.status_label.configure(
                    text="❌ ERROR: An unexpected error occurred during version check.",
                    text_color=self.COLOR_DANGER))
                self.after(0, lambda: messagebox.showwarning(
                    "Update Check Failed",
                    "An unexpected error occurred during the version check."))

        update_thread = threading.Thread(target=_check_in_thread, daemon=True)
        update_thread.start()

    def ask_for_update(self, latest_version):
        # --- FIXED POPUP ---
        if self.is_update_prompt_showing:
            return  # An update prompt is already active

        try:
            self.is_update_prompt_showing = True
            title = "New ADB Commander Update!"
            message = (
                f"An improved version ({latest_version}) is now available!\n\n"
                "New Auto Click what's on your mind Auto Type caption auto switch acc This update contains the latest upgrades and performance improvements for faster and more reliable control of your devices.\n\n"
                "The app will close and restart to complete the update. Would you like to update now?"
            )

            response = messagebox.askyesno(title, message)
            if response:
                self.update_app()
        finally:
            self.is_update_prompt_showing = False  # Ensure this always runs

    def on_closing(self):
        # Cancel the periodic update check job
        if self.update_check_job:
            self.after_cancel(self.update_check_job)

        # Stop all threads
        self.is_auto_typing.clear()
        is_stop_requested.set()

        self.stop_capture()
        self.executor.shutdown(wait=False)
        self.destroy()

    def _configure_tab_layouts(self):
        """
        Helper method to configure the grid layout for each tab with the
        new professional design.

        --- FIXED: Added CTkScrollableFrame inside each tab ---
        """

        # --- Configure "Facebook Automation" Tab ---
        fb_tab_container = self.tab_view.tab("Facebook Automation")

        # --- ADDED SCROLLABLE FRAME ---
        fb_frame = ctk.CTkScrollableFrame(fb_tab_container, fg_color="transparent")
        fb_frame.pack(fill="both", expand=True, padx=0, pady=0)
        # --- END OF FIX ---

        fb_frame.columnconfigure(0, weight=1)

        # --- Section: App Control (MODIFIED to include SWITCH ACC button) ---
        self._create_section_header(fb_frame, "App Control", 0)
        fb_app_frame = self._create_section_frame(fb_frame, 1)
        fb_app_frame.columnconfigure(0, weight=1)
        fb_app_frame.columnconfigure(1, weight=1)
        fb_app_frame.columnconfigure(2, weight=1)  # New column for switch acc

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

        # NEW BUTTON: SWITCH ACC
        self.switch_acc_button = ctk.CTkButton(fb_app_frame, text="SWITCH ACC 🔄",
                                               command=lambda: threading.Thread(
                                                   target=self._threaded_run_switch_account_sequence,
                                                   daemon=True).start(),
                                               corner_radius=8, fg_color=self.COLOR_ACCENT,
                                               hover_color=self.COLOR_ACCENT_HOVER,
                                               height=40, font=self.FONT_BUTTON, text_color=self.COLOR_BACKGROUND)
        self.switch_acc_button.grid(row=0, column=2, sticky='ew', padx=(5, 10), pady=10)  # New column 2

        # --- Section: Single Post ---
        self._create_section_header(fb_frame, "Single Post Visit", 2)
        fb_single_frame = self._create_section_frame(fb_frame, 3)

        self.fb_url_entry = ctk.CTkEntry(fb_single_frame, placeholder_text="Enter Facebook URL...", height=40,
                                         corner_radius=8, font=self.FONT_BODY)
        self.fb_url_entry.grid(row=0, column=0, sticky='ew', padx=10, pady=(10, 5))

        self.fb_button = ctk.CTkButton(fb_single_frame, text="VISIT POST", command=self.open_fb_lite_deeplink,
                                       fg_color="#1877f2", hover_color="#1651b7", height=40,
                                       font=self.FONT_BUTTON, corner_radius=8)
        self.fb_button.grid(row=1, column=0, sticky='ew', padx=10, pady=(5, 10))

        # --- Section: Multi-Post Automation ---
        self._create_section_header(fb_frame, "Multi-Link & Caption Automation", 4)

        # Container para sa mga dynamic na entry
        self.share_pair_frame = ctk.CTkScrollableFrame(fb_frame, fg_color=self.COLOR_FRAME, height=200,
                                                       corner_radius=8, border_color=self.COLOR_BORDER, border_width=1)
        self.share_pair_frame.grid(row=5, column=0, sticky='ew', padx=15, pady=5)
        self.share_pair_frame.columnconfigure(0, weight=1)

        # Add Link/Caption Button
        add_link_button = ctk.CTkButton(fb_frame, text="➕ ADD LINK / CAPTION PAIR", command=self.add_share_pair,
                                        fg_color=self.COLOR_SUCCESS, hover_color=self.COLOR_SUCCESS_HOVER, height=40,
                                        font=self.FONT_BUTTON, corner_radius=8,
                                        text_color=self.COLOR_BACKGROUND)
        add_link_button.grid(row=6, column=0, sticky='ew', padx=15, pady=(5, 10))

        # Initial pair upon startup
        self.add_share_pair(is_initial=True)

        # --- Section: Automation Actions ---
        self._create_section_header(fb_frame, "Automation Actions", 7)
        action_frame = self._create_section_frame(fb_frame, 8)
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

        # --- Prominent "START AUTO-TYPE" Button ---
        self.find_click_type_button = ctk.CTkButton(fb_frame, text="START AUTO-TYPE ⌨️",
                                                    command=self.toggle_auto_type_loop,
                                                    fg_color=self.COLOR_ACCENT, hover_color=self.COLOR_ACCENT_HOVER,
                                                    height=50,
                                                    font=self.FONT_SUBHEADING,
                                                    text_color=self.COLOR_BACKGROUND,
                                                    corner_radius=8)
        self.find_click_type_button.grid(row=9, column=0, sticky='ew', padx=15, pady=(15, 15))

        # --- Configure "Utilities" Tab (NEW MERGED TAB) ---
        utility_tab_container = self.tab_view.tab("Utilities")

        # --- ADDED SCROLLABLE FRAME ---
        utility_frame = ctk.CTkScrollableFrame(utility_tab_container, fg_color="transparent")
        utility_frame.pack(fill="both", expand=True, padx=0, pady=0)
        # --- END OF FIX ---

        utility_frame.columnconfigure(0, weight=1)

        # --- Section: App Management ---
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
                                          corner_radius=8, height=40,
                                          font=self.FONT_BUTTON)
        browse_apk_button.grid(row=0, column=0, sticky='ew', padx=(0, 5))

        install_apk_button = ctk.CTkButton(apk_button_frame, text="INSTALL APK ⬇️", command=self.install_apk_to_devices,
                                           fg_color=self.COLOR_ACCENT, hover_color=self.COLOR_ACCENT_HOVER,
                                           corner_radius=8,
                                           height=40,
                                           font=self.FONT_BUTTON, text_color=self.COLOR_BACKGROUND)
        install_apk_button.grid(row=0, column=1, sticky='ew', padx=(5, 0))

        # --- Section: Device Control ---
        self._create_section_header(utility_frame, "Device Control", 2)
        device_control_frame = self._create_section_frame(utility_frame, 3)
        device_control_frame.columnconfigure(0, weight=1)
        device_control_frame.columnconfigure(1, weight=1)

        enable_airplane_button = ctk.CTkButton(device_control_frame, text="ENABLE AIRPLANE ✈️",
                                               command=self.enable_airplane_mode,
                                               fg_color=self.COLOR_BORDER, hover_color=self.COLOR_TEXT_SECONDARY,
                                               corner_radius=8, height=40,
                                               font=self.FONT_BUTTON)
        enable_airplane_button.grid(row=0, column=0, sticky='ew', padx=(10, 5), pady=10)

        disable_airplane_button = ctk.CTkButton(device_control_frame, text="DISABLE AIRPLANE 📶",
                                                command=self.disable_airplane_mode,
                                                fg_color=self.COLOR_SUCCESS, hover_color=self.COLOR_SUCCESS_HOVER,
                                                corner_radius=8,
                                                height=40, text_color=self.COLOR_BACKGROUND,
                                                font=self.FONT_BUTTON)
        disable_airplane_button.grid(row=0, column=1, sticky='ew', padx=(5, 10), pady=10)

        # --- Section: Image Sharing (Moved from old "Image" tab) ---
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
                                                height=40,
                                                font=self.FONT_BUTTON, corner_radius=8,
                                                text_color=self.COLOR_BACKGROUND)
        self.share_image_button.grid(row=1, column=0, sticky='ew', padx=10, pady=(5, 10))

    # --- NEW METHOD: Switch Account Sequence ---

    def _run_switch_account_adb_commands(self, serial):
        """Runs the complete switch account ADB sequence on a single device."""
        if is_stop_requested.is_set():
            return False

        try:
            # 1. Tap at [621,48][695,122] (Center: 658, 85)
            tap_x_1, tap_y_1 = 658, 85
            # self.after(0, lambda: self.status_label.configure(text=f"[CMD] Tap 1 ({tap_x_1},{tap_y_1}) on {serial}", text_color=self.COLOR_ACCENT))
            run_adb_command(['shell', 'input', 'tap', str(tap_x_1), str(tap_y_1)], serial)

            # 2. Delay 2s and Swipe 359 1233 372 176 500
            # self.after(0, lambda: self.status_label.configure(text=f"[SYS] Delay 2s (Swipe Pre) on {serial}", text_color=self.COLOR_TEXT_SECONDARY))
            time.sleep(2)
            swipe_cmd = ['shell', 'input', 'swipe', '359', '1233', '372', '176', '500']
            # self.after(0, lambda: self.status_label.configure(text=f"[CMD] Swipe on {serial}", text_color=self.COLOR_ACCENT))
            run_adb_command(swipe_cmd, serial)
            # self.after(0, lambda: self.status_label.configure(text=f"[SYS] Delay 2s (Swipe Post) on {serial}", text_color=self.COLOR_TEXT_SECONDARY))
            time.sleep(2)  # Delay after swipe

            # 3. Delay 3s and Tap at [112,1208][231,1253] (Center: 172, 1231)
            # self.after(0, lambda: self.status_label.configure(text=f"[SYS] Delay 3s (Tap 2 Pre) on {serial}", text_color=self.COLOR_TEXT_SECONDARY))
            time.sleep(3)
            tap_x_2, tap_y_2 = 172, 1231
            # self.after(0, lambda: self.status_label.configure(text=f"[CMD] Tap 2 ({tap_x_2},{tap_y_2}) on {serial}", text_color=self.COLOR_ACCENT))
            run_adb_command(['shell', 'input', 'tap', str(tap_x_2), str(tap_y_2)], serial)

            # 4. Tap at [95,684][347,756] (Center: 221, 720)
            tap_x_3, tap_y_3 = 221, 720
            # self.after(0, lambda: self.status_label.configure(text=f"[CMD] Tap 3 ({tap_x_3},{tap_y_3}) on {serial}", text_color=self.COLOR_ACCENT))
            run_adb_command(['shell', 'input', 'tap', str(tap_x_3), str(tap_y_3)], serial)

            return True
        except Exception as e:
            # print(f"Error during switch sequence on {serial}: {e}")
            return False

    def _threaded_run_switch_account_sequence(self):
        """Thread wrapper for the switch account sequence, handling multi-device execution and UI updates."""
        if not self.devices:
            self.after(0, lambda: self.status_label.configure(text="⚠️ No devices detected.",
                                                              text_color=self.COLOR_WARNING))
            return

        self.after(0, lambda: self.status_label.configure(
            text="[CMD] Starting SWITCH ACCOUNT sequence on all devices...",
            text_color=self.COLOR_ACCENT))

        futures = []
        for serial in self.devices:
            futures.append(self.executor.submit(self._run_switch_account_adb_commands, serial))

        # Wait for all devices to finish the sequence
        concurrent.futures.wait(futures)

        # Check results and update final status
        results = [f.result() for f in futures if f.exception() is None]
        all_success = all(results)

        if all_success and self.devices:
            self.after(0, lambda: self.status_label.configure(
                text=f"✅ SWITCH ACCOUNT sequence completed successfully on {len(self.devices)} devices.",
                text_color=self.COLOR_SUCCESS))
        else:
            fail_count = len(self.devices) - sum(results)
            self.after(0, lambda: self.status_label.configure(
                text=f"❌ SWITCH ACCOUNT sequence FAILED on {fail_count} device(s). Check device screen/connection.",
                text_color=self.COLOR_DANGER))

    # --- End NEW METHOD: Switch Account Sequence ---

    # --- New ADB Utility Methods for Airplane Mode ---

    def _threaded_airplane_mode(self, mode):
        """Helper function to run airplane mode commands in a thread."""
        if not self.devices:
            self.after(0, lambda: self.status_label.configure(text="⚠️ No devices detected.",
                                                              text_color=self.COLOR_WARNING))
            return

        state = '1' if mode == 'enable' else '0'
        name = 'ENABLE' if mode == 'enable' else 'DISABLE'

        self.after(0, lambda: self.status_label.configure(
            text=f"[CMD] Sending {name} AIRPLANE MODE command...", text_color=self.COLOR_ACCENT))

        # 1. Set the system setting
        set_cmd = ['shell', 'settings', 'put', 'global', 'airplane_mode_on', state]

        # 2. Broadcast the change (crucial for it to take effect instantly)
        broadcast_cmd = ['shell', 'am', 'broadcast', '-a', 'android.intent.action.AIRPLANE_MODE']

        # Submit both commands for each device
        for serial in self.devices:
            # We don't wait for success/failure here as setting changes don't return meaningful output
            self.executor.submit(run_adb_command, set_cmd, serial)
            self.executor.submit(run_adb_command, broadcast_cmd, serial)

        self.after(0, lambda: self.status_label.configure(
            text=f"✅ AIRPLANE MODE {name} command sent to all devices.", text_color=self.COLOR_SUCCESS))

    def enable_airplane_mode(self):
        """Enables Airplane Mode on all connected devices."""
        threading.Thread(target=self._threaded_airplane_mode, args=('enable',), daemon=True).start()

    def disable_airplane_mode(self):
        """Disables Airplane Mode on all connected devices."""
        threading.Thread(target=self._threaded_airplane_mode, args=('disable',), daemon=True).start()

    # --- Existing ADB Utility Methods ---

    def browse_apk_file(self):
        """Opens a file dialog to select an APK file."""
        file_path = filedialog.askopenfilename(
            defaultextension=".apk",
            filetypes=[("APK files", "*.apk")]
        )
        if file_path:
            self.apk_path = file_path
            self.apk_path_entry.delete(0, tk.END)
            self.apk_path_entry.insert(0, os.path.basename(file_path))
            self.status_label.configure(text=f"✅ APK SELECTED: {os.path.basename(file_path)}",
                                        text_color=self.COLOR_SUCCESS)

    def install_apk_to_devices(self):
        """Installs the selected APK on all connected devices."""
        if not self.apk_path or not os.path.exists(self.apk_path):
            self.status_label.configure(text="⚠️ Please select a valid APK file first.", text_color=self.COLOR_WARNING)
            return

        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color=self.COLOR_WARNING)
            return

        self.status_label.configure(text=f"[CMD] Installing {os.path.basename(self.apk_path)} on all devices...",
                                    text_color=self.COLOR_ACCENT)

        command = ['install', '-r', self.apk_path]  # -r flag means reinstall if it already exists

        results = []

        def _install_task(serial):
            success, output = run_adb_command(command, serial)
            results.append((serial, success, output))

        # Submit tasks and wait for all to complete
        futures = [self.executor.submit(_install_task, serial) for serial in self.devices]
        concurrent.futures.wait(futures)

        # Check results and update status
        all_success = all(success for _, success, _ in results)
        if all_success:
            self.status_label.configure(text="✅ APK INSTALL SUCCESSFUL.", text_color=self.COLOR_SUCCESS)
        else:
            error_count = sum(1 for _, success, _ in results if not success)
            self.status_label.configure(text=f"❌ INSTALLATION FAILED on {error_count} device(s).",
                                        text_color=self.COLOR_DANGER)

    # --- Existing Methods (Updated for Styling) ---

    def update_app(self):
        # Adjusted error handling in _update_in_thread for clarity
        def _update_in_thread():
            try:
                self.status_label.configure(text="[SYS] Downloading latest version...", text_color=self.COLOR_ACCENT)

                response = requests.get(UPDATE_URL)
                response.raise_for_status()  # Raise HTTPError for bad status codes (4xx or 5xx)

                desktop_path = Path.home() / "Desktop"
                # Handle both frozen executable and script mode
                old_file_path = Path(sys.executable) if getattr(sys, 'frozen', False) else Path(sys.argv[0])

                # Check if the app is run from a location we can write to and execute later
                if not old_file_path.is_file():
                    # If running from a temp location (like a frozen app not on desktop), default to desktop
                    new_file_path = desktop_path / "adb_tool_by_dars.py"
                elif old_file_path.suffix == '.py':
                    new_file_path = old_file_path.parent / old_file_path.name
                else:  # frozen executable
                    new_file_path = desktop_path / old_file_path.name  # Replace the exe on the desktop

                with open(new_file_path, 'wb') as f:
                    f.write(response.content)

                messagebox.showinfo("Update Complete",
                                    "The new version has been downloaded. The application will now close and update.")

                create_and_run_updater_script(new_file_path, old_file_path)

                self.destroy()

            except requests.exceptions.HTTPError as http_err:
                status_code = http_err.response.status_code
                self.after(0, lambda: self.status_label.configure(
                    text=f"❌ ERROR: Update download failed. HTTP Status: {status_code}",
                    text_color=self.COLOR_DANGER))
                self.after(0, lambda: messagebox.showerror(
                    "Update Download Failed",
                    f"Failed to download update (HTTP Error {status_code}). Check if the update file exists at the URL."))
            except requests.exceptions.ConnectionError:
                self.after(0, lambda: self.status_label.configure(
                    text="❌ ERROR: Update download failed. Connection Refused.",
                    text_color=self.COLOR_DANGER))
                self.after(0, lambda: messagebox.showerror(
                    "Update Download Failed",
                    "Failed to download update. Cannot connect to the server. Check your internet connection or firewall."))
            except requests.exceptions.Timeout:
                self.after(0, lambda: self.status_label.configure(
                    text="❌ ERROR: Update download timed out.",
                    text_color=self.COLOR_DANGER))
                self.after(0, lambda: messagebox.showerror(
                    "Update Download Failed",
                    "Update download timed out. Your network might be slow or unstable."))
            except requests.exceptions.RequestException as e:
                self.after(0, lambda: self.status_label.configure(
                    text=f"❌ ERROR: Update download failed. Details: {e.__class__.__name__}",
                    text_color=self.COLOR_DANGER))
                self.after(0, lambda: messagebox.showerror(
                    "Update Download Failed",
                    f"An error occurred during download: {e.__class__.__name__}. Check logs for details."))
            except Exception as e:
                self.after(0, lambda: self.status_label.configure(
                    text=f"❌ ERROR: An unexpected update error occurred: {e}",
                    text_color=self.COLOR_DANGER))
                self.after(0, lambda: messagebox.showerror(
                    "Update Error",
                    f"An unexpected file operation error occurred.\nError: {e}"))

        update_thread = threading.Thread(target=_update_in_thread, daemon=True)
        update_thread.start()

    # --- NEW METHODS: Dynamic Link/Caption Pair Management ---

    def add_share_pair(self, is_initial=False):
        """Adds a new row for a share URL and its corresponding caption file."""

        # Use the frame we defined in _configure_tab_layouts
        frame = ctk.CTkFrame(self.share_pair_frame, fg_color=self.COLOR_BACKGROUND, corner_radius=8)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=0)  # Button column

        # Row 0: Link Entry and Remove Button
        link_frame = ctk.CTkFrame(frame, fg_color="transparent")
        link_frame.grid(row=0, column=0, columnspan=2, sticky='ew', padx=10, pady=(10, 5))
        link_frame.columnconfigure(0, weight=1)
        link_frame.columnconfigure(1, weight=0)

        # Share URL Entry
        share_url_entry = ctk.CTkEntry(link_frame,
                                       placeholder_text=f"Link #{len(self.share_pairs) + 1}: Enter link to share...",
                                       height=35, corner_radius=8, font=self.FONT_BODY)
        share_url_entry.grid(row=0, column=0, sticky='ew', padx=(0, 5))

        # Remove Button (Only for non-initial pairs)
        if not is_initial:
            remove_button = ctk.CTkButton(link_frame, text="✖️", width=35, height=35, corner_radius=8,
                                          fg_color=self.COLOR_DANGER, hover_color=self.COLOR_DANGER_HOVER,
                                          command=lambda: self.remove_share_pair(frame))
            remove_button.grid(row=0, column=1, sticky='e')

        # Row 1: Caption Entry and Browse Button
        caption_frame = ctk.CTkFrame(frame, fg_color="transparent")
        caption_frame.grid(row=1, column=0, columnspan=2, sticky='ew', padx=10, pady=(0, 10))
        caption_frame.columnconfigure(0, weight=1)
        caption_frame.columnconfigure(1, weight=0)

        # File Path Entry
        file_path_entry = ctk.CTkEntry(caption_frame, placeholder_text="Caption File Path: Select a text file...",
                                       height=35, corner_radius=8, font=self.FONT_BODY)
        file_path_entry.grid(row=0, column=0, sticky='ew', padx=(0, 5))

        # Browse Button
        browse_button = ctk.CTkButton(caption_frame, text="BROWSE TXT", corner_radius=8, width=120, height=35,
                                      fg_color=self.COLOR_BORDER, hover_color=self.COLOR_TEXT_SECONDARY,
                                      font=self.FONT_BUTTON,
                                      command=lambda: self.browse_share_pair_file(file_path_entry))
        browse_button.grid(row=0, column=1, sticky='e')

        # Add the pair to the list and pack the frame
        self.share_pairs.append({
            'frame': frame,
            'url_entry': share_url_entry,
            'file_entry': file_path_entry
        })
        frame.pack(fill='x', padx=5, pady=5)
        self.share_pair_frame.update_idletasks()  # Force update to make scrollbar work

    def remove_share_pair(self, pair_frame_to_remove):
        """Removes a share pair from the UI and the internal list."""
        for i, pair in enumerate(self.share_pairs):
            if pair['frame'] == pair_frame_to_remove:
                pair['frame'].destroy()
                self.share_pairs.pop(i)
                self.status_label.configure(text=f"✅ Link/Caption Pair removed.", text_color=self.COLOR_SUCCESS)
                # If auto-typing is running, stop and restart to update the list of texts
                if self.is_auto_typing.is_set():
                    self.stop_auto_type_loop()
                    self.after(100, self.start_auto_type_loop)
                return

    def browse_share_pair_file(self, target_entry):
        """Opens a file dialog and updates the specific target entry."""
        file_path = filedialog.askopenfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if file_path:
            target_entry.delete(0, tk.END)
            target_entry.insert(0, file_path)
            self.status_label.configure(text=f"✅ FILE SELECTED: {os.path.basename(file_path)}",
                                        text_color=self.COLOR_SUCCESS)
            # Automatically stop and restart the loop if a new file is selected while running
            if self.is_auto_typing.is_set():
                self.stop_auto_type_loop()
                self.after(100, self.start_auto_type_loop)

    # --- MODIFIED: Text Command and Emoji Removal to use the dynamic list ---

    def _threaded_send_text(self):
        # --- NEW: Get all valid file paths ---
        file_paths = []
        for pair in self.share_pairs:
            file_path = pair['file_entry'].get()
            if file_path and os.path.exists(file_path):
                file_paths.append(file_path)

        if not file_paths:
            self.status_label.configure(text="⚠️ Please select a text file for at least one pair.",
                                        text_color=self.COLOR_WARNING)
            return

        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color=self.COLOR_WARNING)
            return

        # --- MODIFIED: Select a random file path and read its content ---
        random_file_path = random.choice(file_paths)

        try:
            with open(random_file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            clean_lines = [line.strip() for line in lines if line.strip()]

            if not clean_lines:
                self.status_label.configure(
                    text=f"⚠️ The selected file '{os.path.basename(random_file_path)}' is empty.",
                    text_color=self.COLOR_WARNING)
                return

            self.status_label.configure(
                text=f"[CMD] Sending random text from file '{os.path.basename(random_file_path)}' to all devices...",
                text_color=self.COLOR_ACCENT)

            for device_serial in self.devices:
                random_text = random.choice(clean_lines)
                self.executor.submit(run_text_command, random_text, device_serial)

            self.status_label.configure(text=f"✅ Text commands submitted.", text_color=self.COLOR_SUCCESS)


        except FileNotFoundError:
            self.status_label.configure(text="❌ ERROR: File not found.", text_color=self.COLOR_DANGER)
        except Exception as e:
            self.status_label.configure(text=f"❌ ERROR: An error occurred: {e}", text_color=self.COLOR_DANGER)

    def send_text_to_devices(self):
        send_thread = threading.Thread(target=self._threaded_send_text, daemon=True)
        send_thread.start()

    # --- NEW METHODS: Refactored auto-type logic ---
    def start_auto_type_loop(self):
        """Starts the auto-type loop if it is not already running."""
        if self.is_auto_typing.is_set():
            return  # Already running

        # --- NEW: Get all valid pairs ---
        valid_pairs = []
        for pair in self.share_pairs:
            share_url = pair['url_entry'].get()
            file_path = pair['file_entry'].get()

            # --- BINAGO ANG LOGIC DITO ---
            # Ituring na valid basta may URL. Ang file_path ay optional na.
            if share_url:
                valid_pairs.append({'url': share_url, 'file': file_path})
            # --- WAKAS NG PAGBABAGO ---

        if not valid_pairs:
            self.status_label.configure(text="⚠️ No valid Links found. Please enter at least one URL.",
                                        text_color=self.COLOR_WARNING)
            return

        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color=self.COLOR_WARNING)
            return

        # Set the flag
        self.is_auto_typing.set()

        # Update button to be a STOP button
        self.find_click_type_button.configure(text="STOP AUTO-TYPE 🛑",
                                              fg_color=self.COLOR_DANGER,
                                              hover_color=self.COLOR_DANGER_HOVER,
                                              text_color=self.COLOR_TEXT_PRIMARY)

        self.status_label.configure(text="[CMD] Auto-type loop STARTED.", text_color=self.COLOR_SUCCESS)

        # Start the loop thread, passing the list of valid pairs
        threading.Thread(target=self._threaded_find_click_type_LOOP, args=(valid_pairs,), daemon=True).start()

    def stop_auto_type_loop(self):
        """Stops the auto-type loop and resets the button."""
        self.is_auto_typing.clear()

        # Check if button exists before configuring (in case window is closing)
        if hasattr(self, 'find_click_type_button') and self.find_click_type_button.winfo_exists():
            self.find_click_type_button.configure(text="START AUTO-TYPE ⌨️",
                                                  fg_color=self.COLOR_ACCENT,
                                                  hover_color=self.COLOR_ACCENT_HOVER,
                                                  text_color=self.COLOR_BACKGROUND)

    def toggle_auto_type_loop(self):
        """
        Toggles the 'while true' loop for finding, clicking, and typing.
        (Linked to the new button)
        """
        if self.is_auto_typing.is_set():
            self.stop_auto_type_loop()
        else:
            self.start_auto_type_loop()

    # --- SIMULA NG PAGDAGDAG NG RETRY LOGIC (Wrapper Function) ---

    def _run_task_with_retry(self, serial, text_to_send, pair_index, max_retries=5):
        """
        Runs the find/click/type logic with retries to ensure completion on a single device.
        """
        for attempt in range(max_retries):
            # 1. Check stop flags
            if not self.is_auto_typing.is_set() or is_stop_requested.is_set():
                return False, "Stop requested"

            # 2. Run the core action (Find, Click, Type)
            success, message = self._run_find_click_type_on_device(serial, text_to_send)

            if success:
                self.after(0, lambda: self.status_label.configure(
                    text=f"✅ Pair {pair_index} on {serial} SUCCESSFUL (Attempt {attempt + 1}).",
                    text_color=self.COLOR_SUCCESS))
                return True, message
            else:
                # 3. Handle failure and retry
                if attempt < max_retries - 1:
                    wait_time = 3 + attempt * 2  # Increase wait time with each attempt (3s, 5s, 7s, 9s, 11s)
                    self.after(0, lambda: self.status_label.configure(
                        text=f"⚠️ Pair {pair_index} on {serial}: Failed ({message}). Retrying in {wait_time}s (Attempt {attempt + 2}/{max_retries}).",
                        text_color=self.COLOR_WARNING))

                    # Pause the single thread before the next retry
                    time.sleep(wait_time)
                else:
                    self.after(0, lambda: self.status_label.configure(
                        text=f"❌ Pair {pair_index} on {serial}: FAILED after {max_retries} attempts ({message}). Moving to next pair.",
                        text_color=self.COLOR_DANGER))
                    return False, message

        return False, "Max retries reached"

    # --- WAKAS NG PAGDAGDAG NG RETRY LOGIC ---

    def _threaded_find_click_type_LOOP(self, valid_pairs):
        """
        The main 'while true' loop for auto-typing.
        (REMOVED the final tap/swipe sequence as it's now in the SWITCH ACC button)
        """

        try:
            # Re-enable the loop using the self.is_auto_typing flag
            while self.is_auto_typing.is_set() and not is_stop_requested.is_set():

                # Itakda ang flag na ito sa 'False' sa simula ng BAWAT cycle
                success_achieved_in_this_cycle = False

                if not self.devices:
                    self.after(0, lambda: self.status_label.configure(text="⚠️ No devices, stopping loop.",
                                                                      text_color=self.COLOR_WARNING))
                    break

                # --- Iterate through all valid pairs sequentially in this cycle ---
                for index, selected_pair in enumerate(valid_pairs):
                    if not self.is_auto_typing.is_set() or is_stop_requested.is_set():
                        break  # Stop if flag is cleared during iteration

                    share_url = selected_pair['url']
                    file_path = selected_pair['file']
                    pair_index = index + 1
                    total_pairs = len(valid_pairs)

                    self.after(0, lambda: self.status_label.configure(
                        text=f"[CMD] Processing Pair {pair_index}/{total_pairs}: Sharing {share_url[:20]}...",
                        text_color=self.COLOR_ACCENT))

                    # --- SIMULA NG PAGBABAGO: I-check kung may caption file ---
                    clean_lines = []
                    has_caption = False  # Default: Walang caption

                    if file_path and os.path.exists(file_path):
                        # May file path, subukang basahin
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                lines = f.readlines()
                            clean_lines = [line.strip() for line in lines if line.strip()]

                            if clean_lines:
                                has_caption = True  # May nabasa tayong text!
                            else:
                                # May file pero walang laman
                                self.after(0, lambda: self.status_label.configure(
                                    text=f"⚠️ Caption file '{os.path.basename(file_path)}' is empty. Share-only mode.",
                                    text_color=self.COLOR_WARNING))
                        except Exception as e:
                            # Nagka-error sa pagbasa ng file
                            self.after(0, lambda: self.status_label.configure(
                                text=f"❌ Error reading file: {e}. Share-only mode.", text_color=self.COLOR_DANGER))
                    else:
                        # Walang file path na pinili
                        self.after(0, lambda: self.status_label.configure(
                            text=f"ℹ️ No caption file for Pair {pair_index}. Share-only mode.",
                            text_color=self.COLOR_TEXT_SECONDARY))
                    # --- WAKAS NG PAGBABAGO ---

                    # 2. MANDATORY: Run the Share Post (Lagi itong gagana basta may URL)
                    share_command = [
                        'shell', 'am', 'start',
                        '-a', 'android.intent.action.SEND',
                        '-t', 'text/plain',
                        '--es', 'android.intent.extra.TEXT', f'"{share_url}"',  # Uses quotes for robust ADB parsing
                        'com.facebook.lite'
                    ]

                    share_futures = []
                    for serial in self.devices:
                        if not self.is_auto_typing.is_set() or is_stop_requested.is_set():
                            break
                        share_futures.append(self.executor.submit(run_adb_command, share_command, serial))

                    # Hintayin matapos ang share command bago mag-delay
                    concurrent.futures.wait(share_futures)

                    # MAGHINTAY ng 5 segundo para lumabas ang Share Dialogue sa device.
                    time.sleep(5)

                    if not self.is_auto_typing.is_set() or is_stop_requested.is_set():
                        break

                    # 3. Try to Find EditText and Type Caption (KUNG 'has_caption' ay True lang)
                    # --- SIMULA NG PAGBABAGO: Idagdag ang 'if has_caption:' ---
                    if has_caption:
                        self.after(0, lambda: self.status_label.configure(
                            text=f"[CMD] Pair {pair_index}: Starting typing and retry attempts...",
                            text_color=self.COLOR_ACCENT))

                        futures = []
                        for serial in self.devices:
                            if not self.is_auto_typing.is_set() or is_stop_requested.is_set():
                                break

                            random_text = random.choice(clean_lines)  # Ligtas na ito
                            # Call the retry wrapper function
                            futures.append(
                                self.executor.submit(self._run_task_with_retry, serial, random_text, pair_index))

                        # Wait for all devices to complete the typing/posting attempt (including all retries)
                        concurrent.futures.wait(futures)

                        # 4. Check results: Did ANY device succeed after retries?
                        pair_success = False
                        for future in futures:
                            if future.exception() is None:
                                # The result of _run_task_with_retry is (bool success, str message)
                                success, _ = future.result()
                                if success:
                                    pair_success = True
                    else:
                        # --- WAKAS NG PAGBABAGO (if has_caption) ---
                        # --- SIMULA NG PAGBABAGO (else block) ---
                        # Walang caption, kaya ang "share" pa lang ay success na.
                        self.after(0, lambda: self.status_label.configure(
                            text=f"✅ Pair {pair_index}: SHARE-ONLY complete.",
                            text_color=self.COLOR_SUCCESS))
                        pair_success = True
                    # --- WAKAS NG PAGBABAGO (else block) ---

                    if pair_success:
                        # Kung successful ang pag-type/post, itakda ang overall flag
                        success_achieved_in_this_cycle = True

                    # --- SIMULA NG PAGDAGDAG NG COOLDOWN PARA TAPUSIN ANG BAWAT PAIR ---
                    # MAGHINTAY ng 10 segundo bago magpatuloy sa susunod na link.
                    COOLDOWN = 10
                    self.after(0, lambda: self.status_label.configure(
                        text=f"[SYS] Pair {pair_index} processed. Waiting {COOLDOWN}s before next pair...",
                        text_color=self.COLOR_TEXT_SECONDARY))

                    for _ in range(COOLDOWN):
                        if not self.is_auto_typing.is_set() or is_stop_requested.is_set():
                            break
                        time.sleep(1)

                    if not self.is_auto_typing.is_set() or is_stop_requested.is_set():
                        break
                    # --- WAKAS NG PAGDAGDAG NG COOLDOWN ---

                # --- End of sequential processing for all pairs (REMOVED FINAL COMMANDS) ---

                # Check if an overall success was achieved (at least one post was successfully made)
                if success_achieved_in_this_cycle:
                    self.after(0, lambda: self.status_label.configure(
                        text="✅ AUTO-TYPE SUCCESSFUL (Posted/Shared). Stopping loop.",
                        text_color=self.COLOR_SUCCESS))
                    break  # Exit the while loop
                else:
                    # Maghintay ng 5 segundo bago subukang muli (next while loop iteration)
                    self.after(0, lambda: self.status_label.configure(
                        text="[SYS] All pairs processed (No successful post). Waiting 5s for next cycle...",
                        text_color=self.COLOR_TEXT_PRIMARY))

                    wait_duration = 5  # 5 segundo
                    for _ in range(wait_duration):
                        if not self.is_auto_typing.is_set() or is_stop_requested.is_set():
                            break
                        time.sleep(1)


        except Exception as e:
            print(f"Error in auto-type loop: {e}")
            self.after(0, lambda: self.status_label.configure(
                text=f"❌ CRITICAL ERROR in auto-type task: {e}", text_color=self.COLOR_DANGER))
        finally:
            # Ensure the flag and button are reset when the loop breaks or errors
            self.after(0, self.stop_auto_type_loop)

    # --- WAKAS NG PAG-AYOS ---

    def _run_find_click_type_on_device(self, serial, text_to_send):
        """
        The core logic that runs on each device to find, click, and type.
        Returns (bool success, str message)
        """
        local_xml_file = f"ui_dump_{serial}_{uuid.uuid4()}.xml"

        try:
            if self.is_auto_typing.is_set() and not is_stop_requested.is_set():
                # Step 1: Dump UI
                dump_cmd = ['shell', 'uiautomator', 'dump', '/data/local/tmp/ui.xml']
                success, out = run_adb_command(dump_cmd, serial)
                if not success:
                    # print(f"[{serial}] Failed to dump UI.")
                    return False, "Failed to dump UI"
            else:
                return False, "Stop requested"

            if self.is_auto_typing.is_set() and not is_stop_requested.is_set():
                # Step 2: Pull XML
                pull_cmd = ['pull', '/data/local/tmp/ui.xml', local_xml_file]
                success, out = run_adb_command(pull_cmd, serial)
                if not success:
                    # print(f"[{serial}] Failed to pull UI XML.")
                    return False, "Failed to pull UI XML"
            else:
                return False, "Stop requested"

            if self.is_auto_typing.is_set() and not is_stop_requested.is_set():
                # Step 3: Parse XML
                if not os.path.exists(local_xml_file):
                    # print(f"[{serial}] XML file not found locally.")
                    return False, "XML file not found"

                tree = ET.parse(local_xml_file)
                root = tree.getroot()

                # Step 4: Find EditText
                # Find the first node with class="android.widget.EditText"
                edit_text_node = root.find('.//node[@class="android.widget.EditText"]')

                if edit_text_node is None:
                    # print(f"[{serial}] No EditText found.")
                    return False, "No EditText found (Caption box not ready/visible)"

                # Step 5: Get Bounds
                bounds_str = edit_text_node.get('bounds')  # e.g., "[100,200][300,400]"
                if not bounds_str:
                    # print(f"[{serial}] EditText found but has no bounds.")
                    return False, "EditText found but has no bounds"

                coords = re.findall(r'\d+', bounds_str)
                if len(coords) < 4:
                    # print(f"[{serial}] Invalid bounds string.")
                    return False, "Invalid bounds string"

                x1, y1, x2, y2 = map(int, coords[:4])

                # Step 6: Calculate Center
                tap_x = (x1 + x2) // 2
                tap_y = (y1 + y2) // 2

            else:
                return False, "Stop requested"

            if self.is_auto_typing.is_set() and not is_stop_requested.is_set():
                # Step 7: Click
                tap_cmd = ['shell', 'input', 'tap', str(tap_x), str(tap_y)]
                success, out = run_adb_command(tap_cmd, serial)
                if not success:
                    # print(f"[{serial}] Failed to tap.")
                    return False, "Failed to tap"

                # Mas matagal na delay para masigurong lalabas ang keyboard at handa na ang device.
                time.sleep(3)  # <-- BINAGO ang halaga para sa mas matibay na operasyon.

            if self.is_auto_typing.is_set() and not is_stop_requested.is_set():
                # Step 8: Type
                # This will now also click the "Post" button because run_text_command is modified
                run_text_command(text_to_send, serial)
                # print(f"[{serial}] Click and type successful.")
                return True, "Success"
            else:
                return False, "Stop requested"

        except ET.ParseError:
            # print(f"[{serial}] Failed to parse XML.")
            return False, "Failed to parse XML"
        except Exception as e:
            # print(f"[{serial}] Error in find/click/type: {e}")
            return False, str(e)
        finally:
            # Step 9: Cleanup
            if os.path.exists(local_xml_file):
                os.remove(local_xml_file)

    # --- End of new methods ---

    def remove_emojis_from_file(self):
        # --- MODIFIED to use the file path from the FIRST pair ---
        if not self.share_pairs:
            self.status_label.configure(text="⚠️ Please add a Link/Caption Pair first.", text_color=self.COLOR_WARNING)
            return

        file_path = self.share_pairs[0]['file_entry'].get()
        if not file_path:
            self.status_label.configure(text="⚠️ Please select a text file for the first pair.",
                                        text_color=self.COLOR_WARNING)
            return

        try:
            # Pattern to match a wide range of Unicode emojis and symbols
            emoji_pattern = re.compile("["
                                       "\U0001F600-\U0001F64F"  # emoticons
                                       "\U0001F300-\U0001F5FF"  # symbols & pictographs
                                       "\U0001F680-\U0001F6FF"  # transport & map symbols
                                       "\U0001F700-\U0001F77F"  # alchemical symbols
                                       "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
                                       "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
                                       "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
                                       "\U0001FA00-\U0001FA6F"  # Chess Symbols
                                       "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
                                       "\U00002702-\U000027B0"  # Dingbats
                                       "\U00002600-\U000026FF"  # Miscellaneous Symbols
                                       "\U000025A0-\U000025FF"  # Geometric Shapes
                                       "]+", flags=re.UNICODE)

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            cleaned_content = emoji_pattern.sub(r'', content)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(cleaned_content)

            self.status_label.configure(text=f"✅ EMOJIS REMOVED from file: {os.path.basename(file_path)}.",
                                        text_color=self.COLOR_SUCCESS)

        except FileNotFoundError:
            self.status_label.configure(text="❌ ERROR: File not found.", text_color=self.COLOR_DANGER)
        except Exception as e:
            self.status_label.configure(text=f"❌ ERROR: An error occurred: {e}", text_color=self.COLOR_DANGER)

    def detect_devices(self):
        self.stop_capture()

        # Clear the device view panel (RIGHT SIDE)
        for widget in self.device_view_panel.winfo_children():
            widget.destroy()

        # Reset all device-related state
        self.device_frames = {}
        self.device_canvases = {}
        self.device_images = {}
        self.press_start_coords = {}
        self.press_time = {}
        self.selected_device_serial = None
        self.devices = []
        self.status_label.configure(text="[SYS] Detecting devices...", text_color=self.COLOR_ACCENT)

        try:
            result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, check=True, timeout=10)
            devices_output = result.stdout.strip().split('\n')[1:]
            self.devices = [line.split('\t')[0] for line in devices_output if line.strip() and 'device' in line]
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            messagebox.showerror("Error", "ADB is not installed, not in your system PATH, or timed out.")
            self.status_label.configure(text="❌ ERROR: ADB not found or timed out.", text_color=self.COLOR_DANGER)
            self.device_count_label.configure(text="DEVICES: 0")
            # Configure dropdown for no devices
            self.device_option_menu.configure(values=["No devices found"], state="disabled")
            self.device_selector_var.set("No devices found")
            return

        self.device_count_label.configure(text=f"DEVICES: {len(self.devices)}")

        if not self.devices:
            # Show "NO DEVICES" message in the RIGHT panel
            no_devices_label = ctk.CTkLabel(self.device_view_panel,
                                            text="NO DEVICES FOUND.\nEnsure USB debugging is enabled.",
                                            font=self.FONT_HEADING, text_color=self.COLOR_TEXT_SECONDARY)
            no_devices_label.pack(expand=True)
            self.status_label.configure(text="⚠️ No devices detected.", text_color=self.COLOR_WARNING)
            # Configure dropdown for no devices
            self.device_option_menu.configure(values=["No devices found"], state="disabled")
            self.device_selector_var.set("No devices found")
        else:
            self.status_label.configure(text=f"✅ {len(self.devices)} devices connected.", text_color=self.COLOR_SUCCESS)
            # Configure dropdown with found devices
            self.device_option_menu.configure(values=self.devices, state="normal")
            self.device_selector_var.set(self.devices[0])
            # Automatically select and show the first device
            self.on_device_select_menu(self.devices[0])

    def on_device_select_menu(self, selected_serial):
        """
        Callback for when a device is selected from the CTkOptionMenu.
        This REPLACES the old on_device_select.
        """
        if not selected_serial or selected_serial == "No devices found":
            return

        # Stop capture for the *previous* device if there was one
        self.stop_capture()
        self.selected_device_serial = selected_serial

        # Clear the device view panel
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
        # ... (Existing implementation is fine)
        self.is_capturing = False
        if self.update_image_id:
            self.after_cancel(self.update_image_id)
            self.update_image_id = None
        if self.capture_thread and self.capture_thread.is_alive():
            # capture_thread should terminate itself because self.is_capturing is False
            pass
        self.screenshot_queue.queue.clear()

    def start_capture_process(self):
        # ... (Existing implementation is fine)
        if self.is_capturing:
            return

        self.is_capturing = True
        self.capture_thread = threading.Thread(target=self.capture_screen_loop, daemon=True)
        self.capture_thread.start()
        self.update_image_id = self.after(100, self.update_image)

    def capture_screen_loop(self):
        # ... (Implementation remains the same, with added throttle)
        while self.is_capturing:
            try:
                if not self.selected_device_serial:
                    self.is_capturing = False
                    break

                # The 'exec-out' command is faster and avoids file I/O on the device
                process = subprocess.run(['adb', '-s', self.selected_device_serial, 'exec-out', 'screencap', '-p'],
                                         capture_output=True, check=True, timeout=5)
                self.screenshot_queue.put(process.stdout)
            except subprocess.CalledProcessError as e:
                # print(f"Error capturing screen: {e.stderr.decode()}")
                self.is_capturing = False
            except subprocess.TimeoutExpired:
                # print(f"Screen capture timed out for device {self.selected_device_serial}")
                pass
            except Exception as e:
                # print(f"An error occurred in capture loop: {e}")
                self.is_capturing = False

            # if self.is_capturing:
            #     time.sleep(0.05)  # Throttle screen capture rate

    def update_image(self):
        # ... (Implementation remains the same, improved centering logic)
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

                    # Maintain aspect ratio logic (9:16)
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

                        # Calculate position for centering the image on the canvas
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

        except Exception as e:
            # print(f"Error in update_image: {e}")
            self.stop_capture()

    def create_device_frame(self, serial):
        # This frame now lives in self.device_view_panel
        device_frame = ctk.CTkFrame(self.device_view_panel, fg_color="transparent")
        device_frame.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)
        self.device_frames[serial] = device_frame

        title = ctk.CTkLabel(device_frame, text=f"LIVE CONTROL: {serial}", font=self.FONT_HEADING,
                             text_color=self.COLOR_ACCENT)
        title.pack(pady=(0, 10))

        # This Frame will contain the canvas and handle its aspect ratio
        canvas_container = ctk.CTkFrame(device_frame, fg_color=self.COLOR_FRAME, corner_radius=8,
                                        border_width=1, border_color=self.COLOR_BORDER)
        canvas_container.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        canvas_container.bind("<Configure>", self.on_canvas_container_resize)

        canvas = tk.Canvas(canvas_container, bg=self.COLOR_FRAME, highlightthickness=0)
        canvas.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self.device_canvases[serial] = canvas

        canvas.bind("<ButtonPress-1>", lambda event: self.start_press(event, serial))
        canvas.bind("<ButtonRelease-1>", lambda event: self.handle_release(event, serial))

        # Action Buttons Frame
        button_frame = ctk.CTkFrame(device_frame, fg_color="transparent")
        button_frame.pack(pady=(15, 0), fill="x")
        # Center the buttons
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        button_frame.columnconfigure(2, weight=1)
        button_frame.columnconfigure(3, weight=1)
        button_frame.columnconfigure(4, weight=1)
        button_frame.columnconfigure(5, weight=1)

        # --- NEW Styled Buttons ---
        button_style = {'corner_radius': 8, 'width': 100,
                        'fg_color': self.COLOR_FRAME,
                        'hover_color': self.COLOR_BORDER,
                        'text_color': self.COLOR_TEXT_PRIMARY,
                        'border_color': self.COLOR_BORDER, 'border_width': 1,
                        'height': 40, 'font': self.FONT_BUTTON}

        button_padx = 4

        # MINIMIZE / HOME (KEYCODE 3)
        home_button = ctk.CTkButton(button_frame, text="HOME 🏠", command=lambda: self.send_adb_keyevent(3),
                                    **button_style)
        home_button.grid(row=0, column=0, padx=button_padx, sticky="ew")

        # RESTORE DOWN / BACK (KEYCODE 4)
        back_button = ctk.CTkButton(button_frame, text="BACK ↩️", command=lambda: self.send_adb_keyevent(4),
                                    **button_style)
        back_button.grid(row=0, column=1, padx=button_padx, sticky="ew")

        # RECENTS (KEYCODE 187)
        recents_button = ctk.CTkButton(button_frame, text="RECENTS", command=lambda: self.send_adb_keyevent(187),
                                       **button_style)
        recents_button.grid(row=0, column=2, padx=button_padx, sticky="ew")

        # Swipes
        scroll_down_button = ctk.CTkButton(button_frame, text="SCROLL DOWN",
                                           command=lambda: self.send_adb_swipe(serial, 'up'), **button_style)
        scroll_down_button.grid(row=0, column=3, padx=button_padx, sticky="ew")

        scroll_up_button = ctk.CTkButton(button_frame, text="SCROLL UP",
                                         command=lambda: self.send_adb_swipe(serial, 'down'), **button_style)
        scroll_up_button.grid(row=0, column=4, padx=button_padx, sticky="ew")

        # CLOSE / POWER (KEYCODE 26) - Simulates pressing the power button
        close_button = ctk.CTkButton(button_frame, text="SCREEN OFF 💡", command=lambda: self.send_adb_keyevent(26),
                                     corner_radius=8, width=100,
                                     fg_color=self.COLOR_DANGER,
                                     hover_color=self.COLOR_DANGER_HOVER,
                                     text_color=self.COLOR_TEXT_PRIMARY, height=40,
                                     font=self.FONT_BUTTON)
        close_button.grid(row=0, column=5, padx=button_padx, sticky="ew")

    def on_canvas_container_resize(self, event):
        # ... (Implementation remains the same, ensuring aspect ratio is maintained)
        if not self.selected_device_serial:
            return

        canvas = self.device_canvases.get(self.selected_device_serial)
        if not canvas:
            return

        container_width = event.width
        container_height = event.height

        # Calculate new canvas size to maintain aspect ratio (e.g., 9:16 for most phones)
        aspect_ratio = 9 / 16

        # Determine whether to scale based on width or height
        if container_width / container_height > aspect_ratio:
            new_height = container_height
            new_width = int(new_height * aspect_ratio)
        else:
            new_width = container_width
            new_height = int(new_width / aspect_ratio)

        # Update canvas size and position it in the center
        canvas.configure(width=new_width, height=new_height)
        canvas.place(relx=0.5, rely=0.5, anchor=tk.CENTER, width=new_width, height=new_height)

        # Trigger an image update to resize the image
        self.after(10, self.update_image)  # Use after to ensure canvas size has updated

    def start_press(self, event, serial):
        # ... (Existing implementation is fine)
        self.press_time[serial] = time.time()
        self.press_start_coords[serial] = (event.x, event.y)

    def handle_release(self, event, serial):
        # ... (Existing implementation is fine)
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

    # Helper function to get scaled coordinates (reused for tap/long-press/swipe)
    def _get_scaled_coords(self, canvas_x, canvas_y, serial):
        """Calculates ADB screen coordinates from canvas coordinates."""
        pil_image_info = self.device_images.get(self.selected_device_serial, {})
        pil_image = pil_image_info.get('pil_image')

        if not pil_image:
            # print("Image not loaded for scaling.")
            return None, None

        img_width, img_height = pil_image.size
        canvas = self.device_canvases[serial]
        canvas_width = canvas.winfo_width()
        canvas_height = canvas.winfo_height()

        canvas_aspect = canvas_width / canvas_height
        image_aspect = img_width / img_height

        # Calculate effective image area on canvas
        if canvas_aspect > image_aspect:
            effective_height = canvas_height
            effective_width = int(effective_height * image_aspect)
        else:
            effective_width = canvas_width
            # FIX: Use effective_width (which is set to canvas_width) instead of the undefined new_width
            effective_height = int(effective_width / image_aspect)

        image_x_offset = (canvas_width - effective_width) // 2
        image_y_offset = (canvas_height - effective_height) // 2

        click_x = canvas_x - image_x_offset
        click_y = canvas_y - image_y_offset

        if not (0 <= click_x < effective_width and 0 <= click_y < effective_height):
            # Click was outside the effective image area
            return None, None

        # Get device screen size from ADB
        try:
            adb_size_output = subprocess.run(['adb', '-s', serial, 'shell', 'wm', 'size'], capture_output=True,
                                             text=True, check=True, timeout=5).stdout.strip()
            adb_width, adb_height = map(int, adb_size_output.split()[-1].split('x'))
        except Exception:
            # print("Could not get device screen size.")
            return None, None

        scaled_x = int(click_x * adb_width / effective_width)
        scaled_y = int(click_y * adb_height / effective_height)

        return scaled_x, scaled_y

    def send_adb_tap(self, event, serial):
        scaled_x, scaled_y = self._get_scaled_coords(event.x, event.y, serial)
        if scaled_x is None:
            self.status_label.configure(text=f"⚠️ Tap ignored (outside screen area).", text_color=self.COLOR_WARNING)
            return

        command = ['shell', 'input', 'tap', str(scaled_x), str(scaled_y)]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text=f"✅ TAP command sent.", text_color=self.COLOR_SUCCESS)

    def send_adb_long_press(self, event, serial):
        scaled_x, scaled_y = self._get_scaled_coords(event.x, event.y, serial)
        if scaled_x is None:
            self.status_label.configure(text=f"⚠️ Long press ignored (outside screen area).",
                                        text_color=self.COLOR_WARNING)
            return

        # Long press is implemented as a swipe from (x, y) to (x, y) over 1000ms
        command = ['shell', 'input', 'swipe', str(scaled_x), str(scaled_y), str(scaled_x), str(scaled_y), '1000']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text=f"✅ LONG PRESS command sent.", text_color=self.COLOR_SUCCESS)

    def send_adb_swipe_command(self, start_x, start_y, end_x, end_y, serial):
        scaled_start_x, scaled_start_y = self._get_scaled_coords(start_x, start_y, serial)
        scaled_end_x, scaled_end_y = self._get_scaled_coords(end_x, end_y, serial)

        if scaled_start_x is None or scaled_end_x is None:
            self.status_label.configure(text=f"⚠️ Swipe ignored (outside screen area).", text_color=self.COLOR_WARNING)
            return

        # Swipe duration set to 300ms
        command = ['shell', 'input', 'swipe',
                   str(scaled_start_x), str(scaled_start_y),
                   str(scaled_end_x), str(scaled_end_y), '300']

        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text=f"✅ SWIPE command sent.", text_color=self.COLOR_SUCCESS)

    def send_adb_swipe(self, serial, direction):
        # This method handles the pre-defined scroll up/down buttons
        try:
            adb_width_str = subprocess.run(['adb', '-s', serial, 'shell', 'wm', 'size'], capture_output=True, text=True,
                                           check=True).stdout.strip().split()[-1]
            adb_width, adb_height = map(int, adb_width_str.split('x'))

            # Fixed swipe coordinates for a full-screen scroll
            if direction == 'down':  # Scroll down (swipe up)
                start_x, start_y = adb_width // 2, adb_height // 4 * 3  # Bottom quarter
                end_x, end_y = start_x, adb_height // 4  # Top quarter
            elif direction == 'up':  # Scroll up (swipe down)
                start_x, start_y = adb_width // 2, adb_height // 4
                end_x, end_y = start_x, adb_height // 4 * 3

            command = ['shell', 'input', 'swipe',
                       str(start_x), str(start_y), str(end_x), str(end_y), '300']
            for device_serial in self.devices:
                self.executor.submit(run_adb_command, command, device_serial)
            self.status_label.configure(text=f"✅ {direction.upper()} SCROLL command sent.",
                                        text_color=self.COLOR_SUCCESS)
        except Exception as e:
            self.status_label.configure(text=f"❌ ERROR: Failed to send scroll command: {e}",
                                        text_color=self.COLOR_DANGER)

    def send_adb_keyevent(self, keycode):
        command = ['shell', 'input', 'keyevent', str(keycode)]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)

        key_name = {3: "HOME", 4: "BACK", 187: "RECENTS", 24: "VOL UP", 25: "VOL DOWN", 26: "POWER/SCREEN OFF"}.get(
            keycode, "KEY EVENT")
        self.status_label.configure(text=f"✅ {key_name} command sent.", text_color=self.COLOR_SUCCESS)

    def open_fb_lite_deeplink(self):
        # ... (Implementation remains the same, adjusted status text colors)
        post_url = self.fb_url_entry.get()
        if not post_url or not self.devices:
            self.status_label.configure(text="⚠️ Check URL and devices.", text_color=self.COLOR_WARNING)
            return

        self.status_label.configure(text=f"[CMD] Opening FB post URL...", text_color=self.COLOR_ACCENT)

        command = [
            'shell', 'am', 'start',
            '-a', 'android.intent.action.VIEW',
            '-d', f'"{post_url}"',
            'com.facebook.lite'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Visited FB post on all devices.", text_color=self.COLOR_SUCCESS)

    def share_fb_lite_deeplink(self):
        # --- REMOVED this method, as the single share button is gone, replaced by auto-type logic ---
        # The share command logic is now inside _threaded_find_click_type_LOOP's failure case.
        self.status_label.configure(text="⚠️ Use 'Start Auto-Type' to share links from pairs list.",
                                    text_color=self.COLOR_WARNING)

    def launch_fb_lite(self):
        # ... (Implementation remains the same, adjusted status text colors)
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color=self.COLOR_WARNING)
            return

        self.status_label.configure(text=f"[CMD] Launching Facebook Lite...", text_color=self.COLOR_ACCENT)

        command = ['shell', 'am', 'start', '-n', 'com.facebook.lite/com.facebook.lite.MainActivity']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Launched Facebook Lite on all devices.", text_color=self.COLOR_SUCCESS)

    def force_stop_fb_lite(self):
        # ... (Implementation remains the same, adjusted status text colors)
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color=self.COLOR_WARNING)
            return

        self.status_label.configure(text=f"[CMD] Force stopping Facebook Lite...", text_color=self.COLOR_DANGER)

        command = ['shell', 'am', 'force-stop', 'com.facebook.lite']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Force stopped Facebook Lite on all devices.", text_color=self.COLOR_SUCCESS)

    def share_image_to_fb_lite(self):
        # ... (Implementation remains the same, adjusted status text colors)
        file_name = self.image_file_name_entry.get()
        if not file_name or not self.devices:
            self.status_label.configure(text="⚠️ Check image filename and devices.", text_color=self.COLOR_WARNING)
            return

        self.status_label.configure(text=f"[CMD] Sending sharing intent for '{file_name}'...",
                                    text_color=self.COLOR_ACCENT)

        device_path = f'/sdcard/Download/{file_name}'
        command = [
            'shell', 'am', 'start',
            '-a', 'android.intent.action.SEND',
            '-t', 'image/jpeg',
            '--eu', 'android.intent.extra.STREAM', f'file://{device_path}',
            'com.facebook.lite'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Image sharing command sent to all devices.", text_color=self.COLOR_SUCCESS)

    def stop_all_commands(self):
        # ... (Implementation remains the same, adjusted status text colors and max workers)
        self.status_label.configure(text="⚠️ TERMINATING ALL ACTIVE COMMANDS...", text_color=self.COLOR_WARNING)
        is_stop_requested.set()

        # --- NEW: Also clear the auto-type flag ---
        self.stop_auto_type_loop()  # Use new function

        # Wait for all current tasks to finish (or be terminated)
        self.executor.shutdown(wait=True)

        # Reset the executor and the flag for new commands
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count() * 4)
        is_stop_requested.clear()

        self.status_label.configure(text="✅ ALL OPERATIONS TERMINATED. Ready.", text_color=self.COLOR_SUCCESS)


if __name__ == '__main__':
    multiprocessing.freeze_support()
    app = AdbControllerApp()
    app.mainloop()
