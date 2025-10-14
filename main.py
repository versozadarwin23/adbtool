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
from pathlib import Path
import re
import sys
import shutil
import tempfile

# --- App Version and Update URL ---
__version__ = "1.0.8"
UPDATE_URL = "https://raw.githubusercontent.com/versozadarwin23/adbtool/refs/heads/main/main.py"
VERSION_CHECK_URL = "https://raw.githubusercontent.com/versozadarwin23/adbtool/refs/heads/main/version.txt"

# --- Global Flag for Stopping Commands ---
is_stop_requested = threading.Event()


def run_adb_command(command, serial):
    """
    Executes a single ADB command for a specific device with a timeout, checking for a stop signal.
    """
    if is_stop_requested.is_set():
        print(f"🛑 Stop signal received. Aborting command on device {serial}.")
        return

    try:
        process = subprocess.Popen(['adb', '-s', serial] + command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Wait for the command to finish or for a stop signal
        while process.poll() is None:
            if is_stop_requested.is_set():
                process.terminate()  # Use terminate to kill the process
                print(f"🛑 Terminated ADB command on device {serial}.")
                return
            time.sleep(0.1)  # Small delay to reduce CPU usage

        stdout, stderr = process.communicate(timeout=10)
        if process.returncode != 0:
            print(f"❌ Error executing command on device {serial}: {stderr.decode()}")
        else:
            print(f"✅ Command executed on device {serial}: {' '.join(command)}")

    except subprocess.CalledProcessError as e:
        print(f"❌ Error executing command on device {serial}: {e.stderr.decode()}")
    except FileNotFoundError:
        print(f"❌ ADB not found. Please install it and add to PATH.")
    except subprocess.TimeoutExpired:
        print(f"❌ Command timed out on device {serial}")
    except Exception as e:
        print(f"❌ General error on device {serial}: {e}")


def run_text_command(text_to_send, serial):
    """
    Sends a specific text string as individual ADB text commands with a delay.
    """
    if is_stop_requested.is_set():
        print(f"🛑 Stop signal received. Aborting text command on device {serial}.")
        return

    if not text_to_send:
        print(f"Text is empty. Cannot send command to {serial}.")
        return

    for char in text_to_send:
        if is_stop_requested.is_set():
            print(f"🛑 Stop signal received. Aborting text command on device {serial}.")
            return

        try:
            encoded_char = char.replace(' ', '%s')
            command = ['shell', 'input', 'text', encoded_char]
            run_adb_command(command, serial)
        except Exception as e:
            print(f"An error occurred on device {serial}: {e}")


def create_and_run_updater_script(new_file_path, old_file_path):
    try:
        shutil.move(str(new_file_path), str(old_file_path))

        # I-restart ang app
        if sys.platform.startswith('win'):
            os.startfile(str(old_file_path))
        else:
            subprocess.Popen(['python3', str(old_file_path)])

        os._exit(0)  # Isara ang kasalukuyang proseso
    except Exception as e:
        messagebox.showerror("Update Error", f"Failed to replace file: {e}")



# --- AdbControllerApp Class ---
class AdbControllerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Devices Controller By Dars V3")
        self.attributes('-fullscreen', True)
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

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
        self.file_path_entry = None
        self.image_file_name_entry = None

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count() * 2)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- Control Panel Setup ---
        self.control_panel = ctk.CTkScrollableFrame(self, width=400, corner_radius=15, fg_color="#242424")
        self.control_panel.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.control_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.control_panel, text="Dars V3 Controller", font=ctk.CTkFont(size=30, weight="bold"),
                     text_color="#18a2ff").grid(
            row=0, column=0, pady=(20, 10), sticky='ew', padx=25)

        ctk.CTkFrame(self.control_panel, height=2, fg_color="#4a4a4a").grid(row=1, column=0, sticky='ew', padx=25,
                                                                            pady=15)

        device_section_frame = ctk.CTkFrame(self.control_panel, fg_color="transparent")
        device_section_frame.grid(row=2, column=0, sticky="ew", padx=25, pady=5)
        device_section_frame.grid_columnconfigure(0, weight=1)
        device_section_frame.grid_columnconfigure(1, weight=1)

        self.device_count_label = ctk.CTkLabel(device_section_frame, text="Connected Devices: 0",
                                               font=ctk.CTkFont(size=14, weight="bold"))
        self.device_count_label.grid(row=0, column=0, sticky='w')

        self.detect_button = ctk.CTkButton(device_section_frame, text="Refresh", command=self.detect_devices,
                                           width=100, corner_radius=8, fg_color="#3a3a3a", hover_color="#505050")
        self.detect_button.grid(row=0, column=1, sticky='e')

        self.update_button = ctk.CTkButton(device_section_frame, text="Update", command=self.update_app,
                                           fg_color="#007bff", hover_color="#0056b3", corner_radius=8)
        self.update_button.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(10, 5))

        self.device_listbox = tk.Listbox(self.control_panel, height=6, font=("Segoe UI", 12),
                                         bg="#2a2a2a", fg="#e0e0e0", selectbackground="#1f6aa5",
                                         selectforeground="white", borderwidth=0, highlightthickness=0, relief='flat')
        self.device_listbox.grid(row=3, column=0, sticky='ew', padx=25, pady=(5, 20))
        self.device_listbox.bind('<<ListboxSelect>>', self.on_device_select)

        self.tab_view = ctk.CTkTabview(self.control_panel, segmented_button_selected_color="#1f6aa5",
                                       segmented_button_selected_hover_color="#1a5585",
                                       segmented_button_unselected_hover_color="#3a3a3a",
                                       segmented_button_unselected_color="#2b2b2b",
                                       text_color="white",
                                       text_color_disabled="#8a8a8a",
                                       corner_radius=10)
        self.tab_view.grid(row=4, column=0, sticky="nsew", padx=25, pady=10)

        self.tab_view.add("About")
        self.tab_view.add("FB Lite")
        self.tab_view.add("TikTok")
        self.tab_view.add("YouTube")
        self.tab_view.add("Text Cmd")
        self.tab_view.add("Image")
        self.tab_view.set("About")

        self._configure_tab_layouts()

        self.status_label = ctk.CTkLabel(self.control_panel, text="", anchor='w', font=("Segoe UI", 14, "italic"))
        self.status_label.grid(row=5, column=0, sticky='ew', padx=25, pady=(10, 0))

        self.device_view_panel = ctk.CTkFrame(self, fg_color="#1e1e1e", corner_radius=15)
        self.device_view_panel.grid(row=0, column=1, sticky="nsew", padx=(20, 20), pady=(20, 20))

        self.stop_all_button = ctk.CTkButton(self.device_view_panel, text="Stop All Commands",
                                             command=self.stop_all_commands, fg_color="#ffc107",
                                             hover_color="#e0a800", text_color="#2b2b2b", corner_radius=8)
        self.stop_all_button.pack(side="bottom", fill="x", padx=15, pady=(0, 15))

        self.detect_devices()
        self.check_for_updates()

    def check_for_updates(self):
        def _check_in_thread():
            try:
                response = requests.get(VERSION_CHECK_URL, timeout=5)
                response.raise_for_status()
                latest_version = response.text.strip()
                if latest_version > __version__:
                    self.after(0, self.ask_for_update, latest_version)
            except requests.exceptions.RequestException as e:
                print(f"Update check failed: {e}")
            except Exception as e:
                print(f"An unexpected error occurred during version check: {e}")

        update_thread = threading.Thread(target=_check_in_thread, daemon=True)
        update_thread.start()

    def ask_for_update(self, latest_version):
        # The old message:
        # response = messagebox.askyesno("New Update Available",
        #                                f"A new version ({latest_version}) is available. Do you want to update now?\n"
        #                                "The application will restart after the update.")

        # --- NEW MESSAGE ---
        title = "New Dars V3 Controller Update!"
        message = (
            f"An improved version ({latest_version}) is now available!\n\n"
            "This update contains the latest upgrades and performance improvements for faster and more reliable control of your devices.\n\n"
            "The app will close and restart to complete the update. Would you like to update now?"
        )

        response = messagebox.askyesno(title, message)
        # --- END ---

        if response:
            self.update_app()

    def on_closing(self):
        self.stop_capture()
        self.executor.shutdown(wait=False)
        self.destroy()

    def _configure_tab_layouts(self):
        """Helper method to configure the grid layout for each tab with improved spacing."""

        # About Tab
        about_frame = self.tab_view.tab("About")
        about_frame.columnconfigure(0, weight=1)
        about_frame.rowconfigure(1, weight=1)

        ctk.CTkLabel(about_frame, text="About Dars V3 Controller", font=ctk.CTkFont(size=20, weight="bold"),
                     text_color="#18a2ff").grid(row=0, column=0, pady=(15, 5), sticky="n")

        about_text = """
The "Dars V3 Controller" is a desktop application designed to simplify the management and control of multiple Android devices simultaneously. It leverages the Android Debug Bridge (ADB) to send commands quickly and efficiently. Through its simple interface, you can perform various tasks such as tapping, swiping, and running specific commands on all connected devices at once.

---

### Getting Started

1. **Connect Your Devices**: Ensure **USB Debugging** is enabled on all Android devices you intend to use. Then, connect them to your computer using USB cables.

2. **Refresh the Device List**: On the left-side control panel, click the **"Refresh"** button. The application will automatically detect and list all connected devices by their serial number.

3. **Select the Device to Control**: Click on a device's serial number from the list. When selected, the device's screen will appear on the right side of the app, allowing you to control it directly.

---

### Controlling the Device Screen

The main feature of this tool is the **live screen control**. Once your device is connected and its screen is visible, you can perform the following actions:

* **Tap (Single Click)**: Click anywhere on the screen to simulate a single tap.
* **Swipe**: Click and drag your mouse on the device screen. This will perform a swipe gesture just like on the physical device.
* **Long Press**: Press and hold the left mouse button for half a second (0.5s). This will execute a long press command.

Additionally, there are pre-set buttons below the device screen for quick actions:
* **Home**: Returns to the device's home screen.
* **Back**: Navigates back to the previous screen.
* **Recents**: Shows the list of recently used apps.
* **Scroll Down/Up**: Scrolls the screen up or down.

---

### Additional Features (Tab View)

The left-side panel features a **Tab View** with various command categories.

* **FB Lite**: Use this tab to open Facebook posts, share links, or launch/force-stop the Facebook Lite app.
* **TikTok**: Open TikTok post URLs or launch/force-stop the TikTok Lite app.
* **YouTube**: Visit YouTube video URLs or launch/force-stop the YouTube app (using Chrome).
* **Text Cmd**: Select a text file and send a random line of text to all devices. You can also remove emojis from the selected file.
* **Image**: Enter the filename of an image in your phone's `Download` folder to share it via Facebook Lite.

---

### Important Notes

* **General Control**: All commands (except for taps, swipes, and long presses) are sent to **all connected devices simultaneously**.
* **Stop All Commands**: To halt any currently running commands, click the **"Stop All Commands"** button.
* **Auto-Update**: The tool includes an update feature. Click the "Update" button to automatically download the latest version to your Desktop.
* **ADB Path**: Ensure that **ADB (Android Debug Bridge)** is installed and added to your system's PATH for the application to function correctly.
        """
        about_label = ctk.CTkLabel(about_frame, text=about_text, font=ctk.CTkFont(size=14),
                                   justify="left", anchor="w", wraplength=350)
        about_label.grid(row=1, column=0, padx=15, pady=15, sticky="ew")

        # Facebook Lite Tab
        fb_frame = self.tab_view.tab("FB Lite")
        fb_frame.columnconfigure(0, weight=1)
        fb_frame.rowconfigure(6, weight=1)

        ctk.CTkLabel(fb_frame, text="Facebook Post URL:", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky='w', padx=15, pady=(15, 5))
        self.fb_url_entry = ctk.CTkEntry(fb_frame, placeholder_text="Enter Facebook URL...", height=40, corner_radius=8)
        self.fb_url_entry.grid(row=1, column=0, sticky='ew', padx=15, pady=0)
        self.fb_button = ctk.CTkButton(fb_frame, text="Visit Post", command=self.open_fb_lite_deeplink,
                                       fg_color="#1877f2", hover_color="#1651b7", height=45,
                                       font=ctk.CTkFont(weight="bold"))
        self.fb_button.grid(row=2, column=0, sticky='ew', padx=15, pady=10)

        ctk.CTkLabel(fb_frame, text="Link to Share:", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=3, column=0, sticky='w', pady=(15, 5), padx=15)
        self.fb_share_url_entry = ctk.CTkEntry(fb_frame, placeholder_text="Enter link to share...", height=40,
                                               corner_radius=8)
        self.fb_share_url_entry.grid(row=4, column=0, sticky='ew', padx=15, pady=0)
        self.share_button = ctk.CTkButton(fb_frame, text="Share Post", command=self.share_fb_lite_deeplink,
                                          fg_color="#42b72a", hover_color="#369720", height=45,
                                          font=ctk.CTkFont(weight="bold"))
        self.share_button.grid(row=5, column=0, sticky='ew', padx=15, pady=10)

        fb_launch_frame = ctk.CTkFrame(fb_frame, fg_color="transparent")
        fb_launch_frame.grid(row=6, column=0, sticky='ew', padx=15, pady=(20, 5))
        fb_launch_frame.columnconfigure(0, weight=1)
        fb_launch_frame.columnconfigure(1, weight=1)
        self.launch_fb_lite_button = ctk.CTkButton(fb_launch_frame, text="Launch FB Lite", command=self.launch_fb_lite,
                                                   corner_radius=8)
        self.launch_fb_lite_button.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        self.force_stop_fb_lite_button = ctk.CTkButton(fb_launch_frame, text="Force Stop",
                                                       command=self.force_stop_fb_lite, fg_color="#dc3545",
                                                       hover_color="#c82333", corner_radius=8)
        self.force_stop_fb_lite_button.grid(row=0, column=1, sticky='ew', padx=(5, 0))

        # TikTok Tab
        tiktok_frame = self.tab_view.tab("TikTok")
        tiktok_frame.columnconfigure(0, weight=1)
        tiktok_frame.rowconfigure(4, weight=1)

        ctk.CTkLabel(tiktok_frame, text="TikTok URL:", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0,
                                                                                                      sticky='w',
                                                                                                      pady=(15, 5),
                                                                                                      padx=15)
        self.tiktok_url_entry = ctk.CTkEntry(tiktok_frame, placeholder_text="Enter TikTok URL...", height=40,
                                             corner_radius=8)
        self.tiktok_url_entry.grid(row=1, column=0, sticky='ew', padx=15)
        self.tiktok_button = ctk.CTkButton(tiktok_frame, text="Visit Post", command=self.open_tiktok_lite_deeplink,
                                           fg_color="#fe2c55", hover_color="#c82333", height=45,
                                           font=ctk.CTkFont(weight="bold"))
        self.tiktok_button.grid(row=2, column=0, pady=10, sticky='ew', padx=15)

        tiktok_launch_frame = ctk.CTkFrame(tiktok_frame, fg_color="transparent")
        tiktok_launch_frame.grid(row=3, column=0, sticky='ew', padx=15, pady=(20, 5))
        tiktok_launch_frame.columnconfigure(0, weight=1)
        tiktok_launch_frame.columnconfigure(1, weight=1)
        self.launch_tiktok_lite_button = ctk.CTkButton(tiktok_launch_frame, text="Launch TikTok Lite",
                                                       command=self.launch_tiktok_lite, corner_radius=8)
        self.launch_tiktok_lite_button.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        self.force_stop_tiktok_lite_button = ctk.CTkButton(tiktok_launch_frame, text="Force Stop",
                                                           command=self.force_stop_tiktok_lite, fg_color="#dc3545",
                                                           hover_color="#c82333", corner_radius=8)
        self.force_stop_tiktok_lite_button.grid(row=0, column=1, sticky='ew', padx=(5, 0))

        # YouTube Tab
        youtube_frame = self.tab_view.tab("YouTube")
        youtube_frame.columnconfigure(0, weight=1)
        youtube_frame.rowconfigure(4, weight=1)

        ctk.CTkLabel(youtube_frame, text="YouTube URL:", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0,
                                                                                                        sticky='w',
                                                                                                        pady=(15, 5),
                                                                                                        padx=15)
        self.youtube_url_entry = ctk.CTkEntry(youtube_frame, placeholder_text="Enter YouTube URL...", height=40,
                                              corner_radius=8)
        self.youtube_url_entry.grid(row=1, column=0, sticky='ew', padx=15)
        self.youtube_button = ctk.CTkButton(youtube_frame, text="Visit Video", command=self.open_youtube_deeplink,
                                            fg_color="#ff0000", hover_color="#cc0000", height=45,
                                            font=ctk.CTkFont(weight="bold"))
        self.youtube_button.grid(row=2, column=0, pady=10, sticky='ew', padx=15)

        youtube_launch_frame = ctk.CTkFrame(youtube_frame, fg_color="transparent")
        youtube_launch_frame.grid(row=3, column=0, sticky='ew', padx=15, pady=(20, 5))
        youtube_launch_frame.columnconfigure(0, weight=1)
        youtube_launch_frame.columnconfigure(1, weight=1)
        self.launch_youtube_button = ctk.CTkButton(youtube_launch_frame, text="Launch YouTube",
                                                   command=self.launch_youtube, corner_radius=8)
        self.launch_youtube_button.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        self.force_stop_youtube_button = ctk.CTkButton(youtube_launch_frame, text="Force Stop",
                                                       command=self.force_stop_youtube, fg_color="#dc3545",
                                                       hover_color="#c82333", corner_radius=8)
        self.force_stop_youtube_button.grid(row=0, column=1, sticky='ew', padx=(5, 0))

        # Text Command Tab
        text_frame = self.tab_view.tab("Text Cmd")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(4, weight=1)

        ctk.CTkLabel(text_frame, text="Text Command from File:", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0,
                                                                                                                column=0,
                                                                                                                sticky='w',
                                                                                                                pady=(
                                                                                                                    15,
                                                                                                                    5),
                                                                                                                padx=15)
        self.file_path_entry = ctk.CTkEntry(text_frame, placeholder_text="Select a text file...", height=40,
                                            corner_radius=8)
        self.file_path_entry.grid(row=1, column=0, sticky='ew', padx=15)
        browse_button = ctk.CTkButton(text_frame, text="Browse", command=self.browse_file, corner_radius=8)
        browse_button.grid(row=2, column=0, sticky='ew', padx=15, pady=(10, 10))
        self.send_button = ctk.CTkButton(text_frame, text="Send Text", command=self.send_text_to_devices,
                                         fg_color="#28a745", hover_color="#218838", height=45,
                                         font=ctk.CTkFont(weight="bold"))
        self.send_button.grid(row=3, column=0, sticky='ew', padx=15, pady=(5, 5))

        self.remove_emoji_button = ctk.CTkButton(text_frame, text="Remove Emojis 🚫",
                                                 command=self.remove_emojis_from_file,
                                                 fg_color="#ff5733", hover_color="#c04228", height=45,
                                                 font=ctk.CTkFont(weight="bold"))
        self.remove_emoji_button.grid(row=4, column=0, sticky='ew', padx=15, pady=(5, 15))

        # Image Tab
        image_frame = self.tab_view.tab("Image")
        image_frame.columnconfigure(0, weight=1)
        image_frame.rowconfigure(2, weight=1)

        ctk.CTkLabel(image_frame, text="Photo Name (e.g., photo.jpg):", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky='w', pady=(15, 5), padx=15)
        self.image_file_name_entry = ctk.CTkEntry(image_frame, placeholder_text="Enter image name...", height=40,
                                                  corner_radius=8)
        self.image_file_name_entry.grid(row=1, column=0, sticky='ew', padx=15)
        self.share_image_button = ctk.CTkButton(image_frame, text="Share Image", command=self.share_image_to_fb_lite,
                                                fg_color="#42b72a", hover_color="#369720", height=45,
                                                font=ctk.CTkFont(weight="bold"))
        self.share_image_button.grid(row=2, column=0, sticky='ew', padx=15, pady=(10, 5))

    def update_app(self):
        def _update_in_thread():
            try:
                self.status_label.configure(text="Downloading latest version...", text_color="#007bff")

                response = requests.get(UPDATE_URL)
                response.raise_for_status()

                desktop_path = Path.home() / "Desktop"
                old_file_path = Path(sys.executable) if getattr(sys, 'frozen', False) else Path(sys.argv[0])
                new_file_path = desktop_path / "main.py"

                if old_file_path.name != "main.py":
                    messagebox.showerror("Update Error",
                                         "Cannot update. The application is not running from the Desktop or its filename is not 'main.py'.")
                    return

                with open(new_file_path, 'wb') as f:
                    f.write(response.content)

                messagebox.showinfo("Update Complete",
                                    "The new version has been downloaded. The application will now close and update.")

                create_and_run_updater_script(new_file_path, old_file_path)

                self.destroy()

            except requests.exceptions.RequestException as e:
                self.status_label.configure(text=f"❌ Error downloading update: {e}", text_color="#dc3545")
                messagebox.showerror("Update Error",
                                     f"Failed to download update. Check your internet connection.\nError: {e}")
            except Exception as e:
                self.status_label.configure(text=f"❌ An error occurred during update: {e}", text_color="#dc3545")
                messagebox.showerror("Update Error", f"An unexpected error occurred.\nError: {e}")

        update_thread = threading.Thread(target=_update_in_thread, daemon=True)
        update_thread.start()

    def browse_file(self):
        file_path = filedialog.askopenfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if file_path:
            self.file_path_entry.delete(0, tk.END)
            self.file_path_entry.insert(0, file_path)
            self.status_label.configure(text=f"File selected: {os.path.basename(file_path)}", text_color="#28a745")

    def _threaded_send_text(self):
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
                text=f"Sending random text from file '{os.path.basename(file_path)}' to all devices...",
                text_color="#e0e0e0")

            for device_serial in self.devices:
                random_text = random.choice(clean_lines)
                self.executor.submit(run_text_command, random_text, device_serial)

        except FileNotFoundError:
            self.status_label.configure(text="❌ File not found.", text_color="#dc3545")
        except Exception as e:
            self.status_label.configure(text=f"❌ An error occurred: {e}", text_color="#dc3545")

    def send_text_to_devices(self):
        send_thread = threading.Thread(target=self._threaded_send_text, daemon=True)
        send_thread.start()

    def remove_emojis_from_file(self):
        file_path = self.file_path_entry.get()
        if not file_path:
            self.status_label.configure(text="⚠️ Please select a text file first.", text_color="#ffc107")
            return

        try:
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
                                       "\U00002600-\U000026FF"  # Miscellaneous Symbols (kasama ang ☕)
                                       "\U000025A0-\U000025FF"  # Geometric Shapes (kasama ang ⬛)
                                       "]+", flags=re.UNICODE)

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            cleaned_content = emoji_pattern.sub(r'', content)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(cleaned_content)

            self.status_label.configure(text="✅ Emojis and symbols successfully removed from the file.",
                                        text_color="#28a745")

        except FileNotFoundError:
            self.status_label.configure(text="❌ File not found.", text_color="#dc3545")
        except Exception as e:
            self.status_label.configure(text=f"❌ An error occurred: {e}", text_color="#dc3545")

    def detect_devices(self):
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
        self.status_label.configure(text="Detecting devices...", text_color="#e0e0e0")

        try:
            result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, check=True, timeout=10)
            devices_output = result.stdout.strip().split('\n')[1:]
            self.devices = [line.split('\t')[0] for line in devices_output if line.strip() and 'device' in line]
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            messagebox.showerror("Error", "ADB is not installed, not in your system PATH, or timed out.")
            self.status_label.configure(text="❌ ADB not found or timed out.", text_color="#dc3545")
            self.device_count_label.configure(text="Connected Devices: 0")
            return

        self.device_count_label.configure(text=f"Connected Devices: {len(self.devices)}")

        if not self.devices:
            no_devices_label = ctk.CTkLabel(self.device_view_panel,
                                            text="No devices found. Make sure USB debugging is enabled.",
                                            font=ctk.CTkFont(size=16, weight="bold"), text_color="#999999")
            no_devices_label.pack(expand=True)
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return
        else:
            self.status_label.configure(text=f"✅ {len(self.devices)} devices detected.", text_color="#28a745")

        for serial in self.devices:
            self.device_listbox.insert(tk.END, serial)

        if self.devices:
            self.device_listbox.selection_set(0)
            self.on_device_select()

    def on_device_select(self, event=None):
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
        self.is_capturing = False
        if self.update_image_id:
            self.after_cancel(self.update_image_id)
            self.update_image_id = None
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=1)
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
                    continue
                process = subprocess.run(['adb', '-s', self.selected_device_serial, 'exec-out', 'screencap', '-p'],
                                         capture_output=True, check=True, timeout=5)
                self.screenshot_queue.put(process.stdout)
            except subprocess.CalledProcessError as e:
                print(f"Error capturing screen: {e.stderr.decode()}")
                self.is_capturing = False
            except subprocess.TimeoutExpired:
                print(f"Screen capture timed out for device {self.selected_device_serial}")
            except Exception as e:
                print(f"An error occurred in capture loop: {e}")
                self.is_capturing = False

    def update_image(self):
        try:
            if not self.selected_device_serial:
                return

            canvas = self.device_canvases.get(self.selected_device_serial)
            if not canvas:
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

                        if 'item_id' in self.device_images.get(self.selected_device_serial, {}):
                            image_item_id = self.device_images[self.selected_device_serial]['item_id']
                            canvas.itemconfig(image_item_id, image=tk_image)
                        else:
                            image_item_id = canvas.create_image(canvas_width / 2, canvas_height / 2, image=tk_image)
                            self.device_images[self.selected_device_serial]['item_id'] = image_item_id
                            canvas.itemconfig(image_item_id, anchor=tk.CENTER)

            if self.is_capturing:
                self.update_image_id = self.after(100, self.update_image)

        except Exception as e:
            self.stop_capture()

    def create_device_frame(self, serial):
        device_frame = ctk.CTkFrame(self.device_view_panel, fg_color="#2b2b2b", corner_radius=15)
        device_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        self.device_frames[serial] = device_frame

        title = ctk.CTkLabel(device_frame, text=f"Device: {serial}", font=ctk.CTkFont(size=18, weight="bold"))
        title.pack(pady=(15, 10))

        canvas = tk.Canvas(device_frame, bg="#1e1e1e", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 5))
        self.device_canvases[serial] = canvas

        canvas.bind("<ButtonPress-1>", lambda event: self.start_press(event, serial))
        canvas.bind("<ButtonRelease-1>", lambda event: self.handle_release(event, serial))

        button_frame = ctk.CTkFrame(device_frame, fg_color="transparent")
        button_frame.pack(pady=(10, 15))

        home_button = ctk.CTkButton(button_frame, text="Home", command=lambda: self.send_adb_keyevent(3),
                                    corner_radius=8, width=70)
        home_button.pack(side=tk.LEFT, padx=5)

        back_button = ctk.CTkButton(button_frame, text="Back", command=lambda: self.send_adb_keyevent(4),
                                    corner_radius=8, width=70)
        back_button.pack(side=tk.LEFT, padx=5)

        recents_button = ctk.CTkButton(button_frame, text="Recents", command=lambda: self.send_adb_keyevent(187),
                                       corner_radius=8, width=70)
        recents_button.pack(side=tk.LEFT, padx=5)

        scroll_down_button = ctk.CTkButton(button_frame, text="Scroll Down",
                                           command=lambda: self.send_adb_swipe(serial, 'up'), corner_radius=8, width=70)
        scroll_down_button.pack(side=tk.LEFT, padx=5)

        scroll_up_button = ctk.CTkButton(button_frame, text="Scroll Up",
                                         command=lambda: self.send_adb_swipe(serial, 'down'), corner_radius=8, width=70)
        scroll_up_button.pack(side=tk.LEFT, padx=5)

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

    def send_adb_tap(self, event, serial):
        try:
            pil_image = self.device_images.get(self.selected_device_serial, {}).get('pil_image')
            if not pil_image:
                print("Image not loaded for scaling.")
                return

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

            click_x = event.x - image_x_offset
            click_y = event.y - image_y_offset

            if 0 <= click_x < effective_width and 0 <= click_y < effective_height:
                adb_size_output = subprocess.run(['adb', '-s', serial, 'shell', 'wm', 'size'], capture_output=True,
                                                 text=True, check=True).stdout.strip()
                adb_width, adb_height = map(int, adb_size_output.split()[-1].split('x'))
                scaled_x = int(click_x * adb_width / effective_width)
                scaled_y = int(click_y * adb_height / effective_height)

                command = ['shell', 'input', 'tap', str(scaled_x), str(scaled_y)]
                for device_serial in self.devices:
                    self.executor.submit(run_adb_command, command, device_serial)
                self.status_label.configure(text=f"✅ Tap command sent to all devices.", text_color="#28a745")
        except Exception as e:
            self.status_label.configure(text=f"❌ Error handling tap for device {serial}: {e}", text_color="#dc3545")
            print(f"Error handling tap for device {serial}: {e}")

    def send_adb_long_press(self, event, serial):
        try:
            pil_image = self.device_images.get(self.selected_device_serial, {}).get('pil_image')
            if not pil_image:
                print("Image not loaded for scaling.")
                return

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

            click_x = event.x - image_x_offset
            click_y = event.y - image_y_offset

            if 0 <= click_x < effective_width and 0 <= click_y < effective_height:
                adb_size_output = subprocess.run(['adb', '-s', serial, 'shell', 'wm', 'size'], capture_output=True,
                                                 text=True, check=True).stdout.strip()
                adb_width, adb_height = map(int, adb_size_output.split()[-1].split('x'))
                scaled_x = int(click_x * adb_width / effective_width)
                scaled_y = int(click_y * adb_height / effective_height)

                command = ['shell', 'input', 'swipe', str(scaled_x), str(scaled_y), str(scaled_x), str(scaled_y),
                           '1000']
                for device_serial in self.devices:
                    self.executor.submit(run_adb_command, command, device_serial)
                self.status_label.configure(text=f"✅ Long press command sent to all devices.", text_color="#28a745")
        except Exception as e:
            self.status_label.configure(text=f"❌ Error handling long press for device {serial}: {e}",
                                        text_color="#dc3545")
            print(f"Error handling long press for device {serial}: {e}")

    def send_adb_swipe_command(self, start_x, start_y, end_x, end_y, serial):
        try:
            pil_image = self.device_images.get(self.selected_device_serial, {}).get('pil_image')
            if not pil_image:
                print("Image not loaded for scaling.")
                return

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

            image_start_x = start_x - image_x_offset
            image_start_y = start_y - image_y_offset
            image_end_x = end_x - image_x_offset
            image_end_y = end_y - image_y_offset

            adb_size_output = subprocess.run(['adb', '-s', serial, 'shell', 'wm', 'size'], capture_output=True,
                                             text=True, check=True).stdout.strip()
            adb_width, adb_height = map(int, adb_size_output.split()[-1].split('x'))
            scaled_start_x = int(image_start_x * adb_width / effective_width)
            scaled_start_y = int(image_start_y * adb_height / effective_height)
            scaled_end_x = int(image_end_x * adb_width / effective_width)
            scaled_end_y = int(image_end_y * adb_height / effective_height)

            command = ['shell', 'input', 'swipe',
                       str(scaled_start_x), str(scaled_start_y),
                       str(scaled_end_x), str(scaled_end_y), '300']
            for device_serial in self.devices:
                self.executor.submit(run_adb_command, command, device_serial)
            self.status_label.configure(text=f"✅ Swipe command sent to all devices.", text_color="#28a745")
        except Exception as e:
            self.status_label.configure(text=f"❌ Error handling swipe for device {serial}: {e}", text_color="#dc3545")
            print(f"Error handling swipe for device {serial}: {e}")

    def send_adb_swipe(self, serial, direction):
        try:
            adb_width_str = subprocess.run(['adb', '-s', serial, 'shell', 'wm', 'size'], capture_output=True, text=True,
                                           check=True).stdout.strip().split()[-1]
            adb_width, adb_height = map(int, adb_width_str.split('x'))

            if direction == 'down':
                start_x, start_y = adb_width // 2, adb_height // 4
                end_x, end_y = start_x, adb_height // 4 * 3
            elif direction == 'up':
                start_x, start_y = adb_width // 2, adb_height // 4 * 3
                end_x, end_y = start_x, adb_height // 4

            command = ['shell', 'input', 'swipe',
                       str(start_x), str(start_y), str(end_x), str(end_y), '300']
            for device_serial in self.devices:
                self.executor.submit(run_adb_command, command, device_serial)
            self.status_label.configure(text=f"✅ {direction.capitalize()} swipe command sent to all devices.",
                                        text_color="#28a745")
        except Exception as e:
            self.status_label.configure(text=f"❌ Error sending swipe to device {serial}: {e}", text_color="#dc3545")
            print(f"Error sending swipe to device {serial}: {e}")

    def send_adb_keyevent(self, keycode):
        command = ['shell', 'input', 'keyevent', str(keycode)]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Key event sent to all devices.", text_color="#28a745")

    def open_fb_lite_deeplink(self):
        post_url = self.fb_url_entry.get()
        if not post_url:
            self.status_label.configure(text="⚠️ Please enter a Facebook post URL.", text_color="#ffc107")
            return

        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Opening posts URL on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'start',
            '-a', 'android.intent.action.VIEW',
            '-d', f'"{post_url}"',
            'com.facebook.lite'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Visited post on all devices.", text_color="#28a745")

    def share_fb_lite_deeplink(self):
        share_url = self.fb_share_url_entry.get()
        if not share_url:
            self.status_label.configure(text="⚠️ Please enter a link to share.", text_color="#ffc107")
            return

        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text="Sending sharing URL to all devices...", text_color="#e0e0e0")

        command = ['shell', 'am', 'start', '-a', 'android.intent.action.SEND', '-t', 'text/plain', '--es',
                   'android.intent.extra.TEXT', f'"{share_url}"', 'com.facebook.lite']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Shared post on all devices.", text_color="#28a745")

    def launch_fb_lite(self):
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Launching Facebook Lite on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'start', '-n',
            'com.facebook.lite/com.facebook.lite.MainActivity'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Launched Facebook Lite on all devices.", text_color="#28a745")

    def force_stop_fb_lite(self):
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Force stopping Facebook Lite on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'force-stop',
            'com.facebook.lite'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Force stopped Facebook Lite on all devices.", text_color="#28a745")

    def open_tiktok_lite_deeplink(self):
        post_url = self.tiktok_url_entry.get()
        if not post_url:
            self.status_label.configure(text="⚠️ Please enter a TikTok URL.", text_color="#ffc107")
            return

        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Opening TikTok URL on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'start',
            '-a', 'android.intent.action.VIEW',
            '-d', f'"{post_url}"',
            'com.zhiliaoapp.musically.go'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Visited post on all devices.", text_color="#28a745")

    def launch_tiktok_lite(self):
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Launching TikTok Lite on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'start', '-n',
            'com.zhiliaoapp.musically.go/com.ss.android.ugc.aweme.main.homepage.MainActivity'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Launched TikTok Lite on all devices.", text_color="#28a745")

    def force_stop_tiktok_lite(self):
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Force stopping TikTok Lite on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'force-stop',
            'com.zhiliaoapp.musically.go'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Force stopped TikTok Lite on all devices.", text_color="#28a745")

    def open_youtube_deeplink(self):
        video_url = self.youtube_url_entry.get()
        if not video_url:
            self.status_label.configure(text="⚠️ Please enter a YouTube URL.", text_color="#ffc107")
            return

        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Opening YouTube video on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'start',
            '-a', 'android.intent.action.VIEW',
            '-d', f'"{video_url}"',
            'com.android.chrome/com.google.android.apps.chrome.Main'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Visited video on all devices.", text_color="#28a745")

    def launch_youtube(self):
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Launching YouTube on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'start',
            '-a', 'android.intent.action.VIEW',
            '-d', 'https://m.youtube.com/',
            'com.android.chrome/com.google.android.apps.chrome.Main'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Launched YouTube on all devices.", text_color="#28a745")

    def force_stop_youtube(self):
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Force stopping YouTube on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'force-stop',
            'com.android.chrome'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Force stopped YouTube on all devices.", text_color="#28a745")

    def share_image_to_fb_lite(self):
        file_name = self.image_file_name_entry.get()
        if not file_name:
            self.status_label.configure(text="⚠️ Please enter the image filename.", text_color="#ffc107")
            return

        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Sending sharing intent for '{file_name}' to all devices...",
                                    text_color="#e0e0e0")

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
        self.status_label.configure(text="✅ Image sharing command sent to all devices.", text_color="#28a745")

    def stop_all_commands(self):
        self.status_label.configure(text="Stopping all active commands...", text_color="#ffc107")
        is_stop_requested.set()

        # Wait for all current tasks to finish (or be terminated)
        self.executor.shutdown(wait=True)

        # Reset the executor and the flag for new commands
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count() * 2)
        is_stop_requested.clear()

        self.status_label.configure(text="✅ All commands have been stopped.", text_color="#28a745")

    def browse_file(self):
        file_path = filedialog.askopenfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if file_path:
            self.file_path_entry.delete(0, tk.END)
            self.file_path_entry.insert(0, file_path)
            self.status_label.configure(text=f"File selected: {os.path.basename(file_path)}", text_color="#28a745")

    def _threaded_send_text(self):
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
                text=f"Sending random text from file '{os.path.basename(file_path)}' to all devices...",
                text_color="#e0e0e0")

            for device_serial in self.devices:
                random_text = random.choice(clean_lines)
                self.executor.submit(run_text_command, random_text, device_serial)

        except FileNotFoundError:
            self.status_label.configure(text="❌ File not found.", text_color="#dc3545")
        except Exception as e:
            self.status_label.configure(text=f"❌ An error occurred: {e}", text_color="#dc3545")

    def send_text_to_devices(self):
        send_thread = threading.Thread(target=self._threaded_send_text, daemon=True)
        send_thread.start()

    def remove_emojis_from_file(self):
        file_path = self.file_path_entry.get()
        if not file_path:
            self.status_label.configure(text="⚠️ Please select a text file first.", text_color="#ffc107")
            return

        try:
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
                                       "\U00002600-\U000026FF"  # Miscellaneous Symbols (kasama ang ☕)
                                       "\U000025A0-\U000025FF"  # Geometric Shapes (kasama ang ⬛)
                                       "]+", flags=re.UNICODE)

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            cleaned_content = emoji_pattern.sub(r'', content)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(cleaned_content)

            self.status_label.configure(text="✅ Emojis and symbols successfully removed from the file.",
                                        text_color="#28a745")

        except FileNotFoundError:
            self.status_label.configure(text="❌ File not found.", text_color="#dc3545")
        except Exception as e:
            self.status_label.configure(text=f"❌ An error occurred: {e}", text_color="#dc3545")

    def detect_devices(self):
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
        self.status_label.configure(text="Detecting devices...", text_color="#e0e0e0")

        try:
            result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, check=True, timeout=10)
            devices_output = result.stdout.strip().split('\n')[1:]
            self.devices = [line.split('\t')[0] for line in devices_output if line.strip() and 'device' in line]
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            messagebox.showerror("Error", "ADB is not installed, not in your system PATH, or timed out.")
            self.status_label.configure(text="❌ ADB not found or timed out.", text_color="#dc3545")
            self.device_count_label.configure(text="Connected Devices: 0")
            return

        self.device_count_label.configure(text=f"Connected Devices: {len(self.devices)}")

        if not self.devices:
            no_devices_label = ctk.CTkLabel(self.device_view_panel,
                                            text="No devices found. Make sure USB debugging is enabled.",
                                            font=ctk.CTkFont(size=16, weight="bold"), text_color="#999999")
            no_devices_label.pack(expand=True)
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return
        else:
            self.status_label.configure(text=f"✅ {len(self.devices)} devices detected.", text_color="#28a745")

        for serial in self.devices:
            self.device_listbox.insert(tk.END, serial)

        if self.devices:
            self.device_listbox.selection_set(0)
            self.on_device_select()

    def on_device_select(self, event=None):
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
        self.is_capturing = False
        if self.update_image_id:
            self.after_cancel(self.update_image_id)
            self.update_image_id = None
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=1)
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
                    continue
                process = subprocess.run(['adb', '-s', self.selected_device_serial, 'exec-out', 'screencap', '-p'],
                                         capture_output=True, check=True, timeout=5)
                self.screenshot_queue.put(process.stdout)
            except subprocess.CalledProcessError as e:
                print(f"Error capturing screen: {e.stderr.decode()}")
                self.is_capturing = False
            except subprocess.TimeoutExpired:
                print(f"Screen capture timed out for device {self.selected_device_serial}")
            except Exception as e:
                print(f"An error occurred in capture loop: {e}")
                self.is_capturing = False

    def update_image(self):
        try:
            if not self.selected_device_serial:
                return

            canvas = self.device_canvases.get(self.selected_device_serial)
            if not canvas:
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

                        if 'item_id' in self.device_images.get(self.selected_device_serial, {}):
                            image_item_id = self.device_images[self.selected_device_serial]['item_id']
                            canvas.itemconfig(image_item_id, image=tk_image)
                        else:
                            image_item_id = canvas.create_image(canvas_width / 2, canvas_height / 2, image=tk_image)
                            self.device_images[self.selected_device_serial]['item_id'] = image_item_id
                            canvas.itemconfig(image_item_id, anchor=tk.CENTER)

            if self.is_capturing:
                self.update_image_id = self.after(100, self.update_image)

        except Exception as e:
            print(f"Error in update_image: {e}")
            self.stop_capture()

    def create_device_frame(self, serial):
        device_frame = ctk.CTkFrame(self.device_view_panel, fg_color="#2b2b2b", corner_radius=15)
        device_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        self.device_frames[serial] = device_frame

        title = ctk.CTkLabel(device_frame, text=f"Device: {serial}", font=ctk.CTkFont(size=18, weight="bold"))
        title.pack(pady=(15, 10))

        canvas = tk.Canvas(device_frame, bg="#1e1e1e", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 5))
        self.device_canvases[serial] = canvas

        canvas.bind("<ButtonPress-1>", lambda event: self.start_press(event, serial))
        canvas.bind("<ButtonRelease-1>", lambda event: self.handle_release(event, serial))

        button_frame = ctk.CTkFrame(device_frame, fg_color="transparent")
        button_frame.pack(pady=(10, 15))

        home_button = ctk.CTkButton(button_frame, text="Home", command=lambda: self.send_adb_keyevent(3),
                                    corner_radius=8, width=70)
        home_button.pack(side=tk.LEFT, padx=5)

        back_button = ctk.CTkButton(button_frame, text="Back", command=lambda: self.send_adb_keyevent(4),
                                    corner_radius=8, width=70)
        back_button.pack(side=tk.LEFT, padx=5)

        recents_button = ctk.CTkButton(button_frame, text="Recents", command=lambda: self.send_adb_keyevent(187),
                                       corner_radius=8, width=70)
        recents_button.pack(side=tk.LEFT, padx=5)

        scroll_down_button = ctk.CTkButton(button_frame, text="Scroll Down",
                                           command=lambda: self.send_adb_swipe(serial, 'up'), corner_radius=8, width=70)
        scroll_down_button.pack(side=tk.LEFT, padx=5)

        scroll_up_button = ctk.CTkButton(button_frame, text="Scroll Up",
                                         command=lambda: self.send_adb_swipe(serial, 'down'), corner_radius=8, width=70)
        scroll_up_button.pack(side=tk.LEFT, padx=5)

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

    def send_adb_tap(self, event, serial):
        try:
            pil_image = self.device_images.get(self.selected_device_serial, {}).get('pil_image')
            if not pil_image:
                print("Image not loaded for scaling.")
                return

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

            click_x = event.x - image_x_offset
            click_y = event.y - image_y_offset

            if 0 <= click_x < effective_width and 0 <= click_y < effective_height:
                adb_size_output = subprocess.run(['adb', '-s', serial, 'shell', 'wm', 'size'], capture_output=True,
                                                 text=True, check=True).stdout.strip()
                adb_width, adb_height = map(int, adb_size_output.split()[-1].split('x'))
                scaled_x = int(click_x * adb_width / effective_width)
                scaled_y = int(click_y * adb_height / effective_height)

                command = ['shell', 'input', 'tap', str(scaled_x), str(scaled_y)]
                for device_serial in self.devices:
                    self.executor.submit(run_adb_command, command, device_serial)
                self.status_label.configure(text=f"✅ Tap command sent to all devices.", text_color="#28a745")
        except Exception as e:
            self.status_label.configure(text=f"❌ Error handling tap for device {serial}: {e}", text_color="#dc3545")
            print(f"Error handling tap for device {serial}: {e}")

    def send_adb_long_press(self, event, serial):
        try:
            pil_image = self.device_images.get(self.selected_device_serial, {}).get('pil_image')
            if not pil_image:
                print("Image not loaded for scaling.")
                return

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

            click_x = event.x - image_x_offset
            click_y = event.y - image_y_offset

            if 0 <= click_x < effective_width and 0 <= click_y < effective_height:
                adb_size_output = subprocess.run(['adb', '-s', serial, 'shell', 'wm', 'size'], capture_output=True,
                                                 text=True, check=True).stdout.strip()
                adb_width, adb_height = map(int, adb_size_output.split()[-1].split('x'))
                scaled_x = int(click_x * adb_width / effective_width)
                scaled_y = int(click_y * adb_height / effective_height)

                command = ['shell', 'input', 'swipe', str(scaled_x), str(scaled_y), str(scaled_x), str(scaled_y),
                           '1000']
                for device_serial in self.devices:
                    self.executor.submit(run_adb_command, command, device_serial)
                self.status_label.configure(text=f"✅ Long press command sent to all devices.", text_color="#28a745")
        except Exception as e:
            self.status_label.configure(text=f"❌ Error handling long press for device {serial}: {e}",
                                        text_color="#dc3545")
            print(f"Error handling long press for device {serial}: {e}")

    def send_adb_swipe_command(self, start_x, start_y, end_x, end_y, serial):
        try:
            pil_image = self.device_images.get(self.selected_device_serial, {}).get('pil_image')
            if not pil_image:
                print("Image not loaded for scaling.")
                return

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

            image_start_x = start_x - image_x_offset
            image_start_y = start_y - image_y_offset
            image_end_x = end_x - image_x_offset
            image_end_y = end_y - image_y_offset

            adb_size_output = subprocess.run(['adb', '-s', serial, 'shell', 'wm', 'size'], capture_output=True,
                                             text=True, check=True).stdout.strip()
            adb_width, adb_height = map(int, adb_size_output.split()[-1].split('x'))
            scaled_start_x = int(image_start_x * adb_width / effective_width)
            scaled_start_y = int(image_start_y * adb_height / effective_height)
            scaled_end_x = int(image_end_x * adb_width / effective_width)
            scaled_end_y = int(image_end_y * adb_height / effective_height)

            command = ['shell', 'input', 'swipe',
                       str(scaled_start_x), str(scaled_start_y),
                       str(scaled_end_x), str(scaled_end_y), '300']
            for device_serial in self.devices:
                self.executor.submit(run_adb_command, command, device_serial)
            self.status_label.configure(text=f"✅ Swipe command sent to all devices.", text_color="#28a745")
        except Exception as e:
            self.status_label.configure(text=f"❌ Error handling swipe for device {serial}: {e}", text_color="#dc3545")
            print(f"Error handling swipe for device {serial}: {e}")

    def send_adb_swipe(self, serial, direction):
        try:
            adb_width_str = subprocess.run(['adb', '-s', serial, 'shell', 'wm', 'size'], capture_output=True, text=True,
                                           check=True).stdout.strip().split()[-1]
            adb_width, adb_height = map(int, adb_width_str.split('x'))

            if direction == 'down':
                start_x, start_y = adb_width // 2, adb_height // 4
                end_x, end_y = start_x, adb_height // 4 * 3
            elif direction == 'up':
                start_x, start_y = adb_width // 2, adb_height // 4 * 3
                end_x, end_y = start_x, adb_height // 4

            command = ['shell', 'input', 'swipe',
                       str(start_x), str(start_y), str(end_x), str(end_y), '300']
            for device_serial in self.devices:
                self.executor.submit(run_adb_command, command, device_serial)
            self.status_label.configure(text=f"✅ {direction.capitalize()} swipe command sent to all devices.",
                                        text_color="#28a745")
        except Exception as e:
            self.status_label.configure(text=f"❌ Error sending swipe to device {serial}: {e}", text_color="#dc3545")
            print(f"Error sending swipe to device {serial}: {e}")

    def send_adb_keyevent(self, keycode):
        command = ['shell', 'input', 'keyevent', str(keycode)]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Key event sent to all devices.", text_color="#28a745")

    def open_fb_lite_deeplink(self):
        post_url = self.fb_url_entry.get()
        if not post_url:
            self.status_label.configure(text="⚠️ Please enter a Facebook post URL.", text_color="#ffc107")
            return

        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Opening posts URL on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'start',
            '-a', 'android.intent.action.VIEW',
            '-d', f'"{post_url}"',
            'com.facebook.lite'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Visited post on all devices.", text_color="#28a745")

    def share_fb_lite_deeplink(self):
        share_url = self.fb_share_url_entry.get()
        if not share_url:
            self.status_label.configure(text="⚠️ Please enter a link to share.", text_color="#ffc107")
            return

        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text="Sending sharing URL to all devices...", text_color="#e0e0e0")

        command = ['shell', 'am', 'start', '-a', 'android.intent.action.SEND', '-t', 'text/plain', '--es',
                   'android.intent.extra.TEXT', f'"{share_url}"', 'com.facebook.lite']
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Shared post on all devices.", text_color="#28a745")

    def launch_fb_lite(self):
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Launching Facebook Lite on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'start', '-n',
            'com.facebook.lite/com.facebook.lite.MainActivity'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Launched Facebook Lite on all devices.", text_color="#28a745")

    def force_stop_fb_lite(self):
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Force stopping Facebook Lite on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'force-stop',
            'com.facebook.lite'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Force stopped Facebook Lite on all devices.", text_color="#28a745")

    def open_tiktok_lite_deeplink(self):
        post_url = self.tiktok_url_entry.get()
        if not post_url:
            self.status_label.configure(text="⚠️ Please enter a TikTok URL.", text_color="#ffc107")
            return

        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Opening TikTok URL on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'start',
            '-a', 'android.intent.action.VIEW',
            '-d', f'"{post_url}"',
            'com.zhiliaoapp.musically.go'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Visited post on all devices.", text_color="#28a745")

    def launch_tiktok_lite(self):
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Launching TikTok Lite on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'start', '-n',
            'com.zhiliaoapp.musically.go/com.ss.android.ugc.aweme.main.homepage.MainActivity'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Launched TikTok Lite on all devices.", text_color="#28a745")

    def force_stop_tiktok_lite(self):
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Force stopping TikTok Lite on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'force-stop',
            'com.zhiliaoapp.musically.go'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Force stopped TikTok Lite on all devices.", text_color="#28a745")

    def open_youtube_deeplink(self):
        video_url = self.youtube_url_entry.get()
        if not video_url:
            self.status_label.configure(text="⚠️ Please enter a YouTube URL.", text_color="#ffc107")
            return

        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Opening YouTube video on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'start',
            '-a', 'android.intent.action.VIEW',
            '-d', f'"{video_url}"',
            'com.android.chrome/com.google.android.apps.chrome.Main'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Visited video on all devices.", text_color="#28a745")

    def launch_youtube(self):
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Launching YouTube on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'start',
            '-a', 'android.intent.action.VIEW',
            '-d', 'https://m.youtube.com/',
            'com.android.chrome/com.google.android.apps.chrome.Main'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Launched YouTube on all devices.", text_color="#28a745")

    def force_stop_youtube(self):
        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Force stopping YouTube on all devices...", text_color="#e0e0e0")

        command = [
            'shell', 'am', 'force-stop',
            'com.android.chrome'
        ]
        for device_serial in self.devices:
            self.executor.submit(run_adb_command, command, device_serial)
        self.status_label.configure(text="✅ Force stopped YouTube on all devices.", text_color="#28a745")

    def share_image_to_fb_lite(self):
        file_name = self.image_file_name_entry.get()
        if not file_name:
            self.status_label.configure(text="⚠️ Please enter the image filename.", text_color="#ffc107")
            return

        if not self.devices:
            self.status_label.configure(text="⚠️ No devices detected.", text_color="#ffc107")
            return

        self.status_label.configure(text=f"Sending sharing intent for '{file_name}' to all devices...",
                                    text_color="#e0e0e0")

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
        self.status_label.configure(text="✅ Image sharing command sent to all devices.", text_color="#28a745")

    def stop_all_commands(self):
        self.status_label.configure(text="Stopping all active commands...", text_color="#ffc107")
        is_stop_requested.set()

        self.executor.shutdown(wait=True)

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count() * 2)
        is_stop_requested.clear()

        self.status_label.configure(text="✅ All commands have been stopped.", text_color="#28a745")


if __name__ == '__main__':
    multiprocessing.freeze_support()
    app = AdbControllerApp()
    app.mainloop()
# ok


