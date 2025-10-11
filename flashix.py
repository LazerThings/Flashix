#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
import subprocess
import requests
import xml.etree.ElementTree as ET
import os
import sys
import platform
from pathlib import Path

FLASHIX_VERSION = "1.6"

class Flashix:
    def __init__(self, root, multiboot_mode=False):
        self.root = root
        self.multiboot_mode = multiboot_mode
        
        if multiboot_mode:
            self.root.title("Flashix - Experimental Multiboot")
        else:
            self.root.title("Flashix")
        
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
        self.reusable_isos = {}  # Maps display name to {path, url, filename}
        self.list_version = "0.0"
        self.is_flashing = False
        self.download_path = Path.home() / ".flashix_downloads"
        self.download_path.mkdir(exist_ok=True)
        
        # Multiboot-specific
        self.multiboot_initialized = False
        self.installed_isos = []  # List of installed ISO names
        
        # Custom ISO
        self.custom_iso_path = None
        
        if multiboot_mode:
            self.setup_multiboot_ui()
        else:
            self.setup_singleboot_ui()
        
        # Initial actions
        self.load_reusable_isos()
        self.detect_drives()
        self.refresh_os_list()
        
    def setup_singleboot_ui(self):
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
        self.delete_iso_checkbox = tk.Checkbutton(options_frame, text="Delete ISO after flashing", 
                      variable=self.delete_iso_var, font=("Arial", 9))
        self.delete_iso_checkbox.pack(anchor=tk.W)
        
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
        
        # Version label at bottom
        version_label = tk.Label(main_frame, text=f"Flashix v{FLASHIX_VERSION}", 
                                font=("Arial", 8), fg="#95a5a6")
        version_label.pack(pady=(5, 0))
        
    def setup_multiboot_ui(self):
        # Main content
        main_frame = tk.Frame(self.root, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # USB Drive selection
        drive_frame = tk.LabelFrame(main_frame, text="USB Drive", font=("Arial", 10, "bold"), padx=10, pady=10)
        drive_frame.pack(fill=tk.X, pady=(0, 10))
        
        drive_select_frame = tk.Frame(drive_frame)
        drive_select_frame.pack(fill=tk.X)
        
        self.drive_var = tk.StringVar()
        self.drive_combo = ttk.Combobox(drive_select_frame, textvariable=self.drive_var, 
                                        state="readonly", width=35)
        self.drive_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.drive_combo.bind('<<ComboboxSelected>>', self.check_multiboot_status)
        
        detect_btn = tk.Button(drive_select_frame, text="Detect Drives", command=self.detect_drives,
                              bg="#2ecc71", fg="white", relief=tk.FLAT, padx=10, cursor="hand2")
        detect_btn.pack(side=tk.LEFT)
        
        # Status and initialize
        status_frame = tk.Frame(drive_frame)
        status_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.status_label = tk.Label(status_frame, text="Status: Not initialized", 
                                     font=("Arial", 9), fg="#e74c3c")
        self.status_label.pack(anchor=tk.W)
        
        self.init_btn = tk.Button(drive_frame, text="Initialize as Multiboot Drive", 
                                 command=self.start_initialize_multiboot,
                                 bg="#e67e22", fg="white", relief=tk.FLAT, padx=10, cursor="hand2")
        self.init_btn.pack(fill=tk.X, pady=(5, 0))
        
        # Installed ISOs section
        installed_frame = tk.LabelFrame(main_frame, text="Installed ISOs", font=("Arial", 10, "bold"), 
                                       padx=10, pady=10)
        installed_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.installed_listbox = tk.Listbox(installed_frame, height=4, font=("Arial", 9))
        self.installed_listbox.pack(fill=tk.X)
        
        # Add ISO section
        add_frame = tk.LabelFrame(main_frame, text="Add ISO", font=("Arial", 10, "bold"), 
                                 padx=10, pady=10)
        add_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Category dropdown
        tk.Label(add_frame, text="Category:", font=("Arial", 9)).pack(anchor=tk.W, pady=(0, 2))
        self.category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(add_frame, textvariable=self.category_var, 
                                          state="readonly", width=58)
        self.category_combo.pack(fill=tk.X, pady=(0, 10))
        self.category_combo.bind('<<ComboboxSelected>>', self.on_category_selected)
        
        # Version dropdown
        tk.Label(add_frame, text="Version:", font=("Arial", 9)).pack(anchor=tk.W, pady=(0, 2))
        self.version_var = tk.StringVar()
        self.version_combo = ttk.Combobox(add_frame, textvariable=self.version_var, 
                                         state="readonly", width=58)
        self.version_combo.pack(fill=tk.X, pady=(0, 5))
        
        # List version and refresh
        list_info_frame = tk.Frame(add_frame)
        list_info_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.version_label = tk.Label(list_info_frame, text="List version: Not loaded", 
                                     font=("Arial", 9), fg="#7f8c8d")
        self.version_label.pack(side=tk.LEFT)
        
        refresh_btn = tk.Button(list_info_frame, text="Refresh List", command=self.refresh_os_list,
                               bg="#3498db", fg="white", relief=tk.FLAT, padx=10, cursor="hand2")
        refresh_btn.pack(side=tk.RIGHT)
        
        # Progress section
        progress_frame = tk.LabelFrame(main_frame, text="Progress", font=("Arial", 10, "bold"), 
                                      padx=10, pady=10)
        progress_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode='indeterminate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        
        self.log_text = scrolledtext.ScrolledText(progress_frame, height=8, font=("Courier", 9),
                                                  bg="#ecf0f1", state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Add ISO button
        self.add_iso_btn = tk.Button(main_frame, text="ADD ISO TO MULTIBOOT", 
                                     command=self.start_add_multiboot_iso,
                                     bg="#e74c3c", fg="white", font=("Arial", 14, "bold"), 
                                     relief=tk.FLAT, height=2, cursor="hand2", state=tk.DISABLED)
        self.add_iso_btn.pack(fill=tk.X)
        
        # Version label at bottom
        version_label = tk.Label(main_frame, text=f"Flashix v{FLASHIX_VERSION}", 
                                font=("Arial", 8), fg="#95a5a6")
        version_label.pack(pady=(5, 0))
        
    def log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
    def on_category_selected(self, event=None):
        category = self.category_var.get()
        
        # Check if Custom ISO
        if category == "Custom ISO":
            self.version_combo['values'] = []
            self.version_var.set("")
            self.version_combo.config(state=tk.DISABLED)
            
            # Gray out delete checkbox if in single-boot mode
            if not self.multiboot_mode:
                self.delete_iso_var.set(False)
                self.delete_iso_checkbox.config(state=tk.DISABLED)
            
            # Open file dialog
            file_path = filedialog.askopenfilename(
                title="Select Custom ISO",
                filetypes=[("ISO files", "*.iso"), ("All files", "*.*")]
            )
            
            if file_path:
                self.custom_iso_path = file_path
                self.log(f"Custom ISO selected: {Path(file_path).name}")
            else:
                self.custom_iso_path = None
                self.category_var.set("")
            
            return
        
        # Reset custom ISO path and enable checkbox
        self.custom_iso_path = None
        if not self.multiboot_mode:
            self.delete_iso_checkbox.config(state=tk.NORMAL)
        
        # Check if it's a cached ISO
        if category in self.reusable_isos:
            self.version_combo['values'] = []
            self.version_var.set("")
            self.version_combo.config(state=tk.DISABLED)
            return
        
        # Normal category from XML
        if category and category in self.os_data:
            versions = self.os_data[category]
            self.version_combo['values'] = versions
            self.version_combo.config(state="readonly")
            if versions:
                self.version_combo.current(0)
        else:
            self.version_combo['values'] = []
            self.version_combo.config(state="readonly")
        
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
                result = subprocess.run(['diskutil', 'list'], 
                                       capture_output=True, text=True)
                
                # Look for external disks
                for line in result.stdout.split('\n'):
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
                
                # Check multiboot status if in multiboot mode
                if self.multiboot_mode:
                    self.check_multiboot_status()
            else:
                self.drive_combo['values'] = []
                self.log("No USB drives detected")
        except Exception as e:
            self.log(f"Error detecting drives: {e}")
            messagebox.showerror("Error", f"Failed to detect drives:\n{e}")
            
    def load_reusable_isos(self):
        """Load cached ISOs from .reusable files"""
        try:
            reusable_files = list(self.download_path.glob("*.reusable"))
            
            for reusable_file in reusable_files:
                try:
                    with open(reusable_file, 'r') as f:
                        lines = f.read().strip().split('\n')
                        if len(lines) >= 3 and lines[0] == "declare flashix reusable file":
                            url = lines[1]
                            filename = lines[2]
                            iso_path = self.download_path / filename
                            
                            # Check if ISO still exists
                            if iso_path.exists():
                                # Extract category and version from filename
                                display_name = f"{filename[:-4]} (Cached)"
                                self.reusable_isos[display_name] = {
                                    'path': str(iso_path),
                                    'url': url,
                                    'filename': filename
                                }
                                self.log(f"Loaded cached ISO: {filename}")
                            else:
                                # Remove .reusable file if ISO doesn't exist
                                reusable_file.unlink()
                except Exception as e:
                    self.log(f"Error loading reusable file {reusable_file.name}: {e}")
        except Exception as e:
            self.log(f"Error scanning for reusable ISOs: {e}")
            
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
                
                # Build category list: Custom ISO + Cached ISOs + XML categories
                categories = ["Custom ISO"]
                categories.extend(list(self.reusable_isos.keys()))
                categories.extend(list(os_dict.keys()))
                
                self.category_combo['values'] = categories
                if categories:
                    self.category_combo.current(0)
                    self.on_category_selected()
                
                self.version_label.config(text=f"List version: {version}")
                total_os = sum(len(versions) for versions in os_dict.values())
                self.log(f"Loaded {len(os_dict)} categories, {total_os} OS options (version {version})")
            except Exception as e:
                self.log(f"Error fetching OS list: {e}")
                messagebox.showerror("Error", f"Failed to fetch OS list:\n{e}")
        
        threading.Thread(target=fetch, daemon=True).start()
        
    def check_multiboot_status(self, event=None):
        """Check if selected drive is initialized as multiboot"""
        if not self.drive_var.get():
            return
        
        drive = self.drive_var.get().split()[0]
        
        try:
            # Check if drive has multiboot structure
            if self.os_type == 'Darwin':
                result = subprocess.run(['diskutil', 'list', drive],
                                      capture_output=True, text=True)
                # Look for ESP and DATA partitions
                has_esp = 'EFI' in result.stdout
                has_data = 'FLASHIX_DATA' in result.stdout or 'DATA' in result.stdout
            else:
                result = subprocess.run(['lsblk', '-o', 'NAME,LABEL', drive],
                                      capture_output=True, text=True)
                has_esp = 'ESP' in result.stdout
                has_data = 'FLASHIX_DATA' in result.stdout
            
            if has_esp and has_data:
                self.multiboot_initialized = True
                self.status_label.config(text="Status: Initialized", fg="#2ecc71")
                self.add_iso_btn.config(state=tk.NORMAL)
                self.init_btn.config(state=tk.DISABLED)
                
                # Try to load installed ISOs
                self.load_installed_isos(drive)
            else:
                self.multiboot_initialized = False
                self.status_label.config(text="Status: Not initialized", fg="#e74c3c")
                self.add_iso_btn.config(state=tk.DISABLED)
                self.init_btn.config(state=tk.NORMAL)
                self.installed_listbox.delete(0, tk.END)
        except Exception as e:
            self.log(f"Error checking multiboot status: {e}")
            
    def load_installed_isos(self, drive):
        """Load list of installed ISOs from multiboot drive"""
        try:
            self.installed_listbox.delete(0, tk.END)
            # Try to mount and read entries
            # This is a simplified version - actual implementation would mount and read
            self.log("Checking installed ISOs...")
        except Exception as e:
            self.log(f"Error loading installed ISOs: {e}")
            
    def start_initialize_multiboot(self):
        if self.is_flashing:
            messagebox.showwarning("Warning", "Operation already in progress")
            return
            
        if not self.drive_var.get():
            messagebox.showerror("Error", "Please select a USB drive")
            return
        
        drive = self.drive_var.get().split()[0]
        
        confirm = messagebox.askyesno(
            "Confirm Initialize",
            f"WARNING: All data on {drive} will be erased!\n\n"
            f"This will initialize {drive} as a multiboot drive with:\n"
            f"- 512MB ESP partition for bootloader\n"
            f"- Remaining space for ISO storage\n\n"
            "Are you sure you want to continue?"
        )
        
        if not confirm:
            return
        
        self.is_flashing = True
        self.init_btn.config(state=tk.DISABLED)
        self.add_iso_btn.config(state=tk.DISABLED)
        self.progress_bar.start()
        
        threading.Thread(target=self.initialize_multiboot_process, args=(drive,), daemon=True).start()
        
    def initialize_multiboot_process(self, drive):
        try:
            self.log("Preparing initialization script...")
            script_path = self.download_path / 'flashix_init.sh'
            
            with open(script_path, 'w') as f:
                f.write('#!/bin/bash\n')
                f.write('set -e\n\n')
                
                if self.os_type == 'Darwin':
                    f.write(f'echo "Unmounting {drive}..."\n')
                    f.write(f'diskutil unmountDisk {drive}\n\n')
                    
                    f.write(f'echo "Creating partitions..."\n')
                    f.write(f'diskutil partitionDisk {drive} GPT fat32 ESP 512MB exfat DATA R\n\n')
                    
                    f.write(f'echo "Mounting ESP..."\n')
                    f.write('mkdir -p /tmp/flashix_esp\n')
                    f.write(f'mount -t msdos {drive}s1 /tmp/flashix_esp\n\n')
                    
                    f.write('echo "Installing systemd-boot..."\n')
                    f.write('mkdir -p /tmp/flashix_esp/EFI/systemd\n')
                    f.write('mkdir -p /tmp/flashix_esp/EFI/BOOT\n')
                    f.write('mkdir -p /tmp/flashix_esp/loader/entries\n\n')
                    
                    # Note: systemd-boot binaries would need to be bundled or downloaded
                    f.write('# systemd-boot installation would go here\n')
                    f.write('# For now, creating directory structure\n\n')
                    
                    f.write('cat > /tmp/flashix_esp/loader/loader.conf << EOF\n')
                    f.write('default @saved\n')
                    f.write('timeout 10\n')
                    f.write('console-mode max\n')
                    f.write('editor no\n')
                    f.write('EOF\n\n')
                    
                    f.write('echo "Setting volume label..."\n')
                    f.write(f'diskutil rename {drive}s2 FLASHIX_DATA\n\n')
                    
                    f.write('echo "Unmounting..."\n')
                    f.write('umount /tmp/flashix_esp\n')
                    
                else:  # Linux
                    f.write(f'echo "Unmounting {drive}..."\n')
                    f.write(f'umount {drive}* 2>/dev/null || true\n\n')
                    
                    f.write(f'echo "Creating partitions..."\n')
                    f.write(f'parted -s {drive} mklabel gpt\n')
                    f.write(f'parted -s {drive} mkpart ESP fat32 1MiB 513MiB\n')
                    f.write(f'parted -s {drive} set 1 esp on\n')
                    f.write(f'parted -s {drive} mkpart DATA exfat 513MiB 100%\n\n')
                    
                    f.write(f'echo "Formatting partitions..."\n')
                    f.write(f'mkfs.vfat -F32 {drive}1\n')
                    f.write(f'mkfs.exfat -n FLASHIX_DATA {drive}2\n\n')
                    
                    f.write('echo "Mounting ESP..."\n')
                    f.write('mkdir -p /tmp/flashix_esp\n')
                    f.write(f'mount {drive}1 /tmp/flashix_esp\n\n')
                    
                    f.write('echo "Installing systemd-boot..."\n')
                    f.write('bootctl install --esp-path=/tmp/flashix_esp\n\n')
                    
                    f.write('cat > /tmp/flashix_esp/loader/loader.conf << EOF\n')
                    f.write('default @saved\n')
                    f.write('timeout 10\n')
                    f.write('console-mode max\n')
                    f.write('editor no\n')
                    f.write('EOF\n\n')
                    
                    f.write('mkdir -p /tmp/flashix_esp/loader/entries\n\n')
                    
                    f.write('echo "Unmounting..."\n')
                    f.write('umount /tmp/flashix_esp\n')
                
                f.write('\necho "Initialization complete!"\n')
            
            os.chmod(script_path, 0o755)
            
            self.log("System authentication required...")
            self.log("")
            
            if self.os_type == 'Darwin':
                cmd = ['osascript', '-e', f'do shell script "{script_path}" with prompt "Flashix needs administrator permission to initialize multiboot drive." with administrator privileges']
            else:
                cmd = ['pkexec', str(script_path)]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            
            for line in process.stdout:
                self.log(line.strip())
            
            process.wait()
            
            if process.returncode != 0:
                raise Exception(f"Process failed with return code {process.returncode}")
            
            self.log("=" * 50)
            self.log("SUCCESS! Multiboot drive initialized.")
            
            if script_path.exists():
                script_path.unlink()
            
            messagebox.showinfo("Success", f"{drive} has been initialized as a multiboot drive!")
            
            # Update status
            self.check_multiboot_status()
            
        except Exception as e:
            self.log(f"ERROR: {e}")
            messagebox.showerror("Error", f"Initialization failed:\n{e}")
        finally:
            self.is_flashing = False
            self.init_btn.config(state=tk.NORMAL)
            self.progress_bar.stop()
            
    def start_add_multiboot_iso(self):
        if self.is_flashing:
            messagebox.showwarning("Warning", "Operation already in progress")
            return
            
        if not self.drive_var.get():
            messagebox.showerror("Error", "Please select a USB drive")
            return
            
        if not self.category_var.get():
            messagebox.showerror("Error", "Please select a category/OS")
            return
        
        category = self.category_var.get()
        
        # Handle different source types
        if category == "Custom ISO":
            if not self.custom_iso_path:
                messagebox.showerror("Error", "No custom ISO selected")
                return
            iso_source = self.custom_iso_path
            display_name = Path(self.custom_iso_path).stem
        elif category in self.reusable_isos:
            iso_source = self.reusable_isos[category]['path']
            display_name = category.replace(" (Cached)", "")
        else:
            if not self.version_var.get():
                messagebox.showerror("Error", "Please select a version")
                return
            version = self.version_var.get()
            display_name = f"{category} {version}"
            iso_source = None  # Will download
        
        drive = self.drive_var.get().split()[0]
        
        confirm = messagebox.askyesno(
            "Confirm Add ISO",
            f"Add the following ISO to multiboot drive {drive}?\n\n"
            f"ISO: {display_name}\n\n"
            "This will extract the ISO and add a boot entry."
        )
        
        if not confirm:
            return
        
        self.is_flashing = True
        self.add_iso_btn.config(state=tk.DISABLED)
        self.init_btn.config(state=tk.DISABLED)
        self.progress_bar.start()
        
        threading.Thread(target=self.add_multiboot_iso_process, 
                        args=(drive, category, iso_source, display_name), 
                        daemon=True).start()
        
    def add_multiboot_iso_process(self, drive, category, iso_source, display_name):
        try:
            # Determine ISO path
            if iso_source:
                # Custom or cached ISO
                iso_path = iso_source
            else:
                # Download from XML
                version = self.version_var.get()
                key = (category, version)
                os_info = self.os_details.get(key)
                
                if not os_info:
                    raise Exception("OS information not found")
                
                iso_filename = os_info['url'].split('/')[-1]
                iso_path = str(self.download_path / iso_filename)
            
            # Create entry name (sanitized)
            entry_name = display_name.lower().replace(' ', '-').replace('.', '-')
            
            self.log("Preparing multiboot add script...")
            script_path = self.download_path / 'flashix_add_iso.sh'
            
            with open(script_path, 'w') as f:
                f.write('#!/bin/bash\n')
                f.write('set -e\n\n')
                
                # Download if needed
                if not iso_source:
                    f.write(f'echo "Downloading {display_name}..."\n')
                    f.write(f'curl -L -o "{iso_path}" "{os_info["url"]}"\n')
                    f.write('echo "Download complete"\n\n')
                
                # Mount partitions
                if self.os_type == 'Darwin':
                    f.write('echo "Mounting partitions..."\n')
                    f.write('mkdir -p /tmp/flashix_esp /tmp/flashix_data\n')
                    f.write(f'mount -t msdos {drive}s1 /tmp/flashix_esp\n')
                    f.write(f'mount -t exfat {drive}s2 /tmp/flashix_data\n\n')
                else:
                    f.write('echo "Mounting partitions..."\n')
                    f.write('mkdir -p /tmp/flashix_esp /tmp/flashix_data\n')
                    f.write(f'mount {drive}1 /tmp/flashix_esp\n')
                    f.write(f'mount {drive}2 /tmp/flashix_data\n\n')
                
                # Extract ISO
                f.write(f'echo "Extracting ISO..."\n')
                f.write(f'mkdir -p /tmp/flashix_data/Extracted/{entry_name}\n')
                f.write('mkdir -p /tmp/flashix_iso\n')
                f.write(f'mount -o loop "{iso_path}" /tmp/flashix_iso\n')
                f.write(f'cp -r /tmp/flashix_iso/* /tmp/flashix_data/Extracted/{entry_name}/\n')
                f.write('umount /tmp/flashix_iso\n')
                f.write('echo "Extraction complete"\n\n')
                
                # Find EFI file
                f.write('echo "Creating boot entry..."\n')
                f.write(f'EFI_FILE=$(find /tmp/flashix_data/Extracted/{entry_name} -name "grubx64.efi" -o -name "bootx64.efi" | head -1)\n')
                f.write(f'if [ -z "$EFI_FILE" ]; then\n')
                f.write(f'    EFI_FILE=$(find /tmp/flashix_data/Extracted/{entry_name} -name "*.efi" | head -1)\n')
                f.write(f'fi\n')
                f.write(f'EFI_PATH=$(echo $EFI_FILE | sed "s|/tmp/flashix_data/Extracted/{entry_name}||")\n\n')
                
                # Create boot entry
                f.write(f'cat > /tmp/flashix_esp/loader/entries/{entry_name}.conf << EOF\n')
                f.write(f'title   {display_name}\n')
                f.write(f'efi     /Extracted/{entry_name}${{EFI_PATH}}\n')
                f.write('options root=LABEL=FLASHIX_DATA\n')
                f.write('EOF\n\n')
                
                # Unmount
                f.write('echo "Unmounting..."\n')
                f.write('umount /tmp/flashix_esp\n')
                f.write('umount /tmp/flashix_data\n\n')
                
                f.write('echo "Complete!"\n')
            
            os.chmod(script_path, 0o755)
            
            self.log("System authentication required...")
            self.log("")
            
            if self.os_type == 'Darwin':
                cmd = ['osascript', '-e', f'do shell script "{script_path}" with prompt "Flashix needs administrator permission to add ISO to multiboot drive." with administrator privileges']
            else:
                cmd = ['pkexec', str(script_path)]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            
            for line in process.stdout:
                self.log(line.strip())
            
            process.wait()
            
            if process.returncode != 0:
                raise Exception(f"Process failed with return code {process.returncode}")
            
            self.log("=" * 50)
            self.log(f"SUCCESS! {display_name} added to multiboot drive.")
            
            if script_path.exists():
                script_path.unlink()
            
            # Update installed ISOs list
            self.installed_listbox.insert(tk.END, display_name)
            
            messagebox.showinfo("Success", f"{display_name} has been added to the multiboot drive!")
            
        except Exception as e:
            self.log(f"ERROR: {e}")
            messagebox.showerror("Error", f"Adding ISO failed:\n{e}")
        finally:
            self.is_flashing = False
            self.add_iso_btn.config(state=tk.NORMAL)
            self.init_btn.config(state=tk.NORMAL if not self.multiboot_initialized else tk.DISABLED)
            self.progress_bar.stop()
        
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
        
        category = self.category_var.get()
        
        # Handle different source types
        if category == "Custom ISO":
            if not self.custom_iso_path:
                messagebox.showerror("Error", "No custom ISO selected")
                return
            iso_source = self.custom_iso_path
            display_name = Path(self.custom_iso_path).name
        elif category in self.reusable_isos:
            iso_source = self.reusable_isos[category]['path']
            display_name = category
        else:
            if not self.version_var.get():
                messagebox.showerror("Error", "Please select a version")
                return
            version = self.version_var.get()
            display_name = f"{category} - {version}"
            iso_source = None  # Will download
        
        drive = self.drive_var.get().split()[0]
        
        confirm = messagebox.askyesno(
            "Confirm Flash",
            f"WARNING: All data on {drive} will be erased!\n\n"
            f"OS: {display_name}\n"
            f"Drive: {drive}\n\n"
            "Are you sure you want to continue?"
        )
        
        if not confirm:
            return
        
        self.is_flashing = True
        self.flash_btn.config(state=tk.DISABLED)
        self.progress_bar.start()
        
        threading.Thread(target=self.flash_process, 
                        args=(drive, category, iso_source), 
                        daemon=True).start()
        
    def flash_process(self, drive, category, iso_source):
        try:
            # Determine ISO path and details
            if iso_source:
                # Custom or cached ISO
                iso_path = iso_source
                os_info = None
                version = None
            else:
                # Download from XML
                version = self.version_var.get()
                key = (category, version)
                os_info = self.os_details.get(key)
                
                if not os_info:
                    raise Exception("OS information not found")
                
                iso_filename = os_info['url'].split('/')[-1]
                iso_path = self.download_path / iso_filename
            
            # Create complete script
            self.log("Preparing flash script...")
            script_path = self.download_path / 'flashix_complete.sh'
            
            with open(script_path, 'w') as f:
                f.write('#!/bin/bash\n')
                f.write('set -e\n\n')
                
                # Download if needed
                if not iso_source:
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
                
                # Cleanup or create reusable marker
                if not iso_source:  # Only for downloaded ISOs
                    if self.delete_iso_var.get():
                        f.write(f'\necho "Cleaning up..."\n')
                        f.write(f'rm -f "{iso_path}"\n')
                    else:
                        # Create .reusable file
                        reusable_path = self.download_path / f".{Path(iso_path).name}.reusable"
                        f.write(f'\necho "Marking ISO as reusable..."\n')
                        f.write(f'cat > "{reusable_path}" << EOF\n')
                        f.write('declare flashix reusable file\n')
                        f.write(f'{os_info["url"]}\n')
                        f.write(f'{Path(iso_path).name}\n')
                        f.write('EOF\n')
                
                f.write('\necho "Complete!"\n')
            
            os.chmod(script_path, 0o755)
            
            self.log("System authentication required...")
            self.log("Please authenticate to begin download and flash process")
            self.log("")
            
            if self.os_type == 'Darwin':
                cmd = ['osascript', '-e', f'do shell script "{script_path}" with prompt "Flashix needs administrator permission to flash USB drives." with administrator privileges']
            else:
                cmd = ['pkexec', str(script_path)]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            
            for line in process.stdout:
                self.log(line.strip())
            
            process.wait()
            
            if process.returncode != 0:
                raise Exception(f"Process failed with return code {process.returncode}")
            
            self.log("=" * 50)
            self.log("SUCCESS! USB drive is ready to use.")
            
            if script_path.exists():
                script_path.unlink()
            
            display_text = Path(iso_source).name if iso_source else f"{category} - {version}"
            messagebox.showinfo("Success", f"{display_text} has been successfully flashed to {drive}!")
            
            # Reload reusable ISOs if we created one
            if not iso_source and not self.delete_iso_var.get():
                self.load_reusable_isos()
                self.refresh_os_list()
            
        except Exception as e:
            self.log(f"ERROR: {e}")
            messagebox.showerror("Error", f"Flashing failed:\n{e}")
        finally:
            self.is_flashing = False
            self.flash_btn.config(state=tk.NORMAL)
            self.progress_bar.stop()

if __name__ == "__main__":
    # Check for --multi argument
    multiboot_mode = '--multi' in sys.argv
    
    root = tk.Tk()
    app = Flashix(root, multiboot_mode=multiboot_mode)
    root.mainloop()