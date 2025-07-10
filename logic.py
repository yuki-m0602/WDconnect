import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import subprocess
import threading
import socket
import re
import os
import sys
from datetime import datetime
import json
import time
from config import load_config, save_config

class CompactWirelessDebugTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Android ワイヤレスデバッグツール - コンパクト版")
        
        # 変数の初期化
        self.adb_path = None
        self.selected_device = None
        self.config_file = "wireless_debug_config.json"
        
        # UIの設定
        self.setup_compact_ui()
        
        # 設定を読み込み
        self.load_config()
        
        # ADBの自動検索
        self.find_adb()

    def setup_compact_ui(self):
        """コンパクトなUIを設定"""
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # グリッドの重み設定
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(6, weight=1)
        
        # ADB設定セクション
        ttk.Label(main_frame, text="ADB設定:", font=("Arial", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))
        
        ttk.Label(main_frame, text="ADBパス:").grid(row=1, column=0, sticky=tk.W)
        self.adb_path_var = tk.StringVar()
        adb_entry = ttk.Entry(main_frame, textvariable=self.adb_path_var, width=30)
        adb_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(5, 0))
        
        adb_buttons_frame = ttk.Frame(main_frame)
        adb_buttons_frame.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(5, 10))
        ttk.Button(adb_buttons_frame, text="自動検索", command=self.find_adb).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(adb_buttons_frame, text="テスト", command=self.test_adb).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(adb_buttons_frame, text="デバイススキャン", command=self.scan_devices).pack(side=tk.LEFT)

        # デバイス管理セクション
        ttk.Label(main_frame, text="デバイス管理:", font=("Arial", 10, "bold")).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(10, 5))
        
        device_frame = ttk.Frame(main_frame)
        device_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        device_frame.columnconfigure(0, weight=1)
        
        ttk.Label(device_frame, text="デバイス:").grid(row=0, column=0, sticky=tk.W)
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(device_frame, textvariable=self.device_var, state="readonly", width=40)
        self.device_combo.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        self.device_combo.bind("<<ComboboxSelected>>", self.on_device_select)
        
        # ワイヤレスデバッグ設定
        ttk.Label(main_frame, text="ワイヤレスデバッグ設定:", font=("Arial", 10, "bold")).grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(10, 5))
        wireless_frame = ttk.Frame(main_frame)
        wireless_frame.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        wireless_frame.columnconfigure(1, weight=1)

        # IPアドレス選択（ラジオボタン）
        ttk.Label(wireless_frame, text="IPアドレス:").grid(row=0, column=0, sticky=tk.W)
        self.ip_var = tk.StringVar(value="192.168.0.")
        self.ip_last_var = tk.StringVar(value="100")
        
        ip_radio_frame = ttk.Frame(wireless_frame)
        ip_radio_frame.grid(row=0, column=1, sticky=tk.W, padx=(5, 0))
        
        # ラジオボタンを縦に並べる
        ttk.Radiobutton(ip_radio_frame, text="192.168.0.", variable=self.ip_var, value="192.168.0.").grid(row=0, column=0, sticky=tk.W)
        ttk.Radiobutton(ip_radio_frame, text="172.18.11.", variable=self.ip_var, value="172.18.11.").grid(row=1, column=0, sticky=tk.W)
        
        # 数値入力フォームをラジオボタンの右側（縦中央）に配置
        ip_last_entry = ttk.Entry(ip_radio_frame, textvariable=self.ip_last_var, width=8)
        ip_last_entry.grid(row=0, column=1, rowspan=2, sticky=tk.W, padx=(10, 0))

        ttk.Label(wireless_frame, text="ポート:").grid(row=0, column=2, sticky=tk.W, padx=(10, 0))
        self.port_var = tk.StringVar(value="5555")
        port_entry = ttk.Entry(wireless_frame, textvariable=self.port_var, width=8)
        port_entry.grid(row=0, column=3, sticky=tk.W, padx=(5, 0))

        connect_btn = ttk.Button(wireless_frame, text="接続", command=self.connect_device)
        connect_btn.grid(row=0, column=4, sticky=tk.W, padx=(10, 0))

        # ワイヤレス有効化・無効化・切断ボタンは従来通り下に
        wireless_buttons_frame = ttk.Frame(main_frame)
        wireless_buttons_frame.grid(row=7, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        ttk.Button(wireless_buttons_frame, text="ワイヤレス有効化", command=self.enable_wireless_debug).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(wireless_buttons_frame, text="ワイヤレス無効化", command=self.disable_wireless_debug).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(wireless_buttons_frame, text="切断", command=self.disconnect_device).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(wireless_buttons_frame, text="scrcpy起動", command=self.launch_scrcpy).pack(side=tk.LEFT, padx=(0, 5))

        # scrcpyパス設定セクション（ボタン群の下に移動）
        scrcpy_path_frame = ttk.Frame(main_frame)
        scrcpy_path_frame.grid(row=8, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        ttk.Label(scrcpy_path_frame, text="scrcpyパス:").pack(side=tk.LEFT)
        self.scrcpy_path_var = tk.StringVar()
        scrcpy_entry = ttk.Entry(scrcpy_path_frame, textvariable=self.scrcpy_path_var, width=30)
        scrcpy_entry.pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(scrcpy_path_frame, text="参照", command=self.browse_scrcpy).pack(side=tk.LEFT, padx=(5, 0))
        
        # ログ表示
        ttk.Label(main_frame, text="ログ:", font=("Arial", 10, "bold")).grid(row=9, column=0, columnspan=2, sticky=tk.W, pady=(10, 5))
        
        log_frame = ttk.Frame(main_frame)
        log_frame.grid(row=10, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=4, width=60)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        log_buttons_frame = ttk.Frame(main_frame)
        log_buttons_frame.grid(row=11, column=0, columnspan=2, sticky=tk.W)
        ttk.Button(log_buttons_frame, text="ログクリア", command=self.clear_log).pack(side=tk.LEFT)

    def on_device_select(self, event):
        """デバイス選択時の処理"""
        self.selected_device = self.device_var.get()
        if self.selected_device:
            self.log(f"デバイス選択: {self.selected_device}")
    
    def log(self, message):
        """ログメッセージを表示"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        
    def clear_log(self):
        """ログをクリア"""
        self.log_text.delete(1.0, tk.END)
        
    def find_adb(self):
        """ADBを自動検索"""
        self.log("ADBを検索中...")
        
        # 一般的なADBパスをチェック
        possible_paths = [
            "adb",
            "platform-tools/adb",
            "Android/Sdk/platform-tools/adb.exe",
            "AppData/Local/Android/Sdk/platform-tools/adb.exe",
            "Program Files/Android/Android Studio/Sdk/platform-tools/adb.exe",
            "Program Files (x86)/Android/Android Studio/Sdk/platform-tools/adb.exe"
        ]
        
        # 環境変数PATHから検索
        for path in os.environ.get('PATH', '').split(os.pathsep):
            if path:
                adb_path = os.path.join(path, 'adb.exe' if os.name == 'nt' else 'adb')
                if os.path.isfile(adb_path):
                    self.adb_path = adb_path
                    self.adb_path_var.set(adb_path)
                    self.log(f"ADB発見: {adb_path}")
                    return
        
        # 一般的なパスをチェック
        for path in possible_paths:
            if os.path.isfile(path):
                self.adb_path = path
                self.adb_path_var.set(path)
                self.log(f"ADB発見: {path}")
                return
        
        self.log("ADBが見つかりませんでした。手動でパスを設定してください。")
        
    def check_adb(self):
        """ADBが利用可能かチェック"""
        return self.adb_path and os.path.isfile(self.adb_path)
        
    def test_adb(self):
        """ADBのテスト"""
        if not self.check_adb():
            messagebox.showerror("エラー", "ADBが見つかりません。")
            return
            
        try:
            result = subprocess.run([self.adb_path, "version"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.log("ADBテスト成功")
                messagebox.showinfo("成功", "ADBが正常に動作しています。")
            else:
                self.log(f"ADBテスト失敗: {result.stderr}")
                messagebox.showerror("エラー", f"ADBテスト失敗: {result.stderr}")
        except Exception as e:
            self.log(f"ADBテストエラー: {e}")
            messagebox.showerror("エラー", f"ADBテストエラー: {e}")
            
    def scan_devices(self):
        """デバイスをスキャン"""
        if not self.check_adb():
            messagebox.showerror("エラー", "ADBが見つかりません。")
            return
            
        self.log("デバイスをスキャン中...")
        
        try:
            result = subprocess.run([self.adb_path, "devices"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.update_device_list(result.stdout)
            else:
                self.log(f"デバイススキャン失敗: {result.stderr}")
        except Exception as e:
            self.log(f"デバイススキャンエラー: {e}")
            
    def update_device_list(self, devices_output):
        """デバイスリストを更新"""
        devices = []
        lines = devices_output.strip().split('\n')
        
        for line in lines[1:]:  # 最初の行はヘッダー
            if line.strip() and '\t' in line:
                device_id, status = line.split('\t')
                if status == 'device':
                    devices.append(device_id)
                    
        if devices:
            self.device_combo['values'] = devices
            if devices:
                self.device_combo.set(devices[0])
            self.log(f"デバイス発見: {len(devices)}個")
        else:
            self.device_combo['values'] = []
            self.device_combo.set('')
            self.log("デバイスが見つかりませんでした。")

    def enable_wireless_debug(self):
        """ワイヤレスデバッグを有効化"""
        if not self.selected_device:
            messagebox.showerror("エラー", "デバイスを選択してください。")
            return
            
        if not self.check_adb():
            messagebox.showerror("エラー", "ADBが見つかりません。")
            return
            
        self.log(f"ワイヤレスデバッグを有効化中: {self.selected_device}")
        
        try:
            result = subprocess.run([self.adb_path, "-s", self.selected_device, "tcpip", "5555"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.log("ワイヤレスデバッグ有効化成功")
                messagebox.showinfo("成功", "ワイヤレスデバッグが有効化されました。")
            else:
                self.log(f"ワイヤレスデバッグ有効化失敗: {result.stderr}")
                messagebox.showerror("エラー", f"ワイヤレスデバッグ有効化失敗: {result.stderr}")
        except Exception as e:
            self.log(f"ワイヤレスデバッグ有効化エラー: {e}")
            messagebox.showerror("エラー", f"ワイヤレスデバッグ有効化エラー: {e}")
            
    def disable_wireless_debug(self):
        """ワイヤレスデバッグを無効化"""
        if not self.selected_device:
            messagebox.showerror("エラー", "デバイスを選択してください。")
            return
            
        if not self.check_adb():
            messagebox.showerror("エラー", "ADBが見つかりません。")
            return
            
        self.log(f"ワイヤレスデバッグを無効化中: {self.selected_device}")
        
        try:
            result = subprocess.run([self.adb_path, "-s", self.selected_device, "usb"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.log("ワイヤレスデバッグ無効化成功")
                messagebox.showinfo("成功", "ワイヤレスデバッグが無効化されました。")
            else:
                self.log(f"ワイヤレスデバッグ無効化失敗: {result.stderr}")
                messagebox.showerror("エラー", f"ワイヤレスデバッグ無効化失敗: {result.stderr}")
        except Exception as e:
            self.log(f"ワイヤレスデバッグ無効化エラー: {e}")
            messagebox.showerror("エラー", f"ワイヤレスデバッグ無効化エラー: {e}")
            
    def connect_device(self):
        """デバイスに接続"""
        ip_base = self.ip_var.get().strip()
        ip_last = self.ip_last_var.get().strip()
        port = self.port_var.get().strip()
        
        if not ip_base or not ip_last or not port:
            messagebox.showerror("エラー", "IPアドレスとポートを入力してください。")
            return
            
        if not self.check_adb():
            messagebox.showerror("エラー", "ADBが見つかりません。")
            return
            
        # 完全なIPアドレスを組み立て
        full_ip = f"{ip_base}{ip_last}"
        self.log(f"デバイスに接続中: {full_ip}:{port}")
        
        try:
            result = subprocess.run([self.adb_path, "connect", f"{full_ip}:{port}"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.log(f"接続結果: {result.stdout.strip()}")
                if "connected" in result.stdout.lower():
                    # 接続成功時に設定を保存
                    self.save_config()
                    messagebox.showinfo("成功", "デバイスに接続されました。")
                else:
                    messagebox.showwarning("警告", f"接続に失敗しました: {result.stdout.strip()}")
            else:
                self.log(f"接続失敗: {result.stderr}")
                messagebox.showerror("エラー", f"接続失敗: {result.stderr}")
        except Exception as e:
            self.log(f"接続エラー: {e}")
            messagebox.showerror("エラー", f"接続エラー: {e}")
            
    def disconnect_device(self):
        """デバイスを切断"""
        ip_base = self.ip_var.get().strip()
        ip_last = self.ip_last_var.get().strip()
        port = self.port_var.get().strip()
        
        if not ip_base or not ip_last or not port:
            messagebox.showerror("エラー", "IPアドレスとポートを入力してください。")
            return
            
        if not self.check_adb():
            messagebox.showerror("エラー", "ADBが見つかりません。")
            return
            
        # 完全なIPアドレスを組み立て
        full_ip = f"{ip_base}{ip_last}"
        self.log(f"デバイスを切断中: {full_ip}:{port}")
        
        try:
            result = subprocess.run([self.adb_path, "disconnect", f"{full_ip}:{port}"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.log(f"切断結果: {result.stdout.strip()}")
                messagebox.showinfo("成功", "デバイスが切断されました。")
            else:
                self.log(f"切断失敗: {result.stderr}")
                messagebox.showerror("エラー", f"切断失敗: {result.stderr}")
        except Exception as e:
            self.log(f"切断エラー: {e}")
            messagebox.showerror("エラー", f"切断エラー: {e}")
            
    def launch_scrcpy(self):
        """scrcpyを起動"""
        self.log("scrcpyを起動中...")
        
        scrcpy_path = self.scrcpy_path_var.get().strip()
        if not scrcpy_path:
            messagebox.showerror("エラー", "scrcpyのパスが設定されていません。")
            self.log("scrcpyのパスが未設定です")
            return
        if not os.path.isfile(scrcpy_path):
            messagebox.showerror("エラー", f"scrcpyのパスが正しくありません: {scrcpy_path}")
            self.log(f"scrcpyのパスが正しくありません: {scrcpy_path}")
            return
        try:
            # scrcpyを指定パスで起動
            subprocess.Popen([scrcpy_path], shell=True)
            self.log(f"scrcpy起動成功: {scrcpy_path}")
        except Exception as e:
            self.log(f"scrcpy起動エラー: {e}")
            messagebox.showerror("エラー", f"scrcpy起動エラー: {e}")

    def browse_scrcpy(self):
        """scrcpyのパスを参照"""
        scrcpy_path = filedialog.askopenfilename(
            title="scrcpyを選択",
            filetypes=[("scrcpy executable", "*.exe")]
        )
        if scrcpy_path:
            self.scrcpy_path_var.set(scrcpy_path)
            self.log(f"scrcpyパスを設定: {scrcpy_path}")
        else:
            self.log("scrcpyパスの選択がキャンセルされました。")

    # load_config, save_configはconfig.pyを使うように修正
    def load_config(self):
        config = load_config(self.config_file)
        if config:
            if 'ip_base' in config:
                self.ip_var.set(config['ip_base'])
            if 'ip_last' in config:
                self.ip_last_var.set(config['ip_last'])
            if 'scrcpy_path' in config:
                self.scrcpy_path_var.set(config['scrcpy_path'])
            self.log("設定を読み込みました")

    def save_config(self):
        config = {
            'ip_base': self.ip_var.get(),
            'ip_last': self.ip_last_var.get(),
            'scrcpy_path': self.scrcpy_path_var.get()
        }
        save_config(self.config_file, config)
        self.log("設定を保存しました") 