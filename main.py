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
import uuid  # Added for explicit import, though it was in the snippet
import xml.etree.ElementTree as ET  # For XML parsing

# --- App Version and Update URL ---
__version__ = "1.3.9"  # Updated version number
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
    Sends a specific text string as individual ADB text commands with a delay.
    """
    if is_stop_requested.is_set():
        # print(f"🛑 Stop signal received. Aborting text command on device {serial}.")
        return

    if not text_to_send:
        # print(f"Text is empty. Cannot send command to {serial}.")
        return

    # Replace spaces with %s for ADB
    # ADB shell input text handles quotes, so we'll wrap the whole thing
    # This is often more reliable than char-by-char for long text
    formatted_text = text_to_send.replace(" ", "%s")

    try:
        command = ['shell', 'input', 'text', formatted_text]
        subprocess.run(['adb', '-s', serial] + command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True, timeout=15)

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

        # --- Configuration for Minimalist Tech Look ---
        self.title(f"ADB BY DARS: V{__version__}")
        # Removed fullscreen attribute. Set initial size and start zoomed/maximized.
        self.geometry("1200x800")
        self.state('zoomed')
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # Minimalist Tech Color Palette
        self.ACCENT_COLOR = "#FFFFFF"  # Primary control accent (White/Light Gray)
        self.ACCENT_HOVER = "#A9A9A9"  # Lighter hover state
        self.DANGER_COLOR = "#FF6347"  # Tomato Red for clear warnings/stops
        self.SUCCESS_COLOR = "#00FF7F"  # Spring Green for success/install
        self.WARNING_COLOR = "#FFA500"  # Orange for power/reboot
        self.BACKGROUND_COLOR = "#181818"  # Ultra dark background
        self.FRAME_COLOR = "#2C2C2C"  # Clear separation for internal frames
        self.TEXT_COLOR = "#E0E0E0"  # Off-white text

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
        self.apk_path = None  # New variable for APK installation
        self.is_muted = False  # State for volume control
        self.update_check_job = None  # New attribute for scheduled check

        # New attributes for GET TOKEN tab
        self.token_results_textbox = None
        self.account_file_path_entry = None

        # --- NEW: State for auto-typing loop ---
        self.is_auto_typing = threading.Event()

        # Use a higher max_workers count as I/O operations (ADB) are often blocking
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count() * 4)

        # Main window grid configuration: 1/4 size for Control Panel, 3/4 for Device View
        self.grid_columnconfigure(0, weight=1, minsize=600)  # Control Panel (Left)
        self.grid_columnconfigure(1, weight=3)  # Device View (Right)
        self.grid_rowconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- Control Panel Setup (Left) ---
        self.control_panel = ctk.CTkFrame(self, corner_radius=15, fg_color=self.FRAME_COLOR)
        self.control_panel.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.control_panel.grid_columnconfigure(0, weight=1)

        self.control_panel_scrollable = ctk.CTkScrollableFrame(self.control_panel, fg_color="transparent")
        self.control_panel_scrollable.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.control_panel_scrollable.grid_columnconfigure(0, weight=1)

        # Title - White and bold
        ctk.CTkLabel(self.control_panel_scrollable, text=f"ADB TOOL BY DARS: V{__version__}",
                     font=ctk.CTkFont(size=36, weight="bold"),
                     text_color=self.ACCENT_COLOR).grid(
            row=0, column=0, pady=(20, 10), sticky='ew', padx=25)

        # Separator - Distinct white line
        ctk.CTkFrame(self.control_panel_scrollable, height=2, fg_color=self.ACCENT_COLOR).grid(row=1, column=0,
                                                                                               sticky='ew',
                                                                                               padx=25, pady=15)

        # --- (Removed GUI Window Control Section) ---
        # The rows for GUI control buttons were 2 and 3, now shifted up.

        # Device Management Section (Now at row 2, shifted from row 4)
        device_section_frame = ctk.CTkFrame(self.control_panel_scrollable, fg_color="transparent")
        device_section_frame.grid(row=2, column=0, sticky="ew", padx=25, pady=5)
        device_section_frame.grid_columnconfigure(0, weight=1)
        device_section_frame.grid_columnconfigure(1, weight=1)

        self.device_count_label = ctk.CTkLabel(device_section_frame, text="DEVICES: 0",
                                               font=ctk.CTkFont(size=16, weight="bold"), text_color=self.TEXT_COLOR)
        self.device_count_label.grid(row=0, column=0, sticky='w', pady=(0, 5))

        self.detect_button = ctk.CTkButton(device_section_frame, text="REFRESH", command=self.detect_devices,
                                           width=120, corner_radius=8, fg_color="#3A3A3A", hover_color="#555555",
                                           font=ctk.CTkFont(size=14, weight="bold"), border_color=self.ACCENT_COLOR,
                                           border_width=1)
        self.detect_button.grid(row=0, column=1, sticky='e', pady=(0, 5))

        self.update_button = ctk.CTkButton(device_section_frame, text=f"UPDATE NOW (V{__version__})",
                                           command=self.update_app,
                                           fg_color="#444444", hover_color="#666666", corner_radius=8,
                                           font=ctk.CTkFont(size=14, weight="bold"), height=35,
                                           text_color=self.ACCENT_COLOR)
        self.update_button.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(5, 10))

        # Device List - Light text on dark background with clear selection highlight (Now at row 3, shifted from row 5)
        self.device_listbox = tk.Listbox(self.control_panel_scrollable, height=6, font=("Consolas", 14),
                                         # Mono font for tech feel
                                         bg=self.BACKGROUND_COLOR, fg=self.SUCCESS_COLOR,
                                         selectbackground=self.ACCENT_COLOR,
                                         selectforeground="#101010", borderwidth=0, highlightthickness=1,
                                         highlightcolor=self.ACCENT_COLOR, relief='flat')
        self.device_listbox.grid(row=3, column=0, sticky='ew', padx=25, pady=(5, 20))
        self.device_listbox.bind('<<ListboxSelect>>', self.on_device_select)

        # Tab View - White segmented buttons for clean look (Now at row 4, shifted from row 6)
        self.tab_view = ctk.CTkTabview(self.control_panel_scrollable,
                                       segmented_button_selected_color=self.ACCENT_COLOR,
                                       segmented_button_selected_hover_color=self.ACCENT_HOVER,
                                       segmented_button_unselected_hover_color="#3A3A3A",
                                       segmented_button_unselected_color=self.FRAME_COLOR,
                                       text_color=self.TEXT_COLOR,
                                       corner_radius=10,
                                       height=550)
        self.tab_view.grid(row=4, column=0, sticky="nsew", padx=25, pady=10)

        self.tab_view.add("About")
        self.tab_view.add("ADB Utilities")
        self.tab_view.add("FB Lite")
        self.tab_view.add("TikTok")
        self.tab_view.add("YouTube")
        # self.tab_view.add("Text Cmd") # REMOVED
        self.tab_view.add("Image")
        self.tab_view.add("FB API")
        self.tab_view.add("GET TOKEN")  # ADDED NEW TAB
        self.tab_view.set("FB Lite")  # Start on the FB Lite tab

        self._configure_tab_layouts()

        # Status Bar - Thicker status bar at the bottom (Now at row 5, shifted from row 7)
        self.status_label = ctk.CTkLabel(self.control_panel_scrollable, text="Awaiting Command...", anchor='w',
                                         font=("Consolas", 15, "italic"), text_color="#A9A9A9", height=40)
        self.status_label.grid(row=5, column=0, sticky='ew', padx=25, pady=(10, 0))

        # --- Device View Panel Setup (Right) ---
        self.device_view_panel = ctk.CTkFrame(self, fg_color=self.BACKGROUND_COLOR, corner_radius=15)
        self.device_view_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=20)
        self.device_view_panel.grid_columnconfigure(0, weight=1)
        self.device_view_panel.grid_rowconfigure(0, weight=1)

        self.stop_all_button = ctk.CTkButton(self.device_view_panel, text="TERMINATE ALL OPERATIONS",
                                             command=self.stop_all_commands, fg_color=self.DANGER_COLOR,
                                             hover_color="#CC301A", text_color=self.ACCENT_COLOR, corner_radius=10,
                                             font=ctk.CTkFont(size=18, weight="bold"), height=60)
        self.stop_all_button.pack(side="bottom", fill="x", padx=15, pady=(0, 15))

        self.detect_devices()
        self.check_for_updates()

        # Start the recurring check after initial setup
        self.start_periodic_update_check()

    # --- New Methods for GET TOKEN Tab ---

    def Login_API(self, email: str, password: str):
        """
        Performs the API request to retrieve the access token using the user's provided logic.
        """
        r = requests.Session()

        # Define headers (using the user's provided headers)
        head = {
            'Host': 'b-graph.facebook.com',
            'X-Fb-Connection-Quality': 'EXCELLENT',
            'Authorization': 'OAuth 350685531728|62f8ce9f74b12f84c123cc23437a4a32',
            'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 7.1.2; RMX3740 Build/QP1A.190711.020) [FBAN/FB4A;FBAV/417.0.0.33.65;FBPN/com.facebook.katana;FBLC/in_ID;FBBV/480086274;FBCR/Corporation Tbk;FBMF/realme;FBBD/realme;FBDV/RMX3740;FBSV/7.1.2;FBCA/x86:armeabi-v7a;FBDM/{density=1.0,width=540,height=960};FB_FW/1;FBRV/483172840;]',
            'X-Tigon-Is-Retry': 'false',
            'X-Fb-Friendly-Name': 'authenticate',
            'X-Fb-Connection-Bandwidth': str(random.randrange(70000000, 80000000)),
            'Zero-Rated': '0',
            'X-Fb-Net-Hni': str(random.randrange(50000, 60000)),
            'X-Fb-Sim-Hni': str(random.randrange(50000, 60000)),
            'X-Fb-Request-Analytics-Tags': '{"network_tags":{"product":"350685531728","retry_attempt":"0"},"application_tags":"unknown"}',
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Fb-Connection-Type': 'WIFI',
            'X-Fb-Device-Group': str(random.randrange(4700, 5000)),
            'Priority': 'u=3,i',
            'Accept-Encoding': 'gzip, deflate',
            'X-Fb-Http-Engine': 'Liger',
            'X-Fb-Client-Ip': 'true',
            'X-Fb-Server-Cluster': 'true',
            'Content-Length': str(random.randrange(1500, 2000)),
            'cache-control': "private, no-cache, no-store, must-revalidate",
            "facebook-api-version": "v1.0",
            "pragma": "no-cache",
            "priority": "u=0,i",
            "strict-transport-security": "max-age=15552000; preload",
            "vary": "Accept-Encoding",
            "x-fb-connection-quality": "GOOD; q=0.7, rtt=73, rtx=0, c=23, mss=1232, tbw=5012, tp=10, tpl=0, uplat=405, ullat=0",
            "x-fb-debug": "g/lwUlHD6vXZly0pnMoWnhifQ8PoyIuzDnUKVk5ZWru6+2XT2yaUB9Y/TSXbt0/637lElrllnUhGyXNJLheBKA==",
            "x-fb-request-id": "AEJauAi2IHwyhd_zl3pC-4E",
            "x-fb-rev": "1025308755",
            "x-fb-trace-id": "C/GnaBOOeUa",
            "x-frame-options": "DENY"
        }

        # Define data payload (using the user's provided data)
        data = {
            'adid': str(uuid.uuid4()),
            'format': 'json',
            'device_id': str(uuid.uuid4()),
            'email': email,
            'password': f'#PWD_FB4A:0:{str(time.time())[:10]}:{password}',
            'generate_analytics_claim': '1',
            'community_id': '',
            'linked_guest_account_userid': '',
            'cpl': True,
            'try_num': '1',
            'family_device_id': str(uuid.uuid4()),
            'secure_family_device_id': str(uuid.uuid4()),
            'credentials_type': 'password',
            'account_switcher_uids': [],
            'fb4a_shared_phone_cpl_experiment': 'fb4a_shared_phone_nonce_cpl_at_risk_v3',
            'fb4a_shared_phone_cpl_group': 'enable_v3_at_risk',
            'enroll_misauth': False,
            'generate_session_cookies': '1',
            'error_detail_type': 'button_with_disabled',
            'source': 'login',
            'machine_id': ''.join(
                [random.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for i in range(24)]),
            'jazoest': str(random.randrange(22000, 23000)),
            'meta_inf_fbmeta': 'V2_UNTAGGED',
            'advertiser_id': str(uuid.uuid4()),
            'encrypted_msisdn': '',
            'currently_logged_in_userid': '0',
            'locale': 'id_ID',
            'client_country_code': 'ID',
            'fb_api_req_friendly_name': 'authenticate',
            'fb_api_caller_class': 'Fb4aAuthHandler',
            'api_key': '882a8490361da98702bf97a021ddc14d',
            'sig': hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()[:32],
            'access_token': '350685531728|62f8ce9f74b12f84c123cc23437a4a32'
        }

        try:
            pos = r.post('https://b-graph.facebook.com/auth/login', data=data, headers=head, timeout=15).json()

            if ('session_key' in str(pos)) and ('access_token' in str(pos)):
                token = pos['access_token']
                # Success: return email and token
                return email, token, None

            elif 'error' in pos and 'message' in pos['error']:
                error_msg = pos['error']['message']
                # Failure: return email and error message
                return email, None, error_msg
            else:
                # Unknown error format
                return email, None, "Unknown error format: " + json.dumps(pos)

        except requests.exceptions.RequestException as e:
            # Network or Timeout error
            return email, None, f"Network Error: {e.__class__.__name__}"
        except Exception as e:
            # General error
            return email, None, f"General Error: {e}"

    def browse_account_file(self):
        """Opens a file dialog to select the account.txt file."""
        file_path = filedialog.askopenfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if file_path:
            self.account_file_path_entry.delete(0, tk.END)
            self.account_file_path_entry.insert(0, file_path)
            self.status_label.configure(text=f"✅ ACCOUNT FILE SELECTED: {os.path.basename(file_path)}",
                                        text_color=self.SUCCESS_COLOR)

    def start_token_retrieval(self):
        """Executes the token retrieval process in a separate thread."""
        file_path = self.account_file_path_entry.get().strip()
        if not file_path or not os.path.exists(file_path):
            self.status_label.configure(text="⚠️ Please select a valid account file.", text_color="#ffc107")
            return

        self.token_results_textbox.configure(state="normal")
        self.token_results_textbox.delete("1.0", "end")
        self.token_results_textbox.insert("end", f"Starting retrieval from {os.path.basename(file_path)}...\n")
        self.token_results_textbox.configure(state="disabled")

        # Start the token retrieval in a thread
        threading.Thread(target=self._threaded_get_token_from_file, args=(file_path,), daemon=True).start()

    def _threaded_get_token_from_file(self, file_path):
        """
        Reads the account file and attempts to get a token for each account.
        Saves successful tokens to token.txt.
        """
        if is_stop_requested.is_set():
            self.after(0, lambda: self.status_label.configure(
                text="🛑 Operation terminated by user.", text_color="#ffc107"))
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_lines = f.readlines()

            account_lines = [line.strip() for line in raw_lines if line.strip()]

        except FileNotFoundError:
            self.after(0, lambda: self.status_label.configure(
                text="❌ ERROR: Account file not found.", text_color=self.DANGER_COLOR))
            return
        except Exception as e:
            self.after(0, lambda: self.status_label.configure(
                text=f"❌ ERROR reading account file: {e}", text_color=self.DANGER_COLOR))
            return

        total_accounts = len(account_lines)
        success_count = 0

        # Determine output file path (e.g., in the same directory as the account file)
        output_dir = Path(file_path).parent
        token_file_path = output_dir / "token.txt"

        self.after(0, lambda: self.status_label.configure(
            text=f"[CMD] Starting token retrieval for {total_accounts} accounts...", text_color=self.ACCENT_COLOR))

        # Open token.txt file in append mode before starting the loop
        # This will create the file if it doesn't exist.
        try:
            token_file = open(token_file_path, 'a', encoding='utf-8')
        except Exception as e:
            self.after(0, lambda: self.status_label.configure(
                text=f"❌ ERROR opening token.txt for writing: {e}", text_color=self.DANGER_COLOR))
            self.after(0, lambda: self._append_result(
                f"[FAIL] Could not save to token.txt: {e}", self.DANGER_COLOR))
            return

        # Use ThreadPoolExecutor for concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_account = {}
            for i, line in enumerate(account_lines):
                if is_stop_requested.is_set():
                    break

                try:
                    # Expecting format: email\tpassword (tab separated)
                    email, password = line.split('\t', 1)
                    email = email.strip()
                    password = password.strip()

                    if not email or not password:
                        self.after(0, lambda line=line: self._append_result(
                            f"[FAIL] Invalid line format: {line.split()[0]}... (Missing email or password)",
                            self.WARNING_COLOR))
                        continue

                    # Submit the task to the executor
                    future = executor.submit(self.Login_API, email, password)
                    future_to_account[future] = email

                except ValueError:
                    self.after(0, lambda line=line: self._append_result(
                        f"[FAIL] Invalid line format: {line[:30]}... (Not tab-separated)", self.WARNING_COLOR))

                # Small pause to avoid immediately overwhelming the server/network
                time.sleep(0.05)

            # Process results as they complete
            for future in concurrent.futures.as_completed(future_to_account):
                if is_stop_requested.is_set():
                    break

                email = future_to_account[future]
                try:
                    email, token, error_msg = future.result()

                    if token:
                        success_count += 1
                        result_text = f"[SUCCESS] {email} -> {token}"

                        # --- SAVING TOKEN TO FILE ---
                        try:
                            token_file.write(f"{email}\t{token}\n")
                            # Flush to ensure immediate write to disk
                            token_file.flush()
                        except Exception as e:
                            self.after(0, lambda: self._append_result(
                                f"[FAIL] Failed to write token for {email} to token.txt: {e}", self.DANGER_COLOR))
                        # --- END SAVING TOKEN TO FILE ---

                        self.after(0, lambda result=result_text: self._append_result(result, self.SUCCESS_COLOR))
                        # Update status label with progress
                        self.after(0, lambda count=success_count, total=total_accounts: self.status_label.configure(
                            text=f"[{count}/{total}] Retrieving tokens... ({total - count} remaining)",
                            text_color=self.ACCENT_COLOR))
                    else:
                        result_text = f"[FAIL] {email} -> {error_msg}"
                        self.after(0, lambda result=result_text: self._append_result(result, self.DANGER_COLOR))
                        # Update status label even on failure
                        self.after(0, lambda count=success_count, total=total_accounts: self.status_label.configure(
                            text=f"[{count}/{total}] Retrieving tokens... ({total - count} remaining)",
                            text_color=self.ACCENT_COLOR))

                except Exception as exc:
                    result_text = f"[FAIL] {email} generated an exception: {exc.__class__.__name__}"
                    self.after(0, lambda result=result_text: self._append_result(result, self.DANGER_COLOR))

        # Close the token file after all operations are done
        token_file.close()

        final_message = f"✅ RETRIEVAL COMPLETE. Total successful tokens: {success_count} / {total_accounts}. Saved to {token_file_path.name}"
        self.after(0, lambda: self.status_label.configure(text=final_message, text_color=self.SUCCESS_COLOR))
        self.after(0, lambda: self._append_result(final_message.split('.')[0] + ".", self.SUCCESS_COLOR))

    def _append_result(self, message, color):
        """Helper to safely append results to the textbox from a non-main thread with color tags."""
        self.token_results_textbox.configure(state="normal")

        # Determine current content length to apply tag correctly
        current_content = self.token_results_textbox.get("1.0", "end-1c")
        start_index = self.token_results_textbox.index("end-1c")

        if current_content.strip():
            # If content exists, insert newline before the message
            self.token_results_textbox.insert("end", "\n")
            start_index = self.token_results_textbox.index("end-1c")
            self.token_results_textbox.insert("end", message)
        else:
            # If empty, just insert the message
            start_index = self.token_results_textbox.index("end-1c")
            self.token_results_textbox.insert("end", message)

        # Apply the tag to the inserted message
        self.token_results_textbox.tag_config(self.SUCCESS_COLOR, foreground=self.SUCCESS_COLOR)
        self.token_results_textbox.tag_config(self.DANGER_COLOR, foreground=self.DANGER_COLOR)
        self.token_results_textbox.tag_config(self.WARNING_COLOR, foreground=self.WARNING_COLOR)

        # Apply the color tag using start_index (where message starts) and end
        self.token_results_textbox.tag_add(color, start_index, "end")

        self.token_results_textbox.see("end")
        self.token_results_textbox.configure(state="disabled")

    # --- End of New Methods for GET TOKEN Tab ---

    # NEW METHOD: Setup periodic update check
    def start_periodic_update_check(self):
        """Starts a recurring, silent update check every 60 seconds (60000 ms)."""
        # 60000 milliseconds = 1 minute
        self.update_check_job = self.after(60000, self._periodic_check_updates)

    def _periodic_check_updates(self):
        """Internal method called periodically to silently check for updates."""
        # We run the check in a thread to keep the GUI responsive
        threading.Thread(target=self._check_and_reschedule, daemon=True).start()

    def _check_and_reschedule(self):
        """Checks for updates and reschedules the next check."""
        try:
            # Only perform the actual network check. Do not update the status label unless an error occurs or an update is found.
            response = requests.get(VERSION_CHECK_URL, timeout=10)
            response.raise_for_status()

            latest_version = response.text.strip()
            if latest_version > __version__:
                # Only show prompt if a new version is available
                self.after(0, self.ask_for_update, latest_version)

        except requests.exceptions.RequestException:
            # Errors are expected occasionally (e.g., no internet/server down).
            # We fail silently as requested. No status bar update is performed here.
            pass
        except Exception:
            # Catch all other unexpected errors silently
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
                if latest_version > __version__:
                    self.after(0, self.ask_for_update, latest_version)

            except requests.exceptions.HTTPError as http_err:
                status_code = http_err.response.status_code
                self.after(0, lambda: self.status_label.configure(
                    text=f"❌ ERROR: Failed to check for update. HTTP Status: {status_code}",
                    text_color=self.DANGER_COLOR))
                self.after(0, lambda: messagebox.showwarning(
                    "Update Check Failed",
                    f"Unable to reach the update server (HTTP Error {status_code}). Check your network or firewall settings."))
            except requests.exceptions.ConnectionError:
                self.after(0, lambda: self.status_label.configure(
                    text="❌ ERROR: Failed to check for update. Connection Refused.",
                    text_color=self.DANGER_COLOR))
                self.after(0, lambda: messagebox.showwarning(
                    "Update Check Failed",
                    "Cannot connect to the update server. Check your internet connection, firewall, or proxy."))
            except requests.exceptions.Timeout:
                self.after(0, lambda: self.status_label.configure(
                    text="❌ ERROR: Failed to check for update. Connection Timed Out.",
                    text_color=self.DANGER_COLOR))
                self.after(0, lambda: messagebox.showwarning(
                    "Update Check Failed",
                    "The connection timed out while checking for updates. Your network might be slow or unstable."))
            except requests.exceptions.RequestException as e:
                self.after(0, lambda: self.status_label.configure(
                    text=f"❌ ERROR: Failed to check for update. Details: {e.__class__.__name__}",
                    text_color=self.DANGER_COLOR))
                self.after(0, lambda: messagebox.showwarning(
                    "Update Check Failed",
                    f"An error occurred during update check: {e.__class__.__name__}. Check logs for details."))
            except Exception:
                # Catch all other unexpected errors
                self.after(0, lambda: self.status_label.configure(
                    text="❌ ERROR: An unexpected error occurred during version check.",
                    text_color=self.DANGER_COLOR))
                self.after(0, lambda: messagebox.showwarning(
                    "Update Check Failed",
                    "An unexpected error occurred during the version check."))

        update_thread = threading.Thread(target=_check_in_thread, daemon=True)
        update_thread.start()

    def ask_for_update(self, latest_version):
        # ... (Existing implementation is fine)
        title = "New ADB Commander Update!"
        message = (
            f"An improved version ({latest_version}) is now available!\n\n"
            "New Auto Click what's on your mind Auto Type caption This update contains the latest upgrades and performance improvements for faster and more reliable control of your devices.\n\n"
            "The app will close and restart to complete the update. Would you like to update now?"
        )

        response = messagebox.askyesno(title, message)
        if response:
            self.update_app()

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

    def _configure_get_token_tab(self, token_frame):
        """Configures the layout for the GET TOKEN tab."""
        token_frame.columnconfigure(0, weight=1)
        token_frame.rowconfigure(5, weight=1)

        # -----------------------------------------------------
        # Section 1: Account File Selection
        # -----------------------------------------------------
        ctk.CTkLabel(token_frame, text="ACCOUNT FILE (email\\tpassword)",
                     font=ctk.CTkFont(size=14, weight="bold"), text_color=self.ACCENT_COLOR).grid(row=0, column=0,
                                                                                                  sticky='w', padx=15,
                                                                                                  pady=(15, 5))
        self.account_file_path_entry = ctk.CTkEntry(token_frame, placeholder_text="Path: Select account file (.txt)...",
                                                    height=40, corner_radius=8)
        self.account_file_path_entry.grid(row=1, column=0, sticky='ew', padx=15)

        browse_account_button = ctk.CTkButton(token_frame, text="BROWSE ACCOUNT FILE 📁",
                                              command=self.browse_account_file,
                                              corner_radius=8, fg_color="#3A3A3A", hover_color="#555555", height=45)
        browse_account_button.grid(row=2, column=0, sticky='ew', padx=15, pady=(10, 15))

        # -----------------------------------------------------
        # Section 2: Start Retrieval Button
        # -----------------------------------------------------
        self.start_token_button = ctk.CTkButton(token_frame, text="START TOKEN RETRIEVAL 🔑",
                                                command=self.start_token_retrieval,
                                                fg_color="#1877f2", hover_color="#1651b7", height=55,
                                                font=ctk.CTkFont(size=16, weight="bold"))
        self.start_token_button.grid(row=3, column=0, sticky='ew', padx=15, pady=(5, 15))

        # -----------------------------------------------------
        # Section 3: Results Console
        # -----------------------------------------------------
        ctk.CTkLabel(token_frame, text="RETRIEVAL RESULTS (Success/Fail)",
                     font=ctk.CTkFont(size=14, weight="bold"), text_color=self.ACCENT_COLOR).grid(row=4, column=0,
                                                                                                  sticky='w', padx=15,
                                                                                                  pady=(10, 5))

        self.token_results_textbox = ctk.CTkTextbox(token_frame, wrap="word", corner_radius=10,
                                                    activate_scrollbars=True,
                                                    font=ctk.CTkFont(size=12, family="Consolas"),
                                                    fg_color=self.BACKGROUND_COLOR,
                                                    border_color="#333333", border_width=1)
        self.token_results_textbox.grid(row=5, column=0, padx=15, pady=(5, 15), sticky="nsew")
        self.token_results_textbox.insert("end", "Status: Ready to retrieve tokens.")
        self.token_results_textbox.configure(state="disabled")

    def _configure_tab_layouts(self):
        """Helper method to configure the grid layout for each tab with improved spacing and the new Utility tab."""

        # --- About Tab ---
        about_frame = self.tab_view.tab("About")
        about_frame.columnconfigure(0, weight=1)
        about_frame.rowconfigure(1, weight=1)

        ctk.CTkLabel(about_frame, text="ADB COMMANDER OVERVIEW",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=self.ACCENT_COLOR).grid(row=0, column=0, pady=(15, 5), sticky="n")

        about_text = f"""The "ADB TOOL BY DARS:" (v{__version__}) is a desktop application designed to simplify the management and control of multiple Android devices simultaneously It leverages the Android Debug Bridge (ADB) to send commands quickly and efficiently Through its simple interface you can perform various tasks such as tapping swiping and running specific commands on all connected devices at once

Getting Started
Connect Your Devices Ensure USB Debugging is enabled on all Android devices you intend to use Then connect them to your computer using USB cables

Refresh the Device List On the left-side control panel click the Refresh button The application will automatically detect and list all connected devices by their serial number

Select the Device to Control Click on a device's serial number from the list When selected the device's screen will appear on the right side of the app allowing you to control it directly

Controlling the Device Screen
The main feature of this tool is the live screen control Once your device is connected and its screen is visible you can perform the following actions

Tap (Single Click) Click anywhere on the screen to simulate a single tap
Swipe Click and drag your mouse on the device screen This will perform a swipe gesture just like on the physical device
Long Press Press and hold the left mouse button for half a second (05s) This will execute a long press command
Additionally there are pre-set buttons below the device screen for quick actions

Home Returns to the device's home screen
Back Navigates back to the previous screen
Recents Shows the list of recently used apps
Scroll Down/Up Scrolls the screen up or down
Additional Features (Tab View)
The left-side panel features a Tab View with various command categories

FB Lite Use this tab to open Facebook posts share links or launch/force-stop the Facebook Lite app. This tab now also includes Text Command functions.
TikTok Open TikTok post URLs or launch/force-stop the TikTok Lite app
YouTube Visit YouTube video URLs or launch/force-stop the YouTube app (using Chrome)
Image Enter the filename of an image in your phone's Download folder to share it via Facebook Lite
FB API Use this tab to post text and links directly to Facebook using the Graph API (requires an Access Token file).
GET TOKEN Use this tab to retrieve a Facebook Access Token from accounts listed in a file (email\\tpassword format).
Important Notes
General Control All commands (except for taps swipes and long presses) are sent to all connected devices simultaneously
Stop All Commands To halt any currently running commands click the Stop All Commands button
Auto-Update The tool includes an update feature Click the Update button to automatically download the latest version to your Desktop
ADB Path Ensure that ADB (Android Debug Bridge) is installed and added to your system's PATH for the application to function correctly"""
        about_text_box = ctk.CTkTextbox(about_frame, wrap="word", corner_radius=10, activate_scrollbars=True,
                                        font=ctk.CTkFont(size=14, family="Consolas"), fg_color=self.BACKGROUND_COLOR,
                                        border_color="#333333", border_width=1)
        about_text_box.grid(row=1, column=0, padx=15, pady=15, sticky="nsew")
        about_text_box.insert("1.0", about_text)
        about_text_box.configure(state="disabled")

        # --- ADB Utilities Tab (REFINED Minimalist Layout) ---
        utility_frame = self.tab_view.tab("ADB Utilities")
        utility_frame.columnconfigure(0, weight=1)
        utility_frame.rowconfigure(13, weight=1)  # Increased row count for the new section

        # -----------------------------------------------------
        # Section 1: System Commands (Reboot/Shutdown)
        # -----------------------------------------------------
        ctk.CTkLabel(utility_frame, text="POWER CONTROL",
                     font=ctk.CTkFont(size=16, weight="bold"), text_color=self.WARNING_COLOR).grid(row=0, column=0,
                                                                                                   sticky='w', padx=15,
                                                                                                   pady=(15, 5))

        system_cmd_frame = ctk.CTkFrame(utility_frame, fg_color=self.FRAME_COLOR)
        system_cmd_frame.grid(row=1, column=0, sticky='ew', padx=15, pady=(5, 10))
        system_cmd_frame.columnconfigure(0, weight=1)
        system_cmd_frame.columnconfigure(1, weight=1)

        reboot_button = ctk.CTkButton(system_cmd_frame, text="REBOOT 🔄", command=self.reboot_devices,
                                      fg_color=self.WARNING_COLOR, hover_color="#CC8400", corner_radius=8, height=40,
                                      text_color=self.BACKGROUND_COLOR)
        reboot_button.grid(row=0, column=0, sticky='ew', padx=(10, 5), pady=10)

        shutdown_button = ctk.CTkButton(system_cmd_frame, text="POWER OFF ❌", command=self.shutdown_devices,
                                        fg_color=self.DANGER_COLOR, hover_color="#CC4028", corner_radius=8, height=40,
                                        text_color=self.ACCENT_COLOR)
        shutdown_button.grid(row=0, column=1, sticky='ew', padx=(5, 10), pady=10)

        # -----------------------------------------------------
        # Section 2: Airplane Mode Control (NEW)
        # -----------------------------------------------------
        ctk.CTkLabel(utility_frame, text="AIRPLANE MODE",
                     font=ctk.CTkFont(size=16, weight="bold"), text_color=self.ACCENT_COLOR).grid(row=2, column=0,
                                                                                                  sticky='w', padx=15,
                                                                                                  pady=(10, 5))

        airplane_mode_frame = ctk.CTkFrame(utility_frame, fg_color=self.FRAME_COLOR)
        airplane_mode_frame.grid(row=3, column=0, sticky='ew', padx=15, pady=(5, 10))
        airplane_mode_frame.columnconfigure(0, weight=1)
        airplane_mode_frame.columnconfigure(1, weight=1)

        enable_airplane_button = ctk.CTkButton(airplane_mode_frame, text="ENABLE AIRPLANE ✈️",
                                               command=self.enable_airplane_mode,
                                               fg_color="#3A3A3A", hover_color="#555555", corner_radius=8, height=40)
        enable_airplane_button.grid(row=0, column=0, sticky='ew', padx=(10, 5), pady=10)

        disable_airplane_button = ctk.CTkButton(airplane_mode_frame, text="DISABLE AIRPLANE 📶",
                                                command=self.disable_airplane_mode,
                                                fg_color=self.SUCCESS_COLOR, hover_color="#00A852", corner_radius=8,
                                                height=40, text_color=self.BACKGROUND_COLOR)
        disable_airplane_button.grid(row=0, column=1, sticky='ew', padx=(5, 10), pady=10)

        # -----------------------------------------------------
        # Section 3: Brightness Control (All Devices) (Shifted from row 2/3 to 4/5)
        # -----------------------------------------------------
        ctk.CTkLabel(utility_frame, text="BRIGHTNESS [0-255]",
                     font=ctk.CTkFont(size=16, weight="bold"), text_color=self.ACCENT_COLOR).grid(row=4, column=0,
                                                                                                  sticky='w', padx=15,
                                                                                                  pady=(10, 5))

        brightness_frame = ctk.CTkFrame(utility_frame, fg_color=self.FRAME_COLOR)
        brightness_frame.grid(row=5, column=0, sticky='ew', padx=15, pady=(5, 10))
        brightness_frame.columnconfigure(0, weight=1)
        brightness_frame.columnconfigure(1, weight=1)
        brightness_frame.columnconfigure(2, weight=1)

        self.brightness_slider = ctk.CTkSlider(brightness_frame, from_=0, to=255, command=self.set_brightness,
                                               number_of_steps=256, button_color=self.ACCENT_COLOR,
                                               button_hover_color=self.ACCENT_HOVER, progress_color=self.ACCENT_COLOR)
        self.brightness_slider.set(128)
        self.brightness_slider.grid(row=0, column=0, columnspan=3, sticky='ew', padx=10, pady=(10, 5))

        # Pre-set Brightness Buttons - Monochromatic gray/white
        ctk.CTkButton(brightness_frame, text="LOW [20]", command=lambda: self.set_brightness(20),
                      fg_color="#3A3A3A", hover_color="#555555", corner_radius=8, height=35).grid(row=1, column=0,
                                                                                                  padx=(10, 5),
                                                                                                  pady=(0, 10),
                                                                                                  sticky='ew')
        ctk.CTkButton(brightness_frame, text="MID [128]", command=lambda: self.set_brightness(128),
                      fg_color="#3A3A3A", hover_color="#555555", corner_radius=8, height=35).grid(row=1, column=1,
                                                                                                  padx=5, pady=(0, 10),
                                                                                                  sticky='ew')
        ctk.CTkButton(brightness_frame, text="MAX [255]", command=lambda: self.set_brightness(255),
                      fg_color=self.ACCENT_COLOR, hover_color=self.ACCENT_HOVER, corner_radius=8, height=35,
                      text_color=self.BACKGROUND_COLOR).grid(row=1, column=2, padx=(5, 10), pady=(0, 10), sticky='ew')

        # -----------------------------------------------------
        # Section 4: Volume Control (All Devices) (Shifted from row 4/5 to 6/7)
        # -----------------------------------------------------
        ctk.CTkLabel(utility_frame, text="VOLUME CONTROL",
                     font=ctk.CTkFont(size=16, weight="bold"), text_color=self.ACCENT_COLOR).grid(row=6, column=0,
                                                                                                  sticky='w', padx=15,
                                                                                                  pady=(10, 5))

        volume_frame = ctk.CTkFrame(utility_frame, fg_color=self.FRAME_COLOR)
        volume_frame.grid(row=7, column=0, sticky='ew', padx=15, pady=(5, 10))
        volume_frame.columnconfigure(0, weight=1)
        volume_frame.columnconfigure(1, weight=1)
        volume_frame.columnconfigure(2, weight=1)

        ctk.CTkButton(volume_frame, text="VOL UP 🔊", command=lambda: self.send_adb_keyevent(24),
                      fg_color=self.SUCCESS_COLOR, hover_color="#00A852", corner_radius=8, height=40,
                      text_color=self.BACKGROUND_COLOR).grid(row=0, column=0, padx=(10, 5), pady=10, sticky='ew')

        ctk.CTkButton(volume_frame, text="VOL DOWN 🔉", command=lambda: self.send_adb_keyevent(25),
                      fg_color="#3A3A3A", hover_color="#555555", corner_radius=8, height=40).grid(row=0, column=1,
                                                                                                  padx=5, pady=10,
                                                                                                  sticky='ew')

        self.mute_button = ctk.CTkButton(volume_frame, text="MUTE 🔇", command=self.toggle_mute,
                                         fg_color="#3A3A3A", hover_color="#555555", corner_radius=8, height=40)
        self.mute_button.grid(row=0, column=2, padx=(5, 10), pady=10, sticky='ew')

        # -----------------------------------------------------
        # Section 5: APK Installation (Shifted from row 6/7/8 to 8/9/10)
        # -----------------------------------------------------
        ctk.CTkLabel(utility_frame, text="APK INSTALLATION",
                     font=ctk.CTkFont(size=16, weight="bold"), text_color=self.ACCENT_COLOR).grid(row=8, column=0,
                                                                                                  sticky='w', padx=15,
                                                                                                  pady=(10, 5))

        self.apk_path_entry = ctk.CTkEntry(utility_frame, placeholder_text="Path: No APK selected...", height=35,
                                           corner_radius=8)
        self.apk_path_entry.grid(row=9, column=0, sticky='ew', padx=15)

        apk_button_frame = ctk.CTkFrame(utility_frame, fg_color="transparent")
        apk_button_frame.grid(row=10, column=0, sticky='ew', padx=15, pady=(5, 15))
        apk_button_frame.columnconfigure(0, weight=1)
        apk_button_frame.columnconfigure(1, weight=1)

        browse_apk_button = ctk.CTkButton(apk_button_frame, text="BROWSE", command=self.browse_apk_file,
                                          fg_color="#3A3A3A", hover_color="#555555", corner_radius=8, height=40)
        browse_apk_button.grid(row=0, column=0, sticky='ew', padx=(0, 5))

        install_apk_button = ctk.CTkButton(apk_button_frame, text="INSTALL APK ⬇️", command=self.install_apk_to_devices,
                                           fg_color=self.SUCCESS_COLOR, hover_color="#00A852", corner_radius=8,
                                           height=40,
                                           font=ctk.CTkFont(weight="bold"), text_color=self.BACKGROUND_COLOR)
        install_apk_button.grid(row=0, column=1, sticky='ew', padx=(5, 0))

        # -----------------------------------------------------
        # Section 6: Custom Shell Command (Shifted from row 9/10/11 to 11/12/13)
        # -----------------------------------------------------
        ctk.CTkLabel(utility_frame, text="CUSTOM SHELL COMMAND",
                     font=ctk.CTkFont(size=16, weight="bold"), text_color=self.ACCENT_COLOR).grid(row=11, column=0,
                                                                                                  sticky='w', padx=15,
                                                                                                  pady=(10, 5))

        self.custom_cmd_entry = ctk.CTkEntry(utility_frame,
                                             placeholder_text="Input arguments (e.g., input keyevent 3)...", height=35,
                                             corner_radius=8)
        self.custom_cmd_entry.grid(row=12, column=0, sticky='ew', padx=15)

        run_custom_button = ctk.CTkButton(utility_frame, text="RUN COMMAND >",
                                          command=self.run_custom_shell_command,
                                          fg_color="#3A3A3A", hover_color="#555555", height=45,
                                          font=ctk.CTkFont(size=14, weight="bold"), text_color=self.ACCENT_COLOR,
                                          border_color=self.ACCENT_COLOR, border_width=1)
        run_custom_button.grid(row=13, column=0, sticky='ew', padx=15, pady=(10, 15))

        # --- Remaining Tabs (Layout is also professionally refined) ---

        # Facebook Lite Tab
        fb_frame = self.tab_view.tab("FB Lite")
        fb_frame.columnconfigure(0, weight=1)
        # fb_frame.rowconfigure(6, weight=1) # Removed fixed row config to allow expansion

        # --- FB Lite App Controls ---
        ctk.CTkLabel(fb_frame, text="FB LITE APP CONTROL", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky='w', padx=15, pady=(15, 5))

        fb_launch_frame = ctk.CTkFrame(fb_frame, fg_color="transparent")
        fb_launch_frame.grid(row=1, column=0, sticky='ew', padx=15, pady=(0, 10))
        fb_launch_frame.columnconfigure(0, weight=1)
        fb_launch_frame.columnconfigure(1, weight=1)
        self.launch_fb_lite_button = ctk.CTkButton(fb_launch_frame, text="Launch FB Lite", command=self.launch_fb_lite,
                                                   corner_radius=8, fg_color="#3A3A3A", hover_color="#555555")
        self.launch_fb_lite_button.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        self.force_stop_fb_lite_button = ctk.CTkButton(fb_launch_frame, text="Force Stop",
                                                       command=self.force_stop_fb_lite, fg_color=self.DANGER_COLOR,
                                                       hover_color="#CC4028", corner_radius=8,
                                                       text_color=self.ACCENT_COLOR)
        self.force_stop_fb_lite_button.grid(row=0, column=1, sticky='ew', padx=(5, 0))

        # --- FB Lite URL Controls ---
        ctk.CTkLabel(fb_frame, text="FACEBOOK POST URL", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=2, column=0, sticky='w', padx=15, pady=(15, 5))
        self.fb_url_entry = ctk.CTkEntry(fb_frame, placeholder_text="Enter Facebook URL...", height=40, corner_radius=8)
        self.fb_url_entry.grid(row=3, column=0, sticky='ew', padx=15, pady=0)
        self.fb_button = ctk.CTkButton(fb_frame, text="VISIT POST", command=self.open_fb_lite_deeplink,
                                       fg_color="#1877f2", hover_color="#1651b7", height=45,
                                       font=ctk.CTkFont(weight="bold"))
        self.fb_button.grid(row=4, column=0, sticky='ew', padx=15, pady=10)

        ctk.CTkLabel(fb_frame, text="LINK TO SHARE", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=5, column=0, sticky='w', pady=(15, 5), padx=15)
        self.fb_share_url_entry = ctk.CTkEntry(fb_frame, placeholder_text="Enter link to share...", height=40,
                                               corner_radius=8)
        self.fb_share_url_entry.grid(row=6, column=0, sticky='ew', padx=15, pady=0)
        self.share_button = ctk.CTkButton(fb_frame, text="SHARE POST", command=self.share_fb_lite_deeplink,
                                          fg_color="#42b72a", hover_color="#369720", height=45,
                                          font=ctk.CTkFont(weight="bold"))
        self.share_button.grid(row=7, column=0, sticky='ew', padx=15, pady=10)

        # --- Separator ---
        ctk.CTkFrame(fb_frame, height=1, fg_color=self.ACCENT_COLOR).grid(row=8, column=0,
                                                                          sticky='ew',
                                                                          padx=15, pady=15)

        # --- Text Command Section (Moved from 'Text Cmd' Tab) ---
        ctk.CTkLabel(fb_frame, text="TEXT COMMAND FROM FILE", font=ctk.CTkFont(size=14, weight="bold")).grid(row=9,
                                                                                                             column=0,
                                                                                                             sticky='w',
                                                                                                             pady=(
                                                                                                             0, 5),
                                                                                                             padx=15)
        self.file_path_entry = ctk.CTkEntry(fb_frame, placeholder_text="Path: Select a text file...", height=40,
                                            corner_radius=8)
        self.file_path_entry.grid(row=10, column=0, sticky='ew', padx=15)
        browse_button = ctk.CTkButton(fb_frame, text="BROWSE TXT", command=self.browse_file, corner_radius=8,
                                      fg_color="#3A3A3A", hover_color="#555555")
        browse_button.grid(row=11, column=0, sticky='ew', padx=15, pady=(10, 10))

        # --- Text Command Buttons Frame ---
        text_buttons_frame = ctk.CTkFrame(fb_frame, fg_color="transparent")
        text_buttons_frame.grid(row=12, column=0, sticky='ew', padx=15, pady=0)
        text_buttons_frame.columnconfigure(0, weight=1)
        text_buttons_frame.columnconfigure(1, weight=1)

        self.send_button = ctk.CTkButton(text_buttons_frame, text="SEND RANDOM TEXT ✉️",
                                         command=self.send_text_to_devices,
                                         fg_color=self.SUCCESS_COLOR, hover_color="#00A852", height=45,
                                         font=ctk.CTkFont(weight="bold"), text_color=self.BACKGROUND_COLOR)
        self.send_button.grid(row=0, column=0, sticky='ew', padx=(0, 5), pady=(5, 5))

        self.remove_emoji_button = ctk.CTkButton(text_buttons_frame, text="REMOVE EMOJIS 🚫",
                                                 command=self.remove_emojis_from_file,
                                                 fg_color=self.WARNING_COLOR, hover_color="#CC8400", height=45,
                                                 font=ctk.CTkFont(weight="bold"), text_color=self.BACKGROUND_COLOR)
        self.remove_emoji_button.grid(row=0, column=1, sticky='ew', padx=(5, 0), pady=(5, 5))

        # --- MODIFIED "Find, Click & Type" Button to "START AUTO-TYPE" ---
        self.find_click_type_button = ctk.CTkButton(fb_frame, text="START AUTO-TYPE ⌨️",
                                                    command=self.toggle_auto_type_loop,
                                                    fg_color="#3A3A3A", hover_color="#555555", height=45,
                                                    font=ctk.CTkFont(size=14, weight="bold"),
                                                    text_color=self.ACCENT_COLOR,
                                                    border_color=self.ACCENT_COLOR, border_width=1)
        self.find_click_type_button.grid(row=13, column=0, sticky='ew', padx=15, pady=(10, 15))

        # TikTok Tab
        tiktok_frame = self.tab_view.tab("TikTok")
        tiktok_frame.columnconfigure(0, weight=1)
        tiktok_frame.rowconfigure(4, weight=1)

        ctk.CTkLabel(tiktok_frame, text="TIKTOK URL", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0,
                                                                                                     sticky='w',
                                                                                                     pady=(15, 5),
                                                                                                     padx=15)
        self.tiktok_url_entry = ctk.CTkEntry(tiktok_frame, placeholder_text="Enter TikTok URL...", height=40,
                                             corner_radius=8)
        self.tiktok_url_entry.grid(row=1, column=0, sticky='ew', padx=15)
        self.tiktok_button = ctk.CTkButton(tiktok_frame, text="VISIT POST", command=self.open_tiktok_lite_deeplink,
                                           fg_color="#fe2c55", hover_color="#c82333", height=45,
                                           font=ctk.CTkFont(weight="bold"))
        self.tiktok_button.grid(row=2, column=0, pady=10, sticky='ew', padx=15)

        tiktok_launch_frame = ctk.CTkFrame(tiktok_frame, fg_color="transparent")
        tiktok_launch_frame.grid(row=3, column=0, sticky='ew', padx=15, pady=(20, 15))
        tiktok_launch_frame.columnconfigure(0, weight=1)
        tiktok_launch_frame.columnconfigure(1, weight=1)
        self.launch_tiktok_lite_button = ctk.CTkButton(tiktok_launch_frame, text="Launch TikTok Lite",
                                                       command=self.launch_tiktok_lite, corner_radius=8,
                                                       fg_color="#3A3A3A", hover_color="#555555")
        self.launch_tiktok_lite_button.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        self.force_stop_tiktok_lite_button = ctk.CTkButton(tiktok_launch_frame, text="Force Stop",
                                                           command=self.force_stop_tiktok_lite,
                                                           fg_color=self.DANGER_COLOR,
                                                           hover_color="#CC4028", corner_radius=8,
                                                           text_color=self.ACCENT_COLOR)
        self.force_stop_tiktok_lite_button.grid(row=0, column=1, sticky='ew', padx=(5, 0))

        # YouTube Tab
        youtube_frame = self.tab_view.tab("YouTube")
        youtube_frame.columnconfigure(0, weight=1)
        youtube_frame.rowconfigure(4, weight=1)

        ctk.CTkLabel(youtube_frame, text="YOUTUBE URL", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0,
                                                                                                       sticky='w',
                                                                                                       pady=(15, 5),
                                                                                                       padx=15)
        self.youtube_url_entry = ctk.CTkEntry(youtube_frame, placeholder_text="Enter YouTube URL...", height=40,
                                              corner_radius=8)
        self.youtube_url_entry.grid(row=1, column=0, sticky='ew', padx=15)
        self.youtube_button = ctk.CTkButton(youtube_frame, text="VISIT VIDEO", command=self.open_youtube_deeplink,
                                            fg_color="#ff0000", hover_color="#cc0000", height=45,
                                            font=ctk.CTkFont(weight="bold"))
        self.youtube_button.grid(row=2, column=0, pady=10, sticky='ew', padx=15)

        youtube_launch_frame = ctk.CTkFrame(youtube_frame, fg_color="transparent")
        youtube_launch_frame.grid(row=3, column=0, sticky='ew', padx=15, pady=(20, 15))
        youtube_launch_frame.columnconfigure(0, weight=1)
        youtube_launch_frame.columnconfigure(1, weight=1)
        self.launch_youtube_button = ctk.CTkButton(youtube_launch_frame, text="Launch Chrome",
                                                   command=self.launch_youtube, corner_radius=8,
                                                   fg_color="#3A3A3A", hover_color="#555555")
        self.launch_youtube_button.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        self.force_stop_youtube_button = ctk.CTkButton(youtube_launch_frame, text="Force Stop Chrome",
                                                       command=self.force_stop_youtube, fg_color=self.DANGER_COLOR,
                                                       hover_color="#CC4028", corner_radius=8,
                                                       text_color=self.ACCENT_COLOR)
        self.force_stop_youtube_button.grid(row=0, column=1, sticky='ew', padx=(5, 0))

        # Text Command Tab - REMOVED

        # Image Tab
        image_frame = self.tab_view.tab("Image")
        image_frame.columnconfigure(0, weight=1)
        image_frame.rowconfigure(2, weight=1)

        ctk.CTkLabel(image_frame, text="PHOTO FILE NAME", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky='w', pady=(15, 5), padx=15)
        self.image_file_name_entry = ctk.CTkEntry(image_frame,
                                                  placeholder_text="Enter image name in /sdcard/Download...", height=40,
                                                  corner_radius=8)
        self.image_file_name_entry.grid(row=1, column=0, sticky='ew', padx=15)
        self.share_image_button = ctk.CTkButton(image_frame, text="SHARE IMAGE (FB Lite)",
                                                command=self.share_image_to_fb_lite,
                                                fg_color="#42b72a", hover_color="#369720", height=45,
                                                font=ctk.CTkFont(weight="bold"))
        self.share_image_button.grid(row=2, column=0, sticky='ew', padx=15, pady=(10, 15))

        # FB API Tab (NEW)
        fb_api_frame = self.tab_view.tab("FB API")
        fb_api_frame.columnconfigure(0, weight=1)
        fb_api_frame.rowconfigure(10, weight=1)

        # -----------------------------------------------------
        # Section 1: Access Token File
        # -----------------------------------------------------
        ctk.CTkLabel(fb_api_frame, text="FACEBOOK ACCESS TOKEN FILE (email|TOKEN or TOKEN)",
                     font=ctk.CTkFont(size=14, weight="bold"), text_color=self.ACCENT_COLOR).grid(row=0, column=0,
                                                                                                  sticky='w', padx=15,
                                                                                                  pady=(15, 5))
        self.fb_api_token_entry = ctk.CTkEntry(fb_api_frame, placeholder_text="Path: Select tokens file (.txt)...",
                                               height=40, corner_radius=8)
        self.fb_api_token_entry.grid(row=1, column=0, sticky='ew', padx=15)

        browse_token_button = ctk.CTkButton(fb_api_frame, text="BROWSE TOKEN FILE 🔑", command=self.browse_token_file,
                                            corner_radius=8, fg_color="#3A3A3A", hover_color="#555555", height=45)
        browse_token_button.grid(row=2, column=0, sticky='ew', padx=15, pady=(10, 15))

        # -----------------------------------------------------
        # Section 2: Caption/Message File
        # -----------------------------------------------------
        ctk.CTkLabel(fb_api_frame, text="POST CAPTION/MESSAGE FILE (Random Line)",
                     font=ctk.CTkFont(size=14, weight="bold"), text_color=self.ACCENT_COLOR).grid(row=3, column=0,
                                                                                                  sticky='w', padx=15,
                                                                                                  pady=(15, 5))
        self.fb_api_message_file_entry = ctk.CTkEntry(fb_api_frame,
                                                      placeholder_text="Path: Select caption file (.txt)...",
                                                      height=40, corner_radius=8)
        self.fb_api_message_file_entry.grid(row=4, column=0, sticky='ew', padx=15, pady=(0, 5))

        browse_caption_button = ctk.CTkButton(fb_api_frame, text="BROWSE CAPTION FILE 💬",
                                              command=self.browse_caption_file,
                                              corner_radius=8, fg_color="#3A3A3A", hover_color="#555555", height=45)
        browse_caption_button.grid(row=5, column=0, sticky='ew', padx=15, pady=(10, 15))

        # -----------------------------------------------------
        # Section 3: Link and Target ID
        # -----------------------------------------------------
        ctk.CTkLabel(fb_api_frame, text="LINK AND TARGET CONFIG (Optional)",
                     font=ctk.CTkFont(size=14, weight="bold"), text_color=self.ACCENT_COLOR).grid(row=6, column=0,
                                                                                                  sticky='w', padx=15,
                                                                                                  pady=(10, 5))

        self.fb_api_link_entry = ctk.CTkEntry(fb_api_frame, placeholder_text="Enter link URL to share (Optional)...",
                                              height=40, corner_radius=8)
        self.fb_api_link_entry.grid(row=7, column=0, sticky='ew', padx=15, pady=(0, 5))

        self.fb_api_target_entry = ctk.CTkEntry(fb_api_frame, placeholder_text="Enter user ID or 'me' (Default: me)...",
                                                height=40, corner_radius=8)
        self.fb_api_target_entry.insert(0, 'me')
        self.fb_api_target_entry.grid(row=8, column=0, sticky='ew', padx=15, pady=(5, 15))

        # -----------------------------------------------------
        # Section 4: Post Button
        # -----------------------------------------------------
        self.fb_api_post_button = ctk.CTkButton(fb_api_frame, text="POST TO FACEBOOK API (Using All Tokens) 🚀",
                                                command=self.post_to_facebook_api,
                                                fg_color="#1877f2", hover_color="#1651b7", height=55,
                                                font=ctk.CTkFont(size=16, weight="bold"))
        self.fb_api_post_button.grid(row=9, column=0, sticky='ew', padx=15, pady=(10, 15))

        # --- NEW GET TOKEN TAB CONFIGURATION ---
        self._configure_get_token_tab(self.tab_view.tab("GET TOKEN"))

    # --- Existing Facebook API Methods ---

    def browse_token_file(self):
        """Opens a file dialog to select the text file containing the Facebook Access Token(s)."""
        file_path = filedialog.askopenfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if file_path:
            self.fb_api_token_entry.delete(0, tk.END)
            self.fb_api_token_entry.insert(0, file_path)
            self.status_label.configure(text=f"✅ TOKEN FILE SELECTED: {os.path.basename(file_path)}",
                                        text_color=self.SUCCESS_COLOR)

    def browse_caption_file(self):
        """Opens a file dialog to select the text file containing the messages/captions."""
        file_path = filedialog.askopenfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if file_path:
            self.fb_api_message_file_entry.delete(0, tk.END)
            self.fb_api_message_file_entry.insert(0, file_path)
            self.status_label.configure(text=f"✅ CAPTION FILE SELECTED: {os.path.basename(file_path)}",
                                        text_color=self.SUCCESS_COLOR)

    def post_to_facebook_api(self):
        """Executes the Facebook Graph API post in a separate thread."""
        token_file_path = self.fb_api_token_entry.get().strip()
        caption_file_path = self.fb_api_message_file_entry.get().strip()
        link_url = self.fb_api_link_entry.get().strip()
        target_id = self.fb_api_target_entry.get().strip() or 'me'

        if not token_file_path:
            self.status_label.configure(text="⚠️ Please select an Access Token file.", text_color="#ffc107")
            return

        if not caption_file_path:
            self.status_label.configure(text="⚠️ Please select a Caption/Message file.", text_color="#ffc107")
            return

        if not link_url and not caption_file_path:
            self.status_label.configure(text="⚠️ Enter a Link URL or select a Caption file.", text_color="#ffc107")
            return

        # Start the API call in a thread to keep the GUI responsive
        threading.Thread(target=self._threaded_post_api_call,
                         args=(token_file_path, caption_file_path, link_url, target_id),
                         daemon=True).start()

    def _threaded_post_api_call(self, token_file_path, caption_file_path, link_url, target_id):
        """
        The actual network call logic executed in a thread.
        Reads all tokens, reads all captions, loops through all tokens, and posts with a random caption.
        """
        self.after(0, lambda: self.status_label.configure(
            text=f"[CMD] Preparing to post to {target_id}'s feed using tokens and captions...",
            text_color=self.ACCENT_COLOR))

        # 1. Read and Parse Access Tokens
        valid_tokens = []
        try:
            with open(token_file_path, 'r', encoding='utf-8') as f:
                raw_lines = f.readlines()

            for line in raw_lines:
                line = line.strip()
                if not line:
                    continue

                # Check for 'email|TOKEN' format
                if '|' in line:
                    parts = line.split('|', 1)
                    token = parts[1].strip()
                else:
                    # Assume the whole line is the token
                    token = line

                if token:
                    valid_tokens.append(token)

        except FileNotFoundError:
            self.after(0, lambda: self.status_label.configure(
                text="❌ ERROR: Token file not found.", text_color=self.DANGER_COLOR))
            return
        except Exception as e:
            self.after(0, lambda: self.status_label.configure(
                text=f"❌ ERROR reading token file: {e}", text_color=self.DANGER_COLOR))
            return

        if not valid_tokens:
            self.after(0, lambda: self.status_label.configure(
                text="❌ ERROR: No valid tokens found in the file.", text_color=self.DANGER_COLOR))
            return

        # 2. Read and Parse Captions/Messages
        try:
            with open(caption_file_path, 'r', encoding='utf-8') as f:
                raw_lines = f.readlines()

            clean_captions = [line.strip() for line in raw_lines if line.strip()]

        except FileNotFoundError:
            self.after(0, lambda: self.status_label.configure(
                text="❌ ERROR: Caption file not found.", text_color=self.DANGER_COLOR))
            return
        except Exception as e:
            self.after(0, lambda: self.status_label.configure(
                text=f"❌ ERROR reading caption file: {e}", text_color=self.DANGER_COLOR))
            return

        if not clean_captions:
            self.after(0, lambda: self.status_label.configure(
                text="❌ ERROR: Caption file is empty.", text_color=self.DANGER_COLOR))
            return

        # 3. Post using all tokens with random captions
        API_VERSION = 'v19.0'
        url = f'https://graph.facebook.com/{API_VERSION}/{target_id}/feed'
        success_count = 0

        for i, access_token in enumerate(valid_tokens):
            if is_stop_requested.is_set():
                self.after(0, lambda: self.status_label.configure(
                    text="🛑 Operation terminated by user.", text_color="#ffc107"))
                break

            # Choose a random message for the current token
            random_message = random.choice(clean_captions)

            # Use only a short snippet of the token for display (first 10 chars)
            display_token_snippet = access_token[:10] + '...'
            self.after(0, lambda msg=random_message: self.status_label.configure(
                text=f"[{i + 1}/{len(valid_tokens)}] Posting (Token: {display_token_snippet}, Msg: '{msg[:20]}...')...",
                text_color=self.ACCENT_COLOR))

            payload = {
                'message': random_message,
                'link': link_url,
                'access_token': access_token
            }

            # Remove empty parameters to avoid API errors
            payload = {k: v for k, v in payload.items() if v}

            # 4. Execute API Post for the current token
            try:
                response = requests.post(url, data=payload, timeout=20)
                response_data = response.json()

                if response.status_code == 200 and 'id' in response_data:
                    post_id = response_data['id']
                    success_count += 1
                    # Update status in the main thread
                    self.after(0, lambda post_id=post_id: self.status_label.configure(
                        text=f"[{i + 1}/{len(valid_tokens)}] ✅ SUCCESS! Post ID: {post_id}",
                        text_color=self.SUCCESS_COLOR))
                else:
                    error_detail = response_data.get('error', {}).get('message', 'Unknown API Error')
                    error_code = response_data.get('error', {}).get('code', 'N/A')
                    # Update status in the main thread
                    self.after(0, lambda: self.status_label.configure(
                        text=f"[{i + 1}/{len(valid_tokens)}] ❌ FAIL (Code {error_code}): {error_detail[:50]}...",
                        text_color=self.DANGER_COLOR))

            except requests.exceptions.RequestException as e:
                # Update status in the main thread
                self.after(0, lambda: self.status_label.configure(
                    text=f"[{i + 1}/{len(valid_tokens)}] ❌ NETWORK ERROR: Failed to reach Facebook API.",
                    text_color=self.DANGER_COLOR))

            # Pause between posts to prevent rate-limiting (optional, but highly recommended)
            time.sleep(2)  # 2-second delay between posts

        final_message = f"✅ POSTING COMPLETE. Total successful posts: {success_count} / {len(valid_tokens)}"
        self.after(0, lambda: self.status_label.configure(text=final_message, text_color=self.SUCCESS_COLOR))

    # --- New ADB Utility Methods for Airplane Mode ---

    def _threaded_airplane_mode(self, mode):
        """Helper function to run airplane mode commands in a thread."""
        if not self.devices:
            self.after(0, lambda: self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107"))
            return

        state = '1' if mode == 'enable' else '0'
        name = 'ENABLE' if mode == 'enable' else 'DISABLE'

        self.after(0, lambda: self.status_label.configure(
            text=f"[CMD] Sending {name} AIRPLANE MODE command...", text_color=self.ACCENT_COLOR))

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
            text=f"✅ AIRPLANE MODE {name} command sent to all devices.", text_color=self.SUCCESS_COLOR))

    def enable_airplane_mode(self):
        """Enables Airplane Mode on all connected devices."""
        threading.Thread(target=self._threaded_airplane_mode, args=('enable',), daemon=True).start()

    def disable_airplane_mode(self):
        """Disables Airplane Mode on all connected devices."""
        threading.Thread(target=self._threaded_airplane_mode, args=('disable',), daemon=True).start()

    # --- Existing ADB Utility Methods ---

    def set_brightness(self, value):
        """Sets the screen brightness via ADB settings put command (0-255)."""
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        # Ensure value is an integer and within the valid range
        brightness_level = int(float(value))
        if not 0 <= brightness_level <= 255:
            brightness_level = max(0, min(255, brightness_level))

        # Update slider position (useful when clicking preset buttons)
        self.brightness_slider.set(brightness_level)

        self.status_label.configure(text=f"[CMD] Setting Brightness: {brightness_level} on all devices...",
                                    text_color=self.ACCENT_COLOR)

        # Set screen brightness (0-255)
        brightness_cmd = ['shell', 'settings', 'put', 'system', 'screen_brightness', str(brightness_level)]

        # Set screen brightness mode to manual (0) to allow settings to take effect
        mode_cmd = ['shell', 'settings', 'put', 'system', 'screen_brightness_mode', '0']

        for serial in self.devices:
            # Need to run both mode and brightness commands
            self.executor.submit(run_adb_command, mode_cmd, serial)
            self.executor.submit(run_adb_command, brightness_cmd, serial)

        self.status_label.configure(text=f"✅ BRIGHTNESS SET to {brightness_level}.",
                                    text_color=self.SUCCESS_COLOR)

    def toggle_mute(self):
        """Toggles the volume mute state."""
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        keycode = '23'  # KEYCODE_MUTE (or KEYCODE_VOLUME_MUTE)

        if self.is_muted:
            # If currently muted, un-mute (send key event)
            self.mute_button.configure(text="MUTE 🔇", fg_color="#3A3A3A", hover_color="#555555")
            self.status_label.configure(text="[CMD] Unmuting volume...", text_color=self.ACCENT_COLOR)
            self.is_muted = False
        else:
            # If currently unmuted, mute (send key event)
            self.mute_button.configure(text="UNMUTE 🔊", fg_color=self.DANGER_COLOR, hover_color="#CC4028",
                                       text_color=self.ACCENT_COLOR)
            self.status_label.configure(text="[CMD] Muting volume...", text_color=self.ACCENT_COLOR)
            self.is_muted = True

        command = ['shell', 'input', 'keyevent', keycode]
        for serial in self.devices:
            self.executor.submit(run_adb_command, command, serial)

        self.status_label.configure(text=f"✅ Volume toggle submitted.", text_color=self.SUCCESS_COLOR)

    def reboot_devices(self):
        """Reboots all connected devices."""
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        if not messagebox.askyesno("Confirm Action", "Are you sure you want to REBOOT all connected devices?"):
            return

        self.status_label.configure(text="[CMD] Rebooting all connected devices...", text_color=self.WARNING_COLOR)
        command = ['reboot']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)

        # Redetect devices after a short delay, as rebooting devices disappear and reappear
        self.after(2000, self.detect_devices)

    def shutdown_devices(self):
        """Sends a power off command to all connected devices."""
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        if not messagebox.askyesno("Confirm Action", "Are you sure you want to POWER OFF all connected devices?"):
            return

        self.status_label.configure(text="[CMD] Shutting down all connected devices...", text_color=self.DANGER_COLOR)
        command = ['shell', 'reboot', '-p']  # ADB command for poweroff
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)

        # Redetect devices to clear the list
        self.after(2000, self.detect_devices)

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
                                        text_color=self.SUCCESS_COLOR)

    def install_apk_to_devices(self):
        """Installs the selected APK on all connected devices."""
        if not self.apk_path or not os.path.exists(self.apk_path):
            self.status_label.configure(text="⚠️ Please select a valid APK file first.", text_color="#ffc107")
            return

        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"[CMD] Installing {os.path.basename(self.apk_path)} on all devices...",
                                    text_color=self.ACCENT_COLOR)

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
            self.status_label.configure(text="✅ APK INSTALL SUCCESSFUL.", text_color=self.SUCCESS_COLOR)
        else:
            error_count = sum(1 for _, success, _ in results if not success)
            self.status_label.configure(text=f"❌ INSTALLATION FAILED on {error_count} device(s).",
                                        text_color=self.DANGER_COLOR)

    def run_custom_shell_command(self):
        """Runs a user-defined ADB shell command on all connected devices."""
        custom_cmd_str = self.custom_cmd_entry.get().strip()
        if not custom_cmd_str:
            self.status_label.configure(text="⚠️ Please enter a shell command to run.", text_color="#ffc107")
            return

        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        # Prepare the command: split the string into a list of arguments
        try:
            custom_args = custom_cmd_str.split()
            command = ['shell'] + custom_args

        except Exception:
            self.status_label.configure(text="❌ Invalid command format.", text_color=self.DANGER_COLOR)
            return

        self.status_label.configure(text=f"[CMD] Running custom command: '{custom_cmd_str}'",
                                    text_color=self.ACCENT_COLOR)

        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)

        self.status_label.configure(text=f"✅ Custom command submitted to all devices.", text_color=self.SUCCESS_COLOR)

    # --- Existing Methods (Updated for Styling) ---

    def update_app(self):
        # Adjusted error handling in _update_in_thread for clarity
        def _update_in_thread():
            try:
                self.status_label.configure(text="[SYS] Downloading latest version...", text_color=self.ACCENT_COLOR)

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
                    text_color=self.DANGER_COLOR))
                self.after(0, lambda: messagebox.showerror(
                    "Update Download Failed",
                    f"Failed to download update (HTTP Error {status_code}). Check if the update file exists at the URL."))
            except requests.exceptions.ConnectionError:
                self.after(0, lambda: self.status_label.configure(
                    text="❌ ERROR: Update download failed. Connection Refused.",
                    text_color=self.DANGER_COLOR))
                self.after(0, lambda: messagebox.showerror(
                    "Update Download Failed",
                    "Failed to download update. Cannot connect to the server. Check your internet connection or firewall."))
            except requests.exceptions.Timeout:
                self.after(0, lambda: self.status_label.configure(
                    text="❌ ERROR: Update download timed out.",
                    text_color=self.DANGER_COLOR))
                self.after(0, lambda: messagebox.showerror(
                    "Update Download Failed",
                    "Update download timed out. Your network might be slow or unstable."))
            except requests.exceptions.RequestException as e:
                self.after(0, lambda: self.status_label.configure(
                    text=f"❌ ERROR: Update download failed. Details: {e.__class__.__name__}",
                    text_color=self.DANGER_COLOR))
                self.after(0, lambda: messagebox.showerror(
                    "Update Download Failed",
                    f"An error occurred during download: {e.__class__.__name__}. Check logs for details."))
            except Exception as e:
                self.after(0, lambda: self.status_label.configure(
                    text=f"❌ ERROR: An unexpected update error occurred: {e}",
                    text_color=self.DANGER_COLOR))
                self.after(0, lambda: messagebox.showerror(
                    "Update Error",
                    f"An unexpected file operation error occurred.\nError: {e}"))

        update_thread = threading.Thread(target=_update_in_thread, daemon=True)
        update_thread.start()

    def browse_file(self):
        # ... (Implementation remains the same, adjusted status text colors)
        file_path = filedialog.askopenfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if file_path:
            self.file_path_entry.delete(0, tk.END)
            self.file_path_entry.insert(0, file_path)
            self.status_label.configure(text=f"✅ FILE SELECTED: {os.path.basename(file_path)}",
                                        text_color=self.SUCCESS_COLOR)

            # --- MODIFICATION ---
            # Automatically stop any running loop if a new file is selected
            if self.is_auto_typing.is_set():
                self.toggle_auto_type_loop()

    def _threaded_send_text(self):
        # ... (Implementation remains the same, adjusted status text colors)
        file_path = self.file_path_entry.get()
        if not file_path:
            self.status_label.configure(text="⚠️ Please select a text file.", text_color="#ffc107")
            return

        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            clean_lines = [line.strip() for line in lines if line.strip()]

            if not clean_lines:
                self.status_label.configure(text="⚠️ The selected file is empty or has no content.",
                                            text_color="#ffc107")
                return

            self.status_label.configure(
                text=f"[CMD] Sending random text from file '{os.path.basename(file_path)}' to all devices...",
                text_color=self.ACCENT_COLOR)

            for device_serial in self.devices:
                random_text = random.choice(clean_lines)
                self.executor.submit(run_text_command, random_text, device_serial)

            self.status_label.configure(text=f"✅ Text commands submitted.", text_color=self.SUCCESS_COLOR)


        except FileNotFoundError:
            self.status_label.configure(text="❌ ERROR: File not found.", text_color=self.DANGER_COLOR)
        except Exception as e:
            self.status_label.configure(text=f"❌ ERROR: An error occurred: {e}", text_color=self.DANGER_COLOR)

    def send_text_to_devices(self):
        send_thread = threading.Thread(target=self._threaded_send_text, daemon=True)
        send_thread.start()

    # --- NEW METHOD: Toggles the auto-type loop ---
    def toggle_auto_type_loop(self):
        """
        Toggles the 'while true' loop for finding, clicking, and typing.
        """
        if self.is_auto_typing.is_set():
            # --- STOP THE LOOP ---
            self.is_auto_typing.clear()
            self.find_click_type_button.configure(text="START AUTO-TYPE ⌨️",
                                                  fg_color="#3A3A3A",
                                                  hover_color="#555555")
            self.status_label.configure(text="[CMD] Stopping auto-type loop...", text_color=self.WARNING_COLOR)
            return

        # --- START THE LOOP ---
        file_path = self.file_path_entry.get()
        if not file_path:
            self.status_label.configure(text="⚠️ Please select a text file first.", text_color="#ffc107")
            return

        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            clean_lines = [line.strip() for line in lines if line.strip()]
            if not clean_lines:
                self.status_label.configure(text="⚠️ Text file is empty.", text_color="#ffc107")
                return
        except FileNotFoundError:
            self.status_label.configure(text="❌ ERROR: Text file not found.", text_color=self.DANGER_COLOR)
            return
        except Exception as e:
            self.status_label.configure(text=f"❌ ERROR: Reading file: {e}", text_color=self.DANGER_COLOR)
            return

        # Set the flag
        self.is_auto_typing.set()

        # Update button to be a STOP button
        self.find_click_type_button.configure(text="STOP AUTO-TYPE 🛑",
                                              fg_color=self.DANGER_COLOR,
                                              hover_color="#CC4028")

        self.status_label.configure(text="[CMD] Auto-type loop STARTED.", text_color=self.SUCCESS_COLOR)

        # Start the loop thread
        threading.Thread(target=self._threaded_find_click_type_LOOP, args=(clean_lines,), daemon=True).start()

    def _threaded_find_click_type_LOOP(self, clean_lines):
        """
        The main 'while true' loop for auto-typing.
        Ang loop ay magsa-success at magbe-break pagkatapos ng ISANG cycle.
        """
        try:
            # Loop will run AT LEAST once since self.is_auto_typing is set
            while self.is_auto_typing.is_set() and not is_stop_requested.is_set():
                print("\n🔄 Starting new auto-type cycle...")

                if not self.devices:
                    self.after(0, lambda: self.status_label.configure(text="⚠️ No devices, stopping loop.",
                                                                      text_color="#ffc107"))
                    break

                # Run the task on all devices concurrently for this one cycle
                futures = []
                for serial in self.devices:
                    if not self.is_auto_typing.is_set() or is_stop_requested.is_set():
                        break

                    random_text = random.choice(clean_lines)
                    futures.append(self.executor.submit(self._run_find_click_type_on_device, serial, random_text))

                # Wait for this cycle to finish
                if futures:
                    concurrent.futures.wait(futures)

                    # OPTIONAL: Kung gusto mong i-check ang results para sa errors, gawin dito:
                    # for future in futures:
                    #     if future.exception() is not None:
                    #         print(f"    ❌ Error on device: {future.exception()}")

                # Check for stop signals again
                if not self.is_auto_typing.is_set() or is_stop_requested.is_set():
                    break

                # I-update ang status at mag-break
                self.after(0, lambda: self.status_label.configure(
                    text="[SUCCESS] Auto-type cycle complete. Stopping loop.", text_color=self.ACCENT_COLOR))

                # ITO ANG NAGPAPATIGIL NG LOOP MATAPOS ANG ISANG SUCCESSFUL RUN
                break

                # Old sleep code removed, as we want to break immediately after success

        except Exception as e:
            print(f"Error in auto-type loop: {e}")
            # Tanggalin ang 'pass' at gawing visible ang error para sa debugging
        finally:
            # Loop ended (either by toggle, global stop, or successful completion/break)
            # Reset the button in the main thread
            self.after(0, self.reset_auto_type_button)

    def _run_find_click_type_on_device(self, serial, text_to_send):
        """
        The core logic that runs on each device to find, click, and type.
        Returns (bool success, str message)
        """
        local_xml_file = f"ui_dump_{serial}_{uuid.uuid4()}.xml"

        try:
            # Step 1: Dump UI
            dump_cmd = ['shell', 'uiautomator', 'dump', '/data/local/tmp/ui.xml']
            success, out = run_adb_command(dump_cmd, serial)
            if not success:
                # print(f"[{serial}] Failed to dump UI.")
                return False, "Failed to dump UI"

            # Step 2: Pull XML
            pull_cmd = ['pull', '/data/local/tmp/ui.xml', local_xml_file]
            success, out = run_adb_command(pull_cmd, serial)
            if not success:
                # print(f"[{serial}] Failed to pull UI XML.")
                return False, "Failed to pull UI XML"

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
                return False, "No EditText found"

            # Step 5: Get Bounds
            bounds_str = edit_text_node.get('bounds')  # e.g., "[100,200][300,400]"
            if not bounds_str:
                # print(f"[{serial}] EditText found but has no bounds.")
                return False, "EditText has no bounds"

            coords = re.findall(r'\d+', bounds_str)
            if len(coords) < 4:
                # print(f"[{serial}] Invalid bounds string.")
                return False, "Invalid bounds string"

            x1, y1, x2, y2 = map(int, coords[:4])

            # Step 6: Calculate Center
            tap_x = (x1 + x2) // 2
            tap_y = (y1 + y2) // 2

            # Step 7: Click
            tap_cmd = ['shell', 'input', 'tap', str(tap_x), str(tap_y)]
            success, out = run_adb_command(tap_cmd, serial)
            if not success:
                # print(f"[{serial}] Failed to tap.")
                return False, "Failed to tap"

            # Short delay after tapping before typing
            time.sleep(0.5)

            # Step 8: Type
            run_text_command(text_to_send, serial)
            # print(f"[{serial}] Click and type successful.")
            return True, "Success"

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

    def reset_auto_type_button(self):
        """Resets the auto-type button to its 'START' state."""
        self.is_auto_typing.clear()

        # Check if button exists before configuring (in case window is closing)
        if hasattr(self, 'find_click_type_button') and self.find_click_type_button.winfo_exists():
            self.find_click_type_button.configure(text="START AUTO-TYPE ⌨️",
                                                  fg_color="#3A3A3A",
                                                  hover_color="#555555")

        if hasattr(self, 'status_label') and self.status_label.winfo_exists():
            # Only update status if it's not a global stop
            if not is_stop_requested.is_set():
                self.status_label.configure(text="[CMD] Auto-type loop Done.", text_color=self.ACCENT_COLOR)

    # --- End of new methods ---

    def remove_emojis_from_file(self):
        # ... (Implementation remains the same, adjusted status text colors)
        file_path = self.file_path_entry.get()
        if not file_path:
            self.status_label.configure(text="⚠️ Please select a text file first.", text_color="#ffc107")
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

            self.status_label.configure(text="✅ EMOJIS REMOVED from file.",
                                        text_color=self.SUCCESS_COLOR)

        except FileNotFoundError:
            self.status_label.configure(text="❌ ERROR: File not found.", text_color=self.DANGER_COLOR)
        except Exception as e:
            self.status_label.configure(text=f"❌ ERROR: An error occurred: {e}", text_color=self.DANGER_COLOR)

    def detect_devices(self):
        # ... (Implementation remains the same, adjusted status text colors/labels)
        self.stop_capture()

        for widget in self.device_view_panel.winfo_children():
            if widget != self.stop_all_button:
                widget.destroy()

        self.device_frames = {}
        self.device_canvases = {}
        self.device_images = {}
        self.press_start_coords = {}
        self.press_time = {}
        self.selected_device_serial = None
        self.device_listbox.delete(0, tk.END)
        self.devices = []
        self.status_label.configure(text="[SYS] Detecting devices...", text_color=self.ACCENT_COLOR)

        try:
            result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, check=True, timeout=10)
            devices_output = result.stdout.strip().split('\n')[1:]
            self.devices = [line.split('\t')[0] for line in devices_output if line.strip() and 'device' in line]
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            messagebox.showerror("Error", "ADB is not installed, not in your system PATH, or timed out.")
            self.status_label.configure(text="❌ ERROR: ADB not found or timed out.", text_color=self.DANGER_COLOR)
            self.device_count_label.configure(text="DEVICES: 0")
            return

        self.device_count_label.configure(text=f"DEVICES: {len(self.devices)}")

        if not self.devices:
            no_devices_label = ctk.CTkLabel(self.device_view_panel,
                                            text="NO DEVICES FOUND.\nEnsure USB debugging is enabled.",
                                            font=ctk.CTkFont(size=18, weight="bold"), text_color="#A9A9A9")
            no_devices_label.pack(expand=True)
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return
        else:
            self.status_label.configure(text=f"✅ {len(self.devices)} devices connected.", text_color=self.SUCCESS_COLOR)

        for serial in self.devices:
            self.device_listbox.insert(tk.END, serial)

        if self.devices:
            self.device_listbox.selection_set(0)
            self.on_device_select()

    def on_device_select(self, event=None):
        # ... (Existing implementation is fine)
        selected_index = self.device_listbox.curselection()
        if not selected_index:
            return

        new_serial = self.device_listbox.get(selected_index[0])
        self.stop_capture()
        self.selected_device_serial = new_serial

        for widget in self.device_view_panel.winfo_children():
            if widget != self.stop_all_button:
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
        # ... (Implementation remains the same, adjusted styling/labels)
        device_frame = ctk.CTkFrame(self.device_view_panel, fg_color=self.FRAME_COLOR, corner_radius=15)
        device_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        self.device_frames[serial] = device_frame

        title = ctk.CTkLabel(device_frame, text=f"LIVE CONTROL: {serial}", font=ctk.CTkFont(size=18, weight="bold"),
                             text_color=self.ACCENT_COLOR)
        title.pack(pady=(15, 10))

        # This Frame will contain the canvas and handle its aspect ratio
        canvas_container = ctk.CTkFrame(device_frame, fg_color=self.BACKGROUND_COLOR, corner_radius=10)
        canvas_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 5))
        canvas_container.bind("<Configure>", self.on_canvas_container_resize)

        canvas = tk.Canvas(canvas_container, bg=self.BACKGROUND_COLOR, highlightthickness=0)
        canvas.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self.device_canvases[serial] = canvas

        canvas.bind("<ButtonPress-1>", lambda event: self.start_press(event, serial))
        canvas.bind("<ButtonRelease-1>", lambda event: self.handle_release(event, serial))

        # Action Buttons Frame
        button_frame = ctk.CTkFrame(device_frame, fg_color="transparent")
        button_frame.pack(pady=(10, 15))

        # Adjusted button styling for professional look
        button_style = {'corner_radius': 8, 'width': 80, 'fg_color': "#3A3A3A", 'hover_color': "#555555",
                        'text_color': self.TEXT_COLOR}

        # Buttons control the Android device:

        # MINIMIZE / HOME (KEYCODE 3)
        home_button = ctk.CTkButton(button_frame, text="HOME 🏠", command=lambda: self.send_adb_keyevent(3),
                                    **button_style)
        home_button.pack(side=tk.LEFT, padx=5)

        # RESTORE DOWN / BACK (KEYCODE 4)
        back_button = ctk.CTkButton(button_frame, text="BACK ↩️", command=lambda: self.send_adb_keyevent(4),
                                    **button_style)
        back_button.pack(side=tk.LEFT, padx=5)

        # RECENTS (KEYCODE 187)
        recents_button = ctk.CTkButton(button_frame, text="RECENTS", command=lambda: self.send_adb_keyevent(187),
                                       **button_style)
        recents_button.pack(side=tk.LEFT, padx=5)

        # CLOSE / POWER (KEYCODE 26) - Simulates pressing the power button to turn off the screen
        close_button = ctk.CTkButton(button_frame, text="SCREEN OFF 💡", command=lambda: self.send_adb_keyevent(26),
                                     corner_radius=8, width=120, fg_color=self.DANGER_COLOR, hover_color="#CC4028",
                                     text_color=self.ACCENT_COLOR)
        close_button.pack(side=tk.LEFT, padx=5)

        # Swipes are common actions, keep them here
        scroll_down_button = ctk.CTkButton(button_frame, text="SCROLL DOWN",
                                           command=lambda: self.send_adb_swipe(serial, 'up'), **button_style)
        scroll_down_button.pack(side=tk.LEFT, padx=5)

        scroll_up_button = ctk.CTkButton(button_frame, text="SCROLL UP",
                                         command=lambda: self.send_adb_swipe(serial, 'down'), **button_style)
        scroll_up_button.pack(side=tk.LEFT, padx=5)

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
            self.status_label.configure(text=f"⚠️ Tap ignored (outside screen area).", text_color="#ffc107")
            return

        command = ['shell', 'input', 'tap', str(scaled_x), str(scaled_y)]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text=f"✅ TAP command sent.", text_color=self.SUCCESS_COLOR)

    def send_adb_long_press(self, event, serial):
        scaled_x, scaled_y = self._get_scaled_coords(event.x, event.y, serial)
        if scaled_x is None:
            self.status_label.configure(text=f"⚠️ Long press ignored (outside screen area).", text_color="#ffc107")
            return

        # Long press is implemented as a swipe from (x, y) to (x, y) over 1000ms
        command = ['shell', 'input', 'swipe', str(scaled_x), str(scaled_y), str(scaled_x), str(scaled_y), '1000']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text=f"✅ LONG PRESS command sent.", text_color=self.SUCCESS_COLOR)

    def send_adb_swipe_command(self, start_x, start_y, end_x, end_y, serial):
        scaled_start_x, scaled_start_y = self._get_scaled_coords(start_x, start_y, serial)
        scaled_end_x, scaled_end_y = self._get_scaled_coords(end_x, end_y, serial)

        if scaled_start_x is None or scaled_end_x is None:
            self.status_label.configure(text=f"⚠️ Swipe ignored (outside screen area).", text_color="#ffc107")
            return

        # Swipe duration set to 300ms
        command = ['shell', 'input', 'swipe',
                   str(scaled_start_x), str(scaled_start_y),
                   str(scaled_end_x), str(scaled_end_y), '300']

        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text=f"✅ SWIPE command sent.", text_color=self.SUCCESS_COLOR)

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
                                        text_color=self.SUCCESS_COLOR)
        except Exception as e:
            self.status_label.configure(text=f"❌ ERROR: Failed to send scroll command: {e}",
                                        text_color=self.DANGER_COLOR)

    def send_adb_keyevent(self, keycode):
        command = ['shell', 'input', 'keyevent', str(keycode)]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)

        key_name = {3: "HOME", 4: "BACK", 187: "RECENTS", 24: "VOL UP", 25: "VOL DOWN", 26: "POWER/SCREEN OFF"}.get(
            keycode, "KEY EVENT")
        self.status_label.configure(text=f"✅ {key_name} command sent.", text_color=self.SUCCESS_COLOR)

    def open_fb_lite_deeplink(self):
        # ... (Implementation remains the same, adjusted status text colors)
        post_url = self.fb_url_entry.get()
        if not post_url or not self.devices:
            self.status_label.configure(text="⚠️ Check URL and devices.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"[CMD] Opening FB post URL...", text_color=self.ACCENT_COLOR)

        command = [
            'shell', 'am', 'start',
            '-a', 'android.intent.action.VIEW',
            '-d', f'"{post_url}"',
            'com.facebook.lite'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Visited FB post on all devices.", text_color=self.SUCCESS_COLOR)

    def share_fb_lite_deeplink(self):
        # ... (Implementation remains the same, adjusted status text colors)
        share_url = self.fb_share_url_entry.get()
        if not share_url or not self.devices:
            self.status_label.configure(text="⚠️ Check share link and devices.", text_color="#ffc107")
            return

        self.status_label.configure(text="[CMD] Sending sharing URL...", text_color=self.ACCENT_COLOR)

        command = ['shell', 'am', 'start', '-a', 'android.intent.action.SEND', '-t', 'text/plain', '--es',
                   'android.intent.extra.TEXT', f'"{share_url}"', 'com.facebook.lite']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Shared post on all devices.", text_color=self.SUCCESS_COLOR)

    def launch_fb_lite(self):
        # ... (Implementation remains the same, adjusted status text colors)
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"[CMD] Launching Facebook Lite...", text_color=self.ACCENT_COLOR)

        command = ['shell', 'am', 'start', '-n', 'com.facebook.lite/com.facebook.lite.MainActivity']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Launched Facebook Lite on all devices.", text_color=self.SUCCESS_COLOR)

    def force_stop_fb_lite(self):
        # ... (Implementation remains the same, adjusted status text colors)
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"[CMD] Force stopping Facebook Lite...", text_color=self.DANGER_COLOR)

        command = ['shell', 'am', 'force-stop', 'com.facebook.lite']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Force stopped Facebook Lite on all devices.", text_color=self.SUCCESS_COLOR)

    def open_tiktok_lite_deeplink(self):
        # ... (Implementation remains the same, adjusted status text colors)
        post_url = self.tiktok_url_entry.get()
        if not post_url or not self.devices:
            self.status_label.configure(text="⚠️ Check URL and devices.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"[CMD] Opening TikTok URL...", text_color=self.ACCENT_COLOR)

        command = [
            'shell', 'am', 'start',
            '-a', 'android.intent.action.VIEW',
            '-d', f'"{post_url}"',
            'com.zhiliaoapp.musically.go'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Visited TikTok post on all devices.", text_color=self.SUCCESS_COLOR)

    def launch_tiktok_lite(self):
        # ... (Implementation remains the same, adjusted status text colors)
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"[CMD] Launching TikTok Lite...", text_color=self.ACCENT_COLOR)

        command = ['shell', 'am', 'start', '-n',
                   'com.zhiliaoapp.musically.go/com.ss.android.ugc.aweme.main.homepage.MainActivity']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Launched TikTok Lite on all devices.", text_color=self.SUCCESS_COLOR)

    def force_stop_tiktok_lite(self):
        # ... (Implementation remains the same, adjusted status text colors)
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"[CMD] Force stopping TikTok Lite...", text_color=self.DANGER_COLOR)

        command = ['shell', 'am', 'force-stop', 'com.zhiliaoapp.musically.go']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Force stopped TikTok Lite on all devices.", text_color=self.SUCCESS_COLOR)

    def open_youtube_deeplink(self):
        # ... (Implementation remains the same, adjusted status text colors)
        video_url = self.youtube_url_entry.get()
        if not video_url or not self.devices:
            self.status_label.configure(text="⚠️ Check URL and devices.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"[CMD] Opening YouTube video in Chrome...", text_color=self.ACCENT_COLOR)

        # Using Chrome intent for YouTube video viewing
        command = [
            'shell', 'am', 'start',
            '-a', 'android.intent.action.VIEW',
            '-d', f'"{video_url}"',
            'com.android.chrome/com.google.android.apps.chrome.Main'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Visited video on all devices.", text_color=self.SUCCESS_COLOR)

    def launch_youtube(self):
        # ... (Implementation remains the same, adjusted status text colors)
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"[CMD] Launching YouTube (via Chrome)...", text_color=self.ACCENT_COLOR)

        command = [
            'shell', 'am', 'start',
            '-a', 'android.intent.action.VIEW',
            '-d', 'https://m.youtube.com/',
            'com.android.chrome/com.google.android.apps.chrome.Main'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Launched YouTube on all devices.", text_color=self.SUCCESS_COLOR)

    def force_stop_youtube(self):
        # ... (Implementation remains the same, adjusted status text colors)
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"[CMD] Force stopping Chrome...", text_color=self.DANGER_COLOR)

        command = ['shell', 'am', 'force-stop', 'com.android.chrome']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Force stopped Chrome on all devices.", text_color=self.SUCCESS_COLOR)

    def share_image_to_fb_lite(self):
        # ... (Implementation remains the same, adjusted status text colors)
        file_name = self.image_file_name_entry.get()
        if not file_name or not self.devices:
            self.status_label.configure(text="⚠️ Check image filename and devices.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"[CMD] Sending sharing intent for '{file_name}'...",
                                    text_color=self.ACCENT_COLOR)

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
        self.status_label.configure(text="✅ Image sharing command sent to all devices.", text_color=self.SUCCESS_COLOR)

    def stop_all_commands(self):
        # ... (Implementation remains the same, adjusted status text colors and max workers)
        self.status_label.configure(text="⚠️ TERMINATING ALL ACTIVE COMMANDS...", text_color="#ffc107")
        is_stop_requested.set()

        # --- NEW: Also clear the auto-type flag ---
        self.is_auto_typing.clear()

        # Wait for all current tasks to finish (or be terminated)
        self.executor.shutdown(wait=True)

        # Reset the executor and the flag for new commands
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count() * 4)
        is_stop_requested.clear()

        self.status_label.configure(text="✅ ALL OPERATIONS TERMINATED. Ready.", text_color=self.SUCCESS_COLOR)

        # Also reset the button state just in case
        self.reset_auto_type_button()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    app = AdbControllerApp()
    app.mainloop()

