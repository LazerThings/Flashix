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
import platform
from pathlib import Path

class Flashix:
    def __init__(self, root):
        self.root = root
        self.root.title("Flashix - USB ISO Flasher")
        self.root.geometry("700x900")
        self.root.resizable(False, False)
        
        # Detect operating system
        self.os_type = platform.system()  # 'Linux' or 'Darwin' (macOS)
        
        if self.os_type not in ['Linux', 'Darwin']:
            messagebox.showerror("Unsupported OS", 
                               f"Flashix only supports Linux and macOS.\nDetected: {self.os_type}")
            root.quit()
            return
        
        self.os_list_url = "https://raw.githubusercontent.com/LazerThings/Flashix/refs/heads/main/os-list.xml"
        self.os_data = {}  # Changed to dict: {category: [versions]}
        self.os_details = {}  # Maps (category, version) to {url, checksum, etc}
        self.list_version = "0.0"
        self.is_flashing = False
        self.download_path = Path.home() / ".flashix_downloads"
        self.download_path.mkdir(exist_ok=True)
        
        self.setup_ui()
        # No password prompt needed - will use system auth when needed
        
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
                               bg="#3498db", fg="white", relief=tk.FLAT, padx=10, cursor="hand2")
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
                              bg="#2ecc71", fg="white", relief=tk.FLAT, padx=10, cursor="hand2")
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
                                   relief=tk.FLAT, height=2, cursor="hand2")
        self.flash_btn.pack(fill=tk.X)
        
        # Initial actions
        self.detect_drives()
        self.refresh_os_list()
        
    def log(self, message):
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
            drives = []
            
            if self.os_type == 'Linux':
                # Linux: use lsblk
                result = subprocess.run(['lsblk', '-d', '-n', '-o', 'NAME,SIZE,TYPE'], 
                                      capture_output=True, text=True)
                for line in result.stdout.strip().split('\n'):
                    parts = line.split()
                    if len(parts) >= 3 and parts[2] == 'disk':
                        name = parts[0]
                        size = parts[1]
                        drives.append(f"/dev/{name} ({size})")
            
            elif self.os_type == 'Darwin':
                # macOS: use diskutil
                result = subprocess.run(['diskutil', 'list', '-plist'], 
                                      capture_output=True, text=True)
                
                # Parse diskutil output to find external disks
                result2 = subprocess.run(['diskutil', 'list'], 
                                       capture_output=True, text=True)
                
                # Look for external disks
                for line in result2.stdout.split('\n'):
                    if '/dev/disk' in line and 'external' in line.lower():
                        parts = line.split()
                        if parts:
                            disk_name = parts[0]
                            # Get size info
                            size_result = subprocess.run(['diskutil', 'info', disk_name],
                                                       capture_output=True, text=True)
                            size = "Unknown"
                            for size_line in size_result.stdout.split('\n'):
                                if 'Disk Size' in size_line or 'Total Size' in size_line:
                                    size_parts = size_line.split(':')
                                    if len(size_parts) > 1:
                                        size = size_parts[1].strip().split('(')[0].strip()
                                        break
                            drives.append(f"{disk_name} ({size})")
            
            if drives:
                self.drive_combo['values'] = drives
                self.drive_combo.current(0)
                self.log(f"Detected {len(drives)} drive(s)")
            else:
                self.drive_combo['values'] = []
                self.log("No USB drives detected")
        except Exception as e:
            self.log(f"Error detecting drives: {e}")
            messagebox.showerror("Error", f"Failed to detect drives:\n{e}")
            
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
            
            iso_filename = os_info['url'].split('/')[-1]
            iso_path = self.download_path / iso_filename
            
            # CREATE THE COMPLETE SCRIPT THAT DOES EVERYTHING
            self.log("Preparing flash script...")
            script_path = self.download_path / 'flashix_complete.sh'
            
            with open(script_path, 'w') as f:
                f.write('#!/bin/bash\n')
                f.write('set -e\n\n')
                
                # Download
                f.write(f'echo "Downloading {category} - {version}..."\n')
                f.write(f'curl -L -o "{iso_path}" "{os_info["url"]}"\n')
                f.write('echo "Download complete"\n\n')
                
                # Checksum verification if needed
                if self.verify_var.get() and os_info.get('checksum'):
                    f.write(f'echo "Verifying checksum..."\n')
                    checksum_type = os_info['checksum_type']
                    expected = os_info['checksum']
                    
                    if checksum_type == 'sha256':
                        hash_cmd = 'shasum -a 256' if self.os_type == 'Darwin' else 'sha256sum'
                    elif checksum_type == 'sha1':
                        hash_cmd = 'shasum -a 1' if self.os_type == 'Darwin' else 'sha1sum'
                    elif checksum_type == 'md5':
                        hash_cmd = 'md5' if self.os_type == 'Darwin' else 'md5sum'
                    else:
                        hash_cmd = f'{checksum_type}sum'
                    
                    f.write(f'CHECKSUM=$({hash_cmd} "{iso_path}" | awk \'{{print $1}}\')\n')
                    f.write(f'if [ "$CHECKSUM" != "{expected}" ]; then\n')
                    f.write(f'    echo "Checksum mismatch!"\n')
                    f.write(f'    exit 1\n')
                    f.write(f'fi\n')
                    f.write('echo "Checksum verified"\n\n')
                
                # Flash
                if self.os_type == 'Darwin':
                    f.write(f'echo "Unmounting {drive}..."\n')
                    f.write(f'diskutil unmountDisk {drive}\n')
                    f.write(f'echo "Flashing to {drive}..."\n')
                    f.write(f'dd if="{iso_path}" of={drive} bs=4m conv=fsync\n')
                else:
                    f.write(f'echo "Flashing to {drive}..."\n')
                    f.write(f'dd if="{iso_path}" of={drive} bs=4M status=progress conv=fsync\n')
                
                # Cleanup if requested
                if self.delete_iso_var.get():
                    f.write(f'\necho "Cleaning up..."\n')
                    f.write(f'rm -f "{iso_path}"\n')
                
                f.write('\necho "Complete!"\n')
            
            # Make script executable
            os.chmod(script_path, 0o755)
            
            # AUTHENTICATE AND RUN - ONE PROMPT RIGHT NOW
            self.log("System authentication required...")
            self.log("Please authenticate to begin download and flash process")
            self.log("")
            
            if self.os_type == 'Darwin':
                cmd = ['osascript', '-e', f'do shell script "{script_path}" with prompt "Flashix needs administrator permission to flash USB drives." with administrator privileges']
            else:
                cmd = ['pkexec', str(script_path)]
            
            # Run the authenticated script that does EVERYTHING
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            
            # Read output
            for line in process.stdout:
                self.log(line.strip())
            
            process.wait()
            
            if process.returncode != 0:
                raise Exception(f"Process failed with return code {process.returncode}")
            
            self.log("=" * 50)
            self.log("SUCCESS! USB drive is ready to use.")
            
            # Cleanup script
            if script_path.exists():
                script_path.unlink()
            
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