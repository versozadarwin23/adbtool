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


# --- Helper Functions (dapat nasa labas ng class) ---
def run_adb_command(command, serial):
    """
    Executes a single ADB command for a specific device with a timeout.
    """
    try:
        # Added a timeout to prevent commands from hanging indefinitely
        subprocess.run(['adb', '-s', serial] + command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=10)
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
    Sends a specific text string as a single ADB text command.
    """
    if not text_to_send:
        print(f"Text is empty. Cannot send command to {serial}.")
        return

    try:
        # Use a single command for the entire string
        command = ['shell', 'input', 'text', text_to_send.replace(' ', '%s')]
        run_adb_command(command, serial)
    except Exception as e:
        print(f"An error occurred on device {serial}: {e}")


# --- AdbControllerApp Class ---
class AdbControllerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Devices Controller By Dars V3")
        self.geometry("1366x768")
        self.state('zoomed')
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
        self.active_processes = []
        self.file_path_entry = None
        self.image_file_name_entry = None

        # Changed to a smaller ThreadPoolExecutor for better control over concurrent tasks
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count() * 2)

        # Configure main window grid
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- Control Panel Setup (Restored with Improvements) ---
        self.control_panel = ctk.CTkScrollableFrame(self, width=400, corner_radius=15, fg_color="#242424")
        self.control_panel.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.control_panel.grid_columnconfigure(0, weight=1)

        # Main Title
        ctk.CTkLabel(self.control_panel, text="Dars V3 Controller", font=ctk.CTkFont(size=30, weight="bold"),
                     text_color="#18a2ff").grid(
            row=0, column=0, pady=(20, 10), sticky='ew', padx=25)

        # Section Separator
        ctk.CTkFrame(self.control_panel, height=2, fg_color="#4a4a4a").grid(row=1, column=0, sticky='ew', padx=25,
                                                                            pady=15)

        # Device Section
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

        self.device_listbox = tk.Listbox(self.control_panel, height=6, font=("Segoe UI", 12),
                                         bg="#2a2a2a", fg="#e0e0e0", selectbackground="#1f6aa5",
                                         selectforeground="white", borderwidth=0, highlightthickness=0, relief='flat')
        self.device_listbox.grid(row=3, column=0, sticky='ew', padx=25, pady=(5, 20))
        self.device_listbox.bind('<<ListboxSelect>>', self.on_device_select)

        # Main TabView component
        self.tab_view = ctk.CTkTabview(self.control_panel, segmented_button_selected_color="#1f6aa5",
                                       segmented_button_selected_hover_color="#1a5585",
                                       segmented_button_unselected_hover_color="#3a3a3a",
                                       segmented_button_unselected_color="#2b2b2b",
                                       text_color="white",
                                       text_color_disabled="#8a8a8a",
                                       corner_radius=10)
        self.tab_view.grid(row=4, column=0, sticky="nsew", padx=25, pady=10)

        # Pinalitan ang mga pangalan ng tab para maging mas maikli at mas madaling basahin
        self.tab_view.add("FB Lite")
        self.tab_view.add("TikTok")
        self.tab_view.add("YouTube")
        self.tab_view.add("Text Cmd")
        self.tab_view.add("Image")
        self.tab_view.set("FB Lite")

        self._configure_tab_layouts()

        # Status label at the bottom
        self.status_label = ctk.CTkLabel(self.control_panel, text="", anchor='w', font=("Segoe UI", 14, "italic"))
        self.status_label.grid(row=5, column=0, sticky='ew', padx=25, pady=(10, 0))

        # Device View Panel (right side)
        self.device_view_panel = ctk.CTkFrame(self, fg_color="#1e1e1e", corner_radius=15)
        self.device_view_panel.grid(row=0, column=1, sticky="nsew", padx=(20, 20), pady=(20, 20))

        self.detect_devices()

    def on_closing(self):
        self.stop_capture()
        self.executor.shutdown(wait=False)
        self.destroy()

    def _configure_tab_layouts(self):
        """Helper method to configure the grid layout for each tab with improved spacing."""

        # Facebook Lite Tab
        fb_frame = self.tab_view.tab("FB Lite")
        fb_frame.columnconfigure(0, weight=1)
        fb_frame.rowconfigure(7, weight=1)

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

        self.stop_all_fb_button = ctk.CTkButton(fb_frame, text="Stop All Commands", command=self.stop_all_commands,
                                                fg_color="#ffc107", hover_color="#e0a800", text_color="#2b2b2b",
                                                corner_radius=8)
        self.stop_all_fb_button.grid(row=8, column=0, sticky='ew', padx=15, pady=(15, 5))

        # TikTok Tab
        tiktok_frame = self.tab_view.tab("TikTok")
        tiktok_frame.columnconfigure(0, weight=1)
        tiktok_frame.rowconfigure(5, weight=1)

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

        self.stop_all_tiktok_button = ctk.CTkButton(tiktok_frame, text="Stop All Commands",
                                                    command=self.stop_all_commands, fg_color="#ffc107",
                                                    hover_color="#e0a800", text_color="#2b2b2b", corner_radius=8)
        self.stop_all_tiktok_button.grid(row=4, column=0, sticky='ew', padx=15, pady=(15, 5))

        # YouTube Tab
        youtube_frame = self.tab_view.tab("YouTube")
        youtube_frame.columnconfigure(0, weight=1)
        youtube_frame.rowconfigure(5, weight=1)

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

        self.stop_all_youtube_button = ctk.CTkButton(youtube_frame, text="Stop All Commands",
                                                     command=self.stop_all_commands, fg_color="#ffc107",
                                                     hover_color="#e0a800", text_color="#2b2b2b", corner_radius=8)
        self.stop_all_youtube_button.grid(row=4, column=0, sticky='ew', padx=15, pady=(15, 5))

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

        self.stop_all_text_button = ctk.CTkButton(text_frame, text="Stop All Commands", command=self.stop_all_commands,
                                                  fg_color="#ffc107", hover_color="#e0a800", text_color="#2b2b2b",
                                                  corner_radius=8)
        self.stop_all_text_button.grid(row=4, column=0, sticky='ew', padx=15, pady=(15, 5))

        # Image Tab
        image_frame = self.tab_view.tab("Image")
        image_frame.columnconfigure(0, weight=1)
        image_frame.rowconfigure(4, weight=1)

        ctk.CTkLabel(image_frame, text="Photo Name (e.g., photo.jpg):", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky='w', pady=(15, 5), padx=15)
        self.image_file_name_entry = ctk.CTkEntry(image_frame, placeholder_text="Enter image name...", height=40,
                                                  corner_radius=8)
        self.image_file_name_entry.grid(row=1, column=0, sticky='ew', padx=15)
        self.share_image_button = ctk.CTkButton(image_frame, text="Share Image", command=self.share_image_to_fb_lite,
                                                fg_color="#42b72a", hover_color="#369720", height=45,
                                                font=ctk.CTkFont(weight="bold"))
        self.share_image_button.grid(row=2, column=0, sticky='ew', padx=15, pady=(10, 5))

        self.stop_all_image_button = ctk.CTkButton(image_frame, text="Stop All Commands",
                                                   command=self.stop_all_commands, fg_color="#ffc107",
                                                   hover_color="#e0a800", text_color="#2b2b2b", corner_radius=8)
        self.stop_all_image_button.grid(row=3, column=0, sticky='ew', padx=15, pady=(15, 5))

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
        # Increased refresh rate for better UI performance
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
            # Small delay to reduce CPU usage
            time.sleep(0.05)

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
        device_frame.pack(side=tk.LEFT, padx=10, pady=10, fill=tk.BOTH, expand=True)
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

    # --- New functions for TikTok Lite ---
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

    # --- New functions for YouTube ---
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

    # --- New Functions for Image Sharing with Manual Input ---
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
        self.status_label.configure(text="Stopping all active commands...", text_color="#e0e0e0")

        # Re-initialize the executor to stop all current tasks
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count() * 2)

        self.status_label.configure(text="✅ All commands have been stopped.", text_color="#28a745")


if __name__ == '__main__':
    multiprocessing.freeze_support()
    app = AdbControllerApp()
    app.mainloop()