import customtkinter as ctk
import tkinter as tk
import threading
import time
import cv2
import numpy as np
import mss
import pytesseract
import colorsys
import os
import math
import random
import sys

# --- KONFIGURATION ---

if getattr(sys, 'frozen', False):
    application_path = sys._MEIPASS
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

tesseract_dir = os.path.join(application_path, 'Tesseract-OCR')
tesseract_path = os.path.join(tesseract_dir, 'tesseract.exe')

os.environ["TESSDATA_PREFIX"] = os.path.join(tesseract_dir, 'tessdata')

pytesseract.pytesseract.tesseract_cmd = tesseract_path

ctk.set_appearance_mode("dark")
APP_BG = "#050608"
PANEL_BG = "#0E1116"
NEON_CYAN = "#00FFCC"
WARN_ORANGE = "#F39C12"
SPIKE_THRESHOLD = 50000

class LogWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Terminal // URI_DEBUG")
        self.geometry("600x450")
        self.configure(fg_color="#000000")
        self.attributes("-topmost", True)
        
        self.textbox = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=12), text_color="#00FF41", fg_color="#000000")
        self.textbox.pack(fill="both", expand=True, padx=5, pady=5)
        self.textbox.configure(state="disabled")

    def update_log(self, history_list):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        for entry in reversed(history_list):
            self.textbox.insert("end", entry + "\n")
        self.textbox.configure(state="disabled")

class SnippingTool(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("UriMeter - Bereich")
        self.attributes("-alpha", 0.3)
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)
        self.configure(cursor="crosshair")
        
        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        self.start_x = None
        self.start_y = None
        self.rect = None
        
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

    def on_press(self, event):
        self.start_x = self.canvas.canvasx(event.x)
        self.start_y = self.canvas.canvasy(event.y)
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, 1, 1, outline=NEON_CYAN, width=2, fill="gray")

    def on_drag(self, event):
        cur_x, cur_y = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_release(self, event):
        end_x, end_y = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        
        left = int(min(self.start_x, end_x))
        top = int(min(self.start_y, end_y))
        width = int(abs(end_x - self.start_x))
        height = int(abs(end_y - self.start_y))
        
        self.parent.update_bounding_box({"top": top, "left": left, "width": width, "height": height})
        self.destroy()

class UriMeterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("UriMeter - Orbit")
        self.geometry("460x580") 
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.configure(fg_color=APP_BG)
        
        if not os.path.exists("debug_frames"):
            os.makedirs("debug_frames")
        
        # --- VARIABLEN ---
        self.is_running = False
        self.bounding_box = None
        self.ocr_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789'
        
        # Mathe & Logik
        self.last_uri = None
        self.total_uri_session = 0
        self.accumulated_time = 0.0
        self.current_start_time = 0.0
        self.consecutive_low_reads = 0
        self.consecutive_high_reads = 0 
        
        self.target_uri = 0
        
        self.debug_mode = tk.BooleanVar(value=False)
        self.log_history = []
        self.last_gain = 0
        self.log_window = None
        
        # Animations-Variablen
        self.hue = 0.0
        self.orbit_angle = 0.0
        
        self.build_ui()
        self.live_ui_update()
        self.animate_rgb_and_orbit()

    def build_ui(self):
        font_main = ctk.CTkFont(family="Consolas", size=14)
        font_digits = ctk.CTkFont(family="Consolas", size=38, weight="bold")
        font_tiny = ctk.CTkFont(family="Consolas", size=11)

        # --- MAIN PANEL ---
        self.main_frame = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=12, border_width=1, border_color="#1A202C")
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # --- CANVAS RENDER ---
        self.anim_canvas = tk.Canvas(self.main_frame, height=130, bg=PANEL_BG, highlightthickness=0)
        self.anim_canvas.pack(fill="x", pady=(10, 0))
        
        for _ in range(40):
            sx = random.randint(0, 420)
            sy = random.randint(0, 130)
            size = random.randint(1, 2)
            self.anim_canvas.create_oval(sx, sy, sx+size, sy+size, fill="#2C3E50", outline="")

        self.cx, self.cy = 210, 65 
        self.orbit_rx, self.orbit_ry = 120, 35 
        
        self.anim_canvas.create_oval(self.cx - self.orbit_rx, self.cy - self.orbit_ry, 
                                     self.cx + self.orbit_rx, self.cy + self.orbit_ry, 
                                     outline="#1A252F", width=2, dash=(4, 4))
        
        self.planet_glow = self.anim_canvas.create_oval(self.cx-20, self.cy-20, self.cx+20, self.cy+20, fill="", outline="#00FFCC", width=1)
        self.planet = self.anim_canvas.create_oval(self.cx-12, self.cy-12, self.cx+12, self.cy+12, fill=NEON_CYAN, outline="")
        self.title_text = self.anim_canvas.create_text(self.cx, self.cy + 45, text="U R I M E T E R", font=("Consolas", 18, "bold"), fill="#FFFFFF")
        
        self.satellite = self.anim_canvas.create_oval(0, 0, 8, 8, fill="#FFFFFF", outline="")

        self.coords_label = ctk.CTkLabel(self.main_frame, text="[ NO SIGNAL / NO TARGET ]", font=font_tiny, text_color="#555555")
        self.coords_label.pack(pady=(0, 10))

        # --- STATUS & UPTIME ---
        self.info_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.info_frame.pack(pady=5)
        
        self.status_label = ctk.CTkLabel(self.info_frame, text="STATUS: READY", font=font_main, text_color="#F39C12")
        self.status_label.grid(row=0, column=0, padx=10)
        
        self.runtime_label = ctk.CTkLabel(self.info_frame, text="UPTIME: 00:00:00", font=font_main, text_color="#A9CCE3")
        self.runtime_label.grid(row=0, column=1, padx=10)

        # --- CONTROLS ---
        self.button_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.button_frame.pack(pady=10)
        
        self.btn_start = ctk.CTkButton(self.button_frame, text="INITIATE", font=font_main, width=110, fg_color="#117A65", hover_color="#0B5345", command=self.start_scanner)
        self.btn_start.grid(row=0, column=0, padx=5)
        
        self.btn_stop = ctk.CTkButton(self.button_frame, text="HALT", font=font_main, width=110, fg_color="#922B21", hover_color="#641E16", command=self.stop_scanner)
        self.btn_stop.grid(row=0, column=1, padx=5)
        self.btn_stop.configure(state="disabled")
        
        self.btn_reset = ctk.CTkButton(self.button_frame, text="PURGE", font=font_main, width=110, fg_color="#2C3E50", hover_color="#1A252F", command=self.reset_stats)
        self.btn_reset.grid(row=0, column=2, padx=5)
        
        self.btn_lupe = ctk.CTkButton(self.button_frame, text="[+] CALIBRATE RADAR (SELECT AREA)", font=font_main, width=350, fg_color="transparent", border_width=1, border_color="#555555", text_color="white", hover_color="#1A252F", command=self.open_snipping_tool)
        self.btn_lupe.grid(row=1, column=0, columnspan=3, pady=(15, 5))
        
        # --- ETA TARGET ---
        self.target_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.target_frame.pack(pady=5)
        
        self.target_entry = ctk.CTkEntry(self.target_frame, font=font_main, placeholder_text="Set Target (e.g. 500k)", width=180, fg_color=APP_BG, border_color="#333333")
        self.target_entry.pack(side="left", padx=5)
        
        self.btn_set_target = ctk.CTkButton(self.target_frame, text="LOCK ETA", font=font_tiny, width=90, fg_color="#8E44AD", hover_color="#5B2C6F", command=self.set_target_uri)
        self.btn_set_target.pack(side="left", padx=5)

        # --- STATUS & DEBUG ---
        self.settings_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.settings_frame.pack(pady=10)
        
        self.chk_debug = ctk.CTkCheckBox(self.settings_frame, text="Paparazzi Debug", variable=self.debug_mode, command=self.toggle_debug_ui, font=font_tiny, fg_color=WARN_ORANGE, hover_color="#D35400")
        self.chk_debug.pack(side="left", padx=15)
        
        self.btn_show_log = ctk.CTkButton(self.settings_frame, text=">_ Terminal", font=font_tiny, width=90, fg_color="#2C3E50", hover_color="#1A252F", command=self.open_log_window)
        self.btn_show_log.pack(side="left", padx=15)
        
        # --- FOOTER ---
        self.footer_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.footer_frame.pack(side="bottom", fill="x", padx=10, pady=10)
        
        self.btn_compact = ctk.CTkButton(self.footer_frame, text="▼ COMPACT HUD", font=font_tiny, width=100, fg_color="transparent", text_color="#A9CCE3", hover_color="#1A252F", command=self.enable_compact_mode)
        self.btn_compact.pack(side="left")

        self.dev_label = ctk.CTkLabel(self.footer_frame, text="Dev: SunDiegoBBM", font=font_tiny)
        self.dev_label.pack(side="right")
        
        # --- COMPACT MODE HUD ---
        self.compact_frame = ctk.CTkFrame(self, fg_color=APP_BG, border_width=1, border_color="#1A202C", cursor="hand2")
        
        self.hud_top = ctk.CTkFrame(self.compact_frame, fg_color="transparent")
        self.hud_top.pack(fill="x", padx=10, pady=(5,0))
        
        self.compact_runtime_label = ctk.CTkLabel(self.hud_top, text="00:00:00", font=font_tiny, text_color="#555555")
        self.compact_runtime_label.pack(side="left")
        
        self.compact_status = ctk.CTkLabel(self.hud_top, text="● IDLE", font=font_tiny, text_color="#555555")
        self.compact_status.pack(side="right")

        self.compact_label_live = ctk.CTkLabel(self.compact_frame, text="0 Uri/h", font=font_digits, text_color="#FFFFFF")
        self.compact_label_live.pack(expand=True, pady=(0, 0))
        
        self.compact_debug_label = ctk.CTkLabel(self.compact_frame, text="Last: +0", font=font_tiny, text_color=WARN_ORANGE)

        self.compact_target_frame = ctk.CTkFrame(self.compact_frame, fg_color="transparent")
        self.compact_progress = ctk.CTkProgressBar(self.compact_target_frame, width=240, height=4, fg_color="#1A202C")
        self.compact_progress.set(0)
        self.compact_progress.pack(pady=(0, 2))
        
        self.compact_eta_label = ctk.CTkLabel(self.compact_target_frame, text="ETA: --:--:--", font=font_tiny, text_color="#888888")
        self.compact_eta_label.pack()

        self.compact_info_frame = ctk.CTkFrame(self.compact_frame, fg_color="transparent")
        self.compact_info_frame.pack(expand=True, fill="x", pady=(0, 5))
        
        self.compact_label_total = ctk.CTkLabel(self.compact_info_frame, text="Farm: 0", font=font_main, text_color="#A9CCE3")
        self.compact_label_total.pack(side="left", padx=15)
        
        self.compact_dev_label = ctk.CTkLabel(self.compact_info_frame, text="SunDiegoBBM", font=font_tiny)
        self.compact_dev_label.pack(side="right", padx=15)
        
        elements_to_bind = [self.compact_frame, self.compact_label_live, self.compact_debug_label, 
                            self.compact_label_total, self.compact_info_frame, self.compact_runtime_label, 
                            self.compact_dev_label, self.compact_target_frame, self.compact_eta_label, self.hud_top, self.compact_status]
        
        for elem in elements_to_bind:
            elem.bind("<Button-1>", self.disable_compact_mode)

    def set_target_uri(self):
        val = self.target_entry.get().strip().replace(".", "").replace(",", "")
        if val.isdigit() and int(val) > 0:
            self.target_uri = int(val)
            self.add_log(f"[*] ETA Target locked: {self.target_uri:,}".replace(",", "."))
            self.target_entry.configure(placeholder_text=f"Locked: {self.target_uri:,}".replace(",", "."))
            self.target_entry.delete(0, "end")
        else:
            self.target_uri = 0
            self.add_log("[!] Target reset.")

    def animate_rgb_and_orbit(self):
        self.hue += 0.005 
        if self.hue > 1.0:
            self.hue = 0.0
            
        r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(self.hue, 1.0, 1.0)]
        hex_color = f"#{r:02x}{g:02x}{b:02x}"
        
        self.anim_canvas.itemconfig(self.title_text, fill=hex_color)
        self.anim_canvas.itemconfig(self.planet, fill=hex_color)
        self.anim_canvas.itemconfig(self.planet_glow, outline=hex_color)
        
        self.dev_label.configure(text_color=hex_color)
        self.compact_dev_label.configure(text_color=hex_color)
        self.compact_progress.configure(progress_color=hex_color) 
        
        speed = 0.08 if self.is_running else 0.02 
        self.orbit_angle += speed
        
        sat_x = self.cx + self.orbit_rx * math.cos(self.orbit_angle)
        sat_y = self.cy + self.orbit_ry * math.sin(self.orbit_angle)
        self.anim_canvas.coords(self.satellite, sat_x-3, sat_y-3, sat_x+3, sat_y+3)
        self.anim_canvas.itemconfig(self.satellite, fill=hex_color)
        
        if self.is_running:
            self.main_frame.configure(border_color=hex_color)
            self.compact_frame.configure(border_color=hex_color)
            self.compact_status.configure(text="● TRACKING", text_color=hex_color)
            self.compact_label_live.configure(text_color="#FFFFFF")
        else:
            self.main_frame.configure(border_color="#1A202C")
            self.compact_frame.configure(border_color="#1A202C")
            self.compact_status.configure(text="● IDLE", text_color="#555555")
            self.compact_label_live.configure(text_color="#888888")
            
        self.after(40, self.animate_rgb_and_orbit) 
        
    def toggle_debug_ui(self):
        if self.debug_mode.get():
            self.add_log("--- PAPARAZZI MODE ON ---")
        else:
            self.add_log("--- PAPARAZZI MODE OFF ---")
        self.refresh_compact_layout()
            
    def refresh_compact_layout(self):
        self.compact_debug_label.pack_forget()
        self.compact_target_frame.pack_forget()
        self.compact_info_frame.pack_forget()
        
        target_height = 115 
        
        if self.debug_mode.get():
            self.compact_debug_label.pack(after=self.compact_label_live, pady=(0, 5))
            target_height += 20
            
        if self.target_uri > 0:
            self.compact_target_frame.pack(after=self.compact_debug_label if self.debug_mode.get() else self.compact_label_live, pady=(0, 5))
            target_height += 35
            
        self.compact_info_frame.pack(expand=True, fill="x", pady=(0, 5))
        
        if not self.main_frame.winfo_ismapped():
            self.geometry(f"290x{target_height}")
            
    def open_log_window(self):
        if self.log_window is None or not self.log_window.winfo_exists():
            self.log_window = LogWindow(self)
            self.log_window.update_log(self.log_history)
        else:
            self.log_window.focus()
            
    def add_log(self, message):
        if len(self.log_history) >= 200:
            self.log_history.pop(0) 
        self.log_history.append(message)
        
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.update_log(self.log_history)
    
    def open_snipping_tool(self):
        SnippingTool(self)
        
    def update_bounding_box(self, box):
        self.bounding_box = box
        self.coords_label.configure(text=f"[ RADAR LOCKED: {box['width']}x{box['height']}px ]", text_color=NEON_CYAN)
        self.btn_lupe.configure(border_color=NEON_CYAN)
        self.add_log(f"[*] Radar bounds: {box}")
        
    def start_scanner(self):
        if not self.bounding_box:
            self.coords_label.configure(text="[ ERROR: RADAR NOT CALIBRATED ]", text_color="red")
            return
            
        self.is_running = True
        self.current_start_time = time.time()
        
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_lupe.configure(state="disabled")
        
        self.add_log(f"[*] Engine STARTED")
        
        # NEUER CHECK FÜR DAS TERMINAL:
        if not os.path.exists(tesseract_path):
            self.add_log(f"[!] FATAL: Tesseract.exe nicht gefunden!")
            self.add_log(f"[!] Suchpfad: {tesseract_path}")
        
        threading.Thread(target=self.scanner_loop, daemon=True).start()

    def stop_scanner(self):
        self.is_running = False
        self.accumulated_time += (time.time() - self.current_start_time)
        
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.btn_lupe.configure(state="normal")
        self.add_log(f"[*] Engine HALTED")

    def reset_stats(self):
        self.total_uri_session = 0
        self.accumulated_time = 0.0
        self.consecutive_low_reads = 0
        self.consecutive_high_reads = 0
        self.last_gain = 0
        self.log_history.clear()
        
        if self.is_running:
            self.current_start_time = time.time()
        self.add_log("--- SYSTEM PURGED ---")
        
        self.compact_label_live.configure(text="0 Uri/h")
        self.compact_label_total.configure(text="Farm: 0")
        self.runtime_label.configure(text="UPTIME: 00:00:00")
        self.compact_runtime_label.configure(text="00:00:00")
        self.compact_debug_label.configure(text="Last: +0")
        self.compact_progress.set(0)
        self.compact_eta_label.configure(text="ETA: --:--:--", text_color="#888888")

    def enable_compact_mode(self):
        self.main_frame.pack_forget()
        self.refresh_compact_layout()
        self.compact_frame.pack(fill="both", expand=True)
        
    def disable_compact_mode(self, event=None):
        self.compact_frame.pack_forget()
        self.geometry("460x580")
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=20)

    def format_runtime(self, seconds):
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def live_ui_update(self):
        active_time = self.accumulated_time
        if self.is_running:
            active_time += (time.time() - self.current_start_time)
            
        current_rate_h = 0
        if active_time > 0:
            current_rate_h = int((self.total_uri_session / active_time) * 3600)

        formatted_live = f"{current_rate_h:,}".replace(",", ".")
        self.compact_label_live.configure(text=f"{formatted_live} Uri/h")
            
        formatted_total = f"{self.total_uri_session:,}".replace(",", ".")
        self.compact_label_total.configure(text=f"Farm: {formatted_total}")
        
        time_str = self.format_runtime(active_time)
        self.runtime_label.configure(text=f"UPTIME: {time_str}")
        self.compact_runtime_label.configure(text=time_str)
        
        if self.target_uri > 0:
            progress = min(self.total_uri_session / self.target_uri, 1.0)
            self.compact_progress.set(progress)
            
            if progress >= 1.0:
                self.compact_eta_label.configure(text="TARGET REACHED", text_color="#00FFCC")
            elif current_rate_h > 0:
                remaining_uri = self.target_uri - self.total_uri_session
                seconds_left = (remaining_uri / current_rate_h) * 3600
                eta_str = self.format_runtime(seconds_left)
                self.compact_eta_label.configure(text=f"ETA: {eta_str}", text_color="#888888")
            else:
                self.compact_eta_label.configure(text="ETA: ∞", text_color="#888888")
        
        if self.debug_mode.get():
            self.compact_debug_label.configure(text=f"Last: +{self.last_gain:,}".replace(",", "."))
        
        self.after(50, self.live_ui_update)

    def process_image(self, img_array):
        gray = cv2.cvtColor(img_array, cv2.COLOR_BGRA2GRAY)
        
        gray = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        inv = cv2.bitwise_not(thresh)
        contours, _ = cv2.findContours(inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if w < 25 and h < 25:
                cv2.drawContours(thresh, [c], -1, 255, -1)
                
        thresh = cv2.copyMakeBorder(thresh, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
        
        return thresh

    def scanner_loop(self):
        with mss.mss() as sct:
            while self.is_running:
                screenshot = np.array(sct.grab(self.bounding_box))
                processed_img = self.process_image(screenshot)
                
                raw_text = pytesseract.image_to_string(processed_img, config=self.ocr_config).strip()
                digits_only = ''.join(filter(str.isdigit, raw_text))
                t_stamp = time.strftime("%H:%M:%S")
                
                if digits_only:
                    current_uri = int(digits_only)
                    
                    if self.last_uri is None:
                        self.last_uri = current_uri
                        self.add_log(f"[{t_stamp}] BASE LOCKED: {current_uri}")
                    
                    elif current_uri != self.last_uri:
                        # --- DROPS / GHOST-SCAN DETECTED ---
                        if current_uri < self.last_uri:
                            self.consecutive_low_reads += 1
                            self.consecutive_high_reads = 0 
                            
                            drop_amount = self.last_uri - current_uri
                            
                            if self.debug_mode.get():
                                safe_raw = "".join([c for c in raw_text if c.isalnum() or c in ".-_"])
                                filename = f"debug_frames/drop_{t_stamp.replace(':', '-')}_Raw-{safe_raw}.png"
                                cv2.imwrite(filename, processed_img)
                                self.add_log(f"[{t_stamp}] DROP DETECTED. Image -> {filename}")
                            
                            # Drop bestätigt (4 Scans in Folge)
                            if self.consecutive_low_reads >= 4:
                                # --- BULLETPROOF UNDO LOGIK ---
                                if drop_amount > SPIKE_THRESHOLD and self.last_gain > SPIKE_THRESHOLD:
                                    self.add_log(f"[{t_stamp}] UNDO: Reverting fake spike (+{self.last_gain})!")
                                    # Fehlerhaften Gewinn vom Total abziehen
                                    self.total_uri_session = max(0, self.total_uri_session - self.last_gain)
                                    self.last_gain = 0
                                else:
                                    self.add_log(f"[{t_stamp}] DROP CONFIRMED. New Base: {current_uri}")
                                
                                self.last_uri = current_uri
                                self.consecutive_low_reads = 0
                                
                        # --- GAINS / SPIKES ---
                        elif current_uri > self.last_uri:
                            gain = current_uri - self.last_uri
                            
                            if gain > SPIKE_THRESHOLD:
                                self.consecutive_high_reads += 1
                                self.consecutive_low_reads = 0 
                                
                                if self.debug_mode.get():
                                    safe_raw = "".join([c for c in raw_text if c.isalnum() or c in ".-_"])
                                    filename = f"debug_frames/spike_{t_stamp.replace(':', '-')}_Raw-{safe_raw}.png"
                                    cv2.imwrite(filename, processed_img)
                                    self.add_log(f"[{t_stamp}] SPIKE WARNING (+{gain}). Wait {self.consecutive_high_reads}/4")
                                    
                                if self.consecutive_high_reads >= 4:
                                    self.add_log(f"[{t_stamp}] MASSIVE GAIN CONFIRMED: +{gain}")
                                    self.total_uri_session += gain
                                    self.last_gain = gain
                                    self.last_uri = current_uri
                                    self.consecutive_high_reads = 0
                            else:
                                self.add_log(f"[{t_stamp}] +{gain} Uri | Raw: '{raw_text}'")
                                self.total_uri_session += gain
                                self.last_gain = gain
                                self.last_uri = current_uri
                                self.consecutive_high_reads = 0
                                self.consecutive_low_reads = 0
                    else:
                        self.consecutive_low_reads = 0
                        self.consecutive_high_reads = 0
                
                time.sleep(0.5)

if __name__ == "__main__":
    app = UriMeterApp()
    app.mainloop()