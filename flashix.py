#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import subprocess
import requests
import xml.etree.ElementTree as ET
import os
import hashlib
import time
from pathlib import Path

class Flashix:
    def __init__(self, root):
        self.root = root
        self.root.title("Flashix - USB ISO Flasher")
        self.root.geometry("700x600")
        self.root.resizable(False, False)
        
        self.os_list_url = "https://raw.githubusercontent.com/YOUR_USERNAME/flashix-os-list/main/os-list.xml"
        self.os_data = {}  # Changed to dict: {category: [versions]}
        self.os_details = {}  # Maps (category, version) to {url, checksum, etc}
        self.list_version = "0.0"
        self.sudo_password = None
        self.is_flashing = False
        self.download_path = Path.home() / ".flashix_downloads"
        self.download_path.mkdir(exist_ok=True)
        
        self.setup_ui()
        self.get_sudo_password()
        
    def setup_ui(self):
        # Title
        title_frame = tk.Frame(self.root, bg="#2c3e50", height=60)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        tk.Label(title_frame, text="⚡ Flashix", font=("Arial", 24, "bold"), 
                bg="#2c3e50", fg="white").pack(pady=10)
        
        # Main content
        main_frame = tk.Frame(self.root, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # OS List section
        list_frame = tk.LabelFrame(main_frame, text="OS List", font=("Arial", 10, "bold"), padx=10, pady=10)
        list_frame.pack(fill=tk.X, pady=(0, 10))
        
        list_info_frame = tk.Frame(list_frame)
        list_info_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.version_label = tk.Label(list_info_frame, text="List version: Not loaded", 
                                     font=("Arial", 9), fg="#7f8c8d")
        self.version_label.pack(side=tk.LEFT)
        
        refresh_btn = tk.Button(list_info_frame, text="Refresh List", command=self.refresh_os_list,
                               bg="#3498db", fg="white", relief=tk.FLAT, padx=10)
        refresh_btn.pack(side=tk.RIGHT)
        
        # USB Drive selection
        drive_frame = tk.LabelFrame(main_frame, text="USB Drive", font=("Arial", 10, "bold"), padx=10, pady=10)
        drive_frame.pack(fill=tk.X, pady=(0, 10))
        
        drive_select_frame = tk.Frame(drive_frame)
        drive_select_frame.pack(fill=tk.X)
        
        self.drive_var = tk.StringVar()
        self.drive_combo = ttk.Combobox(drive_select_frame, textvariable=self.drive_var, 
                                        state="readonly", width=40)
        self.drive_combo.pack(side=tk.LEFT, padx=(0, 10))
        
        detect_btn = tk.Button(drive_select_frame, text="Detect Drives", command=self.detect_drives,
                              bg="#2ecc71", fg="white", relief=tk.FLAT, padx=10)
        detect_btn.pack(side=tk.LEFT)
        
        # OS selection
        os_frame = tk.LabelFrame(main_frame, text="Operating System", font=("Arial", 10, "bold"), 
                                padx=10, pady=10)
        os_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Category/OS dropdown
        tk.Label(os_frame, text="Category / OS:", font=("Arial", 9)).pack(anchor=tk.W, pady=(0, 2))
        self.category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(os_frame, textvariable=self.category_var, 
                                          state="readonly", width=58)
        self.category_combo.pack(fill=tk.X, pady=(0, 10))
        self.category_combo.bind('<<ComboboxSelected>>', self.on_category_selected)
        
        # Version dropdown
        tk.Label(os_frame, text="Version:", font=("Arial", 9)).pack(anchor=tk.W, pady=(0, 2))
        self.version_var = tk.StringVar()
        self.version_combo = ttk.Combobox(os_frame, textvariable=self.version_var, 
                                         state="readonly", width=58)
        self.version_combo.pack(fill=tk.X)
        
        # Options
        options_frame = tk.LabelFrame(main_frame, text="Options", font=("Arial", 10, "bold"), 
                                     padx=10, pady=10)
        options_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.delete_iso_var = tk.BooleanVar(value=True)
        tk.Checkbutton(options_frame, text="Delete ISO after flashing", 
                      variable=self.delete_iso_var, font=("Arial", 9)).pack(anchor=tk.W)
        
        self.verify_var = tk.BooleanVar(value=False)
        tk.Checkbutton(options_frame, text="Verify download (checksum)", 
                      variable=self.verify_var, font=("Arial", 9)).pack(anchor=tk.W)
        
        # Progress section
        progress_frame = tk.LabelFrame(main_frame, text="Progress", font=("Arial", 10, "bold"), 
                                      padx=10, pady=10)
        progress_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode='indeterminate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        
        self.log_text = scrolledtext.ScrolledText(progress_frame, height=8, font=("Courier", 9),
                                                  bg="#ecf0f1", state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Flash button
        self.flash_btn = tk.Button(main_frame, text="FLASH", command=self.start_flash,
                                   bg="#e74c3c", fg="white", font=("Arial", 14, "bold"), 
                                   relief=tk.FLAT, height=2)
        self.flash_btn.pack(fill=tk.X)
        
        # Initial actions
        self.detect_drives()
        self.refresh_os_list()
        
    def log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
    def get_sudo_password(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Sudo Password Required")
        dialog.geometry("400x150")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        frame = tk.Frame(dialog, padx=20, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(frame, text="Flashix requires sudo privileges to flash USB drives.", 
                font=("Arial", 10)).pack(pady=(0, 10))
        tk.Label(frame, text="Please enter your password:", 
                font=("Arial", 9)).pack(anchor=tk.W)
        
        password_var = tk.StringVar()
        password_entry = tk.Entry(frame, textvariable=password_var, show="*", width=40)
        password_entry.pack(fill=tk.X, pady=(5, 15))
        password_entry.focus()
        
        def submit():
            pwd = password_var.get()
            if not pwd:
                messagebox.showerror("Error", "Password cannot be empty")
                return
            
            # Test sudo password
            try:
                result = subprocess.run(
                    ['sudo', '-S', 'echo', 'test'],
                    input=f"{pwd}\n",
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    self.sudo_password = pwd
                    dialog.destroy()
                else:
                    messagebox.showerror("Error", "Incorrect password")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to verify password: {e}")
        
        def cancel():
            messagebox.showwarning("Warning", "Sudo password is required. Exiting.")
            self.root.quit()
        
        btn_frame = tk.Frame(frame)
        btn_frame.pack()
        
        tk.Button(btn_frame, text="Submit", command=submit, bg="#2ecc71", fg="white", 
                 relief=tk.FLAT, padx=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", command=cancel, bg="#95a5a6", fg="white", 
                 relief=tk.FLAT, padx=20).pack(side=tk.LEFT, padx=5)
        
        password_entry.bind('<Return>', lambda e: submit())
        
        dialog.wait_window()
    
    def on_category_selected(self, event=None):
        category = self.category_var.get()
        if category and category in self.os_data:
            versions = self.os_data[category]
            self.version_combo['values'] = versions
            if versions:
                self.version_combo.current(0)
        else:
            self.version_combo['values'] = []
        
    def detect_drives(self):
        try:
            result = subprocess.run(['lsblk', '-d', '-n', '-o', 'NAME,SIZE,TYPE'], 
                                  capture_output=True, text=True)
            drives = []
            for line in result.stdout.strip().split('\n'):
                parts = line.split()
                if len(parts) >= 3 and parts[2] == 'disk':
                    name = parts[0]
                    size = parts[1]
                    # Filter out likely system drives (very large ones)
                    drives.append(f"/dev/{name} ({size})")
            
            if drives:
                self.drive_combo['values'] = drives
                self.drive_combo.current(0)
                self.log(f"Detected {len(drives)} drive(s)")
            else:
                self.drive_combo['values'] = []
                self.log("No USB drives detected")
        except Exception as e:
            self.log(f"Error detecting drives: {e}")
            
    def refresh_os_list(self):
        def fetch():
            try:
                self.log("Fetching OS list...")
                response = requests.get(self.os_list_url, timeout=10)
                response.raise_for_status()
                
                root = ET.fromstring(response.content)
                version = root.get('version', '0.0')
                
                # Parse categories and versions
                os_dict = {}
                details = {}
                
                for category_elem in root.findall('category'):
                    category_name = category_elem.get('name')
                    versions = []
                    
                    for os_elem in category_elem.findall('os'):
                        version_name = os_elem.find('version').text
                        versions.append(version_name)
                        
                        # Store details for this category/version combination
                        key = (category_name, version_name)
                        details[key] = {
                            'url': os_elem.find('url').text,
                            'checksum': os_elem.find('checksum').text if os_elem.find('checksum') is not None else None,
                            'checksum_type': os_elem.find('checksum_type').text if os_elem.find('checksum_type') is not None else 'sha256'
                        }
                    
                    os_dict[category_name] = versions
                
                self.os_data = os_dict
                self.os_details = details
                self.list_version = version
                
                categories = list(os_dict.keys())
                self.category_combo['values'] = categories
                if categories:
                    self.category_combo.current(0)
                    self.on_category_selected()
                
                self.version_label.config(text=f"List version: {version}")
                total_os = sum(len(versions) for versions in os_dict.values())
                self.log(f"Loaded {len(categories)} categories, {total_os} OS options (version {version})")
            except Exception as e:
                self.log(f"Error fetching OS list: {e}")
                messagebox.showerror("Error", f"Failed to fetch OS list:\n{e}")
        
        threading.Thread(target=fetch, daemon=True).start()
        
    def start_flash(self):
        if self.is_flashing:
            messagebox.showwarning("Warning", "Already flashing in progress")
            return
            
        if not self.drive_var.get():
            messagebox.showerror("Error", "Please select a USB drive")
            return
            
        if not self.category_var.get():
            messagebox.showerror("Error", "Please select a category/OS")
            return
            
        if not self.version_var.get():
            messagebox.showerror("Error", "Please select a version")
            return
        
        drive = self.drive_var.get().split()[0]  # Extract /dev/sdX
        category = self.category_var.get()
        version = self.version_var.get()
        
        confirm = messagebox.askyesno(
            "Confirm Flash",
            f"WARNING: All data on {drive} will be erased!\n\n"
            f"OS: {category}\n"
            f"Version: {version}\n"
            f"Drive: {drive}\n\n"
            "Are you sure you want to continue?"
        )
        
        if not confirm:
            return
        
        self.is_flashing = True
        self.flash_btn.config(state=tk.DISABLED)
        self.progress_bar.start()
        
        threading.Thread(target=self.flash_process, args=(drive, category, version), daemon=True).start()
        
    def flash_process(self, drive, category, version):
        try:
            # Get OS details for this category/version
            key = (category, version)
            os_info = self.os_details.get(key)
            
            if not os_info:
                raise Exception("OS information not found")
            
            # Download ISO
            iso_filename = os_info['url'].split('/')[-1]
            iso_path = self.download_path / iso_filename
            
            self.log(f"Downloading {category} - {version}...")
            self.log(f"URL: {os_info['url']}")
            
            response = requests.get(os_info['url'], stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(iso_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            self.log(f"Progress: {percent:.1f}% ({downloaded // (1024*1024)}MB / {total_size // (1024*1024)}MB)")
            
            self.log(f"Download complete: {iso_path}")
            
            # Verify checksum if requested
            if self.verify_var.get() and os_info.get('checksum'):
                self.log(f"Verifying {os_info['checksum_type']} checksum...")
                hash_func = hashlib.new(os_info['checksum_type'])
                with open(iso_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(8192), b''):
                        hash_func.update(chunk)
                
                calculated = hash_func.hexdigest()
                expected = os_info['checksum'].lower()
                
                if calculated != expected:
                    raise Exception(f"Checksum mismatch!\nExpected: {expected}\nGot: {calculated}")
                
                self.log("Checksum verified ✓")
            
            # Flash to USB
            self.log(f"Flashing to {drive}...")
            self.log("This may take several minutes...")
            
            dd_command = [
                'sudo', '-S', 'dd',
                f'if={iso_path}',
                f'of={drive}',
                'bs=4M',
                'status=progress',
                'conv=fsync'
            ]
            
            process = subprocess.Popen(
                dd_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            
            # Send password
            process.stdin.write(f"{self.sudo_password}\n")
            process.stdin.flush()
            
            # Read output
            for line in process.stdout:
                self.log(line.strip())
            
            process.wait()
            
            if process.returncode != 0:
                raise Exception(f"Flashing failed with return code {process.returncode}")
            
            self.log("Flashing complete ✓")
            
            # Delete ISO if requested
            if self.delete_iso_var.get():
                self.log(f"Deleting {iso_filename}...")
                iso_path.unlink()
                self.log("ISO deleted ✓")
            else:
                self.log(f"ISO saved at: {iso_path}")
            
            self.log("=" * 50)
            self.log("SUCCESS! USB drive is ready to use.")
            
            messagebox.showinfo("Success", f"{category} - {version} has been successfully flashed to {drive}!")
            
        except Exception as e:
            self.log(f"ERROR: {e}")
            messagebox.showerror("Error", f"Flashing failed:\n{e}")
        finally:
            self.is_flashing = False
            self.flash_btn.config(state=tk.NORMAL)
            self.progress_bar.stop()
            
if __name__ == "__main__":
    root = tk.Tk()
    app = Flashix(root)
    root.mainloop()