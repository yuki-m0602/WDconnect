import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import subprocess
import threading
import re
from datetime import datetime
import platform

class LightLogcatWidget:
    def __init__(self, parent, adb_path=None, device_id=None):
        self.parent = parent
        self.adb_path = adb_path
        self.device_id = device_id
        self.logcat_process = None
        self.is_running = False
        
        # UI要素
        self.log_text = None
        self.level_combo = None
        self.search_entry = None
        self.exclude_entry = None
        self.start_button = None
        self.stop_button = None
        self.clear_button = None
        
        # フィルター設定
        self.current_level = "INFO"
        self.search_text = ""
        self.exclude_text = ""
        
        # パフォーマンス最適化用（Android Studio風）
        self.log_buffer = []
        self.buffer_size = 30   # 30行ごとにバッチ処理（Android Studio風）
        self.max_lines = 300    # 最大300行まで表示（軽量化）
        self.update_timer = None
        self.update_interval = 50   # 50ms間隔で更新（Android Studio風）
        self.pending_updates = 0
        self.ring_buffer = []   # リングバッファ
        self.ring_buffer_size = 1000  # リングバッファサイズ
        
        # テーマ設定（Android Studio風）
        self.current_theme = "android_studio"
        self.themes = {
            "android_studio": {
                "bg": "#2b2b2b",  # Android Studioのダークテーマ背景
                "fg": "#a9b7c6",  # Android Studioのデフォルト文字色
                "row_bg_1": "#2b2b2b",  # 奇数行背景
                "row_bg_2": "#3c3f41",  # 偶数行背景（Android Studio風）
                "colors": {
                    "VERBOSE": "#808080",  # グレー
                    "DEBUG": "#6897bb",    # ブルーグレー
                    "INFO": "#a9b7c6",     # ライトグレー
                    "WARN": "#ffc66d",     # オレンジ
                    "ERROR": "#bc3f3c",    # レッド
                    "FATAL": "#ff6b68"     # ライトレッド
                }
            },
            "android_studio_light": {
                "bg": "#ffffff",  # ライトテーマ背景
                "fg": "#2b2b2b",  # ダークグレー
                "row_bg_1": "#ffffff",  # 奇数行背景
                "row_bg_2": "#f5f5f5",  # 偶数行背景（Android Studio風）
                "colors": {
                    "VERBOSE": "#808080",  # グレー
                    "DEBUG": "#6897bb",    # ブルーグレー
                    "INFO": "#2b2b2b",     # ダークグレー
                    "WARN": "#ffc66d",     # オレンジ
                    "ERROR": "#bc3f3c",    # レッド
                    "FATAL": "#ff6b68"     # ライトレッド
                }
            },
            "dark": {
                "bg": "#2b2b2b",
                "fg": "#ffffff",
                "row_bg_1": "#2b2b2b",
                "row_bg_2": "#3c3f41",
                "colors": {
                    "VERBOSE": "#888888",
                    "DEBUG": "#87ceeb",
                    "INFO": "#ffffff",
                    "WARN": "#ffa500",
                    "ERROR": "#ff6b6b",
                    "FATAL": "#ff0000"
                }
            },
            "green": {
                "bg": "#0c0c0c",
                "fg": "#00ff00",
                "row_bg_1": "#0c0c0c",
                "row_bg_2": "#1a1a1a",
                "colors": {
                    "VERBOSE": "#666666",
                    "DEBUG": "#00cc00",
                    "INFO": "#00ff00",
                    "WARN": "#ffff00",
                    "ERROR": "#ff0000",
                    "FATAL": "#ff6666"
                }
            }
        }
        
        # ログ行カウンター（行背景色用）
        self.log_line_count = 0
        self.row_alternate = True  # 行の交互色フラグ
        
        self.setup_ui()
        
    def setup_ui(self):
        """軽量なログキャットUIを設定"""
        # メインフレーム
        main_frame = ttk.LabelFrame(self.parent, text="Light Logcat", padding="5")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # コントロールフレーム
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 5))
        
        # 左側のコントロール
        left_control = ttk.Frame(control_frame)
        left_control.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # ログレベル選択
        ttk.Label(left_control, text="レベル:").pack(side=tk.LEFT)
        self.level_combo = ttk.Combobox(left_control, values=["VERBOSE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"], 
                                       state="readonly", width=10)
        self.level_combo.set("INFO")
        self.level_combo.pack(side=tk.LEFT, padx=(5, 10))
        self.level_combo.bind("<<ComboboxSelected>>", self.on_level_change)
        
        # 検索ボックス
        ttk.Label(left_control, text="検索:").pack(side=tk.LEFT)
        self.search_entry = ttk.Entry(left_control, width=20)
        self.search_entry.pack(side=tk.LEFT, padx=(5, 10))
        self.search_entry.bind("<KeyRelease>", self.on_search_change)
        
        # 除外ワードボックス
        ttk.Label(left_control, text="除外:").pack(side=tk.LEFT)
        self.exclude_entry = ttk.Entry(left_control, width=20)
        self.exclude_entry.pack(side=tk.LEFT, padx=(5, 10))
        self.exclude_entry.bind("<KeyRelease>", self.on_exclude_change)
        
        # 右側のボタン
        right_control = ttk.Frame(control_frame)
        right_control.pack(side=tk.RIGHT)
        
        # テーマ選択（Android Studio風）
        ttk.Label(right_control, text="テーマ:").pack(side=tk.LEFT, padx=(0, 5))
        self.theme_combo = ttk.Combobox(right_control, values=["android_studio", "android_studio_light", "dark", "green"], 
                                       state="readonly", width=15)
        self.theme_combo.set("android_studio")
        self.theme_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.theme_combo.bind("<<ComboboxSelected>>", self.on_theme_change)
        
        self.start_button = ttk.Button(right_control, text="開始", command=self.start_logcat)
        self.start_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.stop_button = ttk.Button(right_control, text="停止", command=self.stop_logcat, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.clear_button = ttk.Button(right_control, text="クリア", command=self.clear_log)
        self.clear_button.pack(side=tk.LEFT)
        
        # ログ表示エリア
        log_frame = ttk.Frame(main_frame)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        # スクロール可能なテキストウィジェット（Android Studio風）
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=80, 
                                                font=("Consolas", 9), wrap=tk.NONE,
                                                undo=False, maxundo=0,  # undo機能を無効化
                                                selectbackground="#214283",  # Android Studio風の選択色
                                                selectforeground="#ffffff")   # 選択時の文字色
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 色設定
        self.setup_colors()
        
    def setup_colors(self):
        """ログレベルの色を設定"""
        self.apply_theme(self.current_theme)
        
    def apply_theme(self, theme_name):
        """テーマを適用"""
        if theme_name not in self.themes:
            return
            
        self.current_theme = theme_name
        theme = self.themes[theme_name]
        
        # テキストウィジェットの背景色と文字色を設定
        self.log_text.configure(
            background=theme["bg"],
            foreground=theme["fg"],
            insertbackground=theme["fg"]  # カーソル色
        )
        
        # ログレベルの色を設定
        colors = theme["colors"]
        self.log_text.tag_configure("VERBOSE", foreground=colors["VERBOSE"])
        self.log_text.tag_configure("DEBUG", foreground=colors["DEBUG"])
        self.log_text.tag_configure("INFO", foreground=colors["INFO"])
        self.log_text.tag_configure("WARN", foreground=colors["WARN"])
        self.log_text.tag_configure("ERROR", foreground=colors["ERROR"])
        self.log_text.tag_configure("FATAL", foreground=colors["FATAL"])
        
        # 行背景色のタグを設定
        self.log_text.tag_configure("row_bg_1", background=theme["row_bg_1"])
        self.log_text.tag_configure("row_bg_2", background=theme["row_bg_2"])
        
        # 既存のログに色を再適用
        self.reapply_colors()
        
    def set_adb_path(self, adb_path):
        """ADBパスを設定"""
        self.adb_path = adb_path
        
    def set_device_id(self, device_id):
        """デバイスIDを設定"""
        self.device_id = device_id
        
    def start_logcat(self):
        """logcatを開始"""
        if not self.adb_path:
            self.add_log("エラー: ADBパスが設定されていません", "ERROR")
            return
            
        if not self.device_id:
            self.add_log("エラー: デバイスが選択されていません", "ERROR")
            return
            
        if self.is_running:
            self.add_log("logcatは既に実行中です", "WARN")
            return
            
        self.is_running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        
        # 別スレッドでlogcatを実行
        self.logcat_thread = threading.Thread(target=self._run_logcat, daemon=True)
        self.logcat_thread.start()
        
        self.add_log("logcatを開始しました", "INFO")
        
    def stop_logcat(self):
        """logcatを停止"""
        if not self.is_running:
            return
            
        self.is_running = False
        
        # 残りのバッファを処理
        if self.log_buffer:
            self._update_ui()
        
        if self.logcat_process:
            try:
                self.logcat_process.terminate()
                self.logcat_process.wait(timeout=5)
            except:
                self.logcat_process.kill()
            finally:
                self.logcat_process = None
                
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.add_log("logcatを停止しました", "INFO")
        
    def _run_logcat(self):
        """logcatを実行（別スレッド）"""
        try:
            # logcatコマンドを構築
            cmd = [self.adb_path, "-s", self.device_id, "logcat"]
            
            # ログレベルを追加
            level = self.current_level
            if level:
                cmd.extend([level + ":*"])
                
            # Windowsでコマンドラインウィンドウを表示しないようにする
            if platform.system() == "Windows":
                self.logcat_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    bufsize=1,
                    universal_newlines=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                self.logcat_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    bufsize=1,
                    universal_newlines=True
                )
            
            # ログを読み取り
            for line in self.logcat_process.stdout:
                if not self.is_running:
                    break
                    
                try:
                    # バッファに追加
                    self._add_to_buffer(line)
                except UnicodeDecodeError:
                    # エンコーディングエラーの場合は置換文字で処理
                    safe_line = line.encode('utf-8', errors='replace').decode('utf-8')
                    self._add_to_buffer(safe_line)
                
        except Exception as e:
            self.parent.after(0, self.add_log, f"logcatエラー: {e}", "ERROR")
            self.parent.after(0, self.stop_logcat)
            
    def _parse_log_level(self, line):
        """ログレベルを解析し、フル表記で返す"""
        # 1文字→フル表記変換辞書
        level_map = {
            'V': 'VERBOSE',
            'D': 'DEBUG',
            'I': 'INFO',
            'W': 'WARN',
            'E': 'ERROR',
            'F': 'FATAL',
        }
        # 例: "E/SomeTag" や "W/SomeTag" など
        m = re.match(r'([VDIWEF])/[^:]+', line)
        if m:
            return level_map.get(m.group(1), 'INFO')
        # 例: "VERBOSE", "DEBUG" などフル表記
        for lv in level_map.values():
            if lv in line:
                return lv
        return "INFO"  # デフォルト

    def _add_to_buffer(self, line):
        """ログをバッファに追加"""
        if not self.is_running:
            return
            
        try:
            # エラー行は無視
            if "[エラー] ログ行の処理に失敗" in line:
                return
                
            # エンコーディングエラーを防ぐため、安全に処理
            if isinstance(line, bytes):
                line = line.decode('utf-8', errors='replace')
            elif not isinstance(line, str):
                line = str(line)
                
            # 空行は無視
            if not line.strip():
                return
                
            # 除外ワードフィルターをチェック（高速化）
            if self.exclude_text:
                line_lower = line.lower()
                exclude_words = [word.strip() for word in self.exclude_text.split(',') if word.strip()]
                for word in exclude_words:
                    if word.lower() in line_lower:
                        return  # 除外ワードが含まれている場合は表示しない
                        
            # 検索フィルターをチェック（高速化）
            if self.search_text:
                if self.search_text.lower() not in line.lower():
                    return
                
            # ログレベルを解析
            level = self._parse_log_level(line)
            if not level:
                return
                
            # レベルフィルタ
            level_order = ['VERBOSE', 'DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL']
            try:
                if level_order.index(level) < level_order.index(self.current_level):
                    return
            except ValueError:
                return
                
            # タイムスタンプを追加（Android Studio風）
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # ミリ秒まで表示
            formatted_line = f"[{timestamp}] {line.rstrip()}\n"
            
            # 行背景色を決定（交互に色を変える）
            row_bg_tag = "row_bg_1" if self.row_alternate else "row_bg_2"
            self.row_alternate = not self.row_alternate
            
            # リングバッファに追加
            self.ring_buffer.append((formatted_line, level, row_bg_tag))
            if len(self.ring_buffer) > self.ring_buffer_size:
                self.ring_buffer.pop(0)  # 古いログを削除
                
            # バッファに追加
            self.log_buffer.append((formatted_line, level, row_bg_tag))
            
            # バッファサイズに達したらUI更新をスケジュール
            if len(self.log_buffer) >= self.buffer_size:
                self._schedule_update()
            # または一定時間経過したら更新
            elif self.pending_updates == 0:
                self._schedule_update()
                
        except Exception:
            # 例外時は何もせずスキップ
            return
            
    def _schedule_update(self):
        """UI更新をスケジュール"""
        if self.update_timer is None:
            self.pending_updates += 1
            self.update_timer = self.parent.after(self.update_interval, self._update_ui)
            
    def _update_ui(self):
        """UIを一括更新"""
        if not self.is_running:
            self.update_timer = None
            self.pending_updates = 0
            return
            
        try:
            # バッファが空の場合は何もしない
            if not self.log_buffer:
                self.update_timer = None
                self.pending_updates = 0
                return
                
            # バッファの内容を一括で追加（行背景色付き）
            text_to_add = ""
            start_line = int(self.log_text.index("end-1c").split('.')[0])
            current_line = start_line
            
            for formatted_line, level, row_bg_tag in self.log_buffer:
                text_to_add += formatted_line
                
            # 一括でテキストを追加
            if text_to_add:
                self.log_text.insert(tk.END, text_to_add)
                
                # 行背景色を適用
                for formatted_line, level, row_bg_tag in self.log_buffer:
                    line_start = f"{current_line}.0"
                    line_end = f"{current_line}.end"
                    self.log_text.tag_add(row_bg_tag, line_start, line_end)
                    self.log_text.tag_add(level, line_start, line_end)
                    current_line += 1
                
            # スクロール（最後に一度だけ）
            self.log_text.see(tk.END)
            
            # バッファをクリア
            self.log_buffer.clear()
            
            # ログが多すぎる場合は古いものを削除（Android Studio風）
            lines = int(self.log_text.index("end-1c").split('.')[0])
            if lines > self.max_lines:
                # 古いログを削除（一度に削除）
                delete_lines = lines - self.max_lines + 50
                if delete_lines > 0:
                    self.log_text.delete("1.0", f"{delete_lines}.0")
                
        except Exception as e:
            # エラーが発生した場合はバッファをクリア
            self.log_buffer.clear()
            print(f"ログ更新エラー: {e}")
            
        finally:
            self.update_timer = None
            self.pending_updates = 0
        
    def on_level_change(self, event=None):
        """ログレベル変更時の処理"""
        self.current_level = self.level_combo.get()
        if self.is_running:
            self.stop_logcat()
            self.start_logcat()
        
    def on_search_change(self, event=None):
        """検索テキスト変更時の処理"""
        self.search_text = self.search_entry.get().strip()
        
    def on_exclude_change(self, event=None):
        """除外ワード変更時の処理"""
        self.exclude_text = self.exclude_entry.get().strip()
        
    def on_theme_change(self, event=None):
        """テーマ変更時の処理"""
        new_theme = self.theme_combo.get()
        if new_theme != self.current_theme:
            self.apply_theme(new_theme)
            
    def reapply_colors(self):
        """既存のログに色を再適用（行背景色付き）"""
        try:
            # 既存のタグを削除
            for tag in ["VERBOSE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL", "row_bg_1", "row_bg_2"]:
                self.log_text.tag_remove(tag, "1.0", tk.END)
            
            # 各行を再解析して色を適用
            content = self.log_text.get("1.0", tk.END)
            lines = content.split('\n')
            
            line_num = 1
            row_alternate = True
            for line in lines:
                if line.strip():
                    level = self._parse_log_line_for_color(line)
                    if level:
                        start = f"{line_num}.0"
                        end = f"{line_num}.end"
                        # 行背景色を適用
                        row_bg_tag = "row_bg_1" if row_alternate else "row_bg_2"
                        self.log_text.tag_add(row_bg_tag, start, end)
                        self.log_text.tag_add(level, start, end)
                        row_alternate = not row_alternate
                line_num += 1
        except Exception:
            # エラーが発生した場合は何もしない
            pass
            
    def _parse_log_line_for_color(self, line):
        """色適用用のログレベル解析"""
        # 既にタイムスタンプが付いている行からレベルを抽出
        level_map = {
            'V': 'VERBOSE',
            'D': 'DEBUG', 
            'I': 'INFO',
            'W': 'WARN',
            'E': 'ERROR',
            'F': 'FATAL',
        }
        
        # 例: "[12:34:56] E/SomeTag" や "[12:34:56] W/SomeTag" など
        m = re.search(r'([VDIWEF])/[^:]+', line)
        if m:
            return level_map.get(m.group(1), 'INFO')
            
        # フル表記の検索
        for lv in level_map.values():
            if lv in line:
                return lv
                
        return "INFO"
        
    def add_log(self, message, level="INFO"):
        """ログメッセージを追加（Android Studio風）"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # ミリ秒まで表示
        formatted_message = f"[{timestamp}] {message}\n"
        
        self.log_text.insert(tk.END, formatted_message)
        self.log_text.see(tk.END)
        
        # 色を適用
        start = self.log_text.index("end-2c linestart")
        end = self.log_text.index("end-1c")
        self.log_text.tag_add(level, start, end)
        
    def clear_log(self):
        """ログをクリア"""
        self.log_text.delete(1.0, tk.END)
        # バッファもクリア
        self.log_buffer.clear()
        self.ring_buffer.clear()
        self.row_alternate = True  # 行背景色をリセット
        if self.update_timer:
            self.parent.after_cancel(self.update_timer)
            self.update_timer = None
            self.pending_updates = 0
        
    def destroy(self):
        """ウィジェットを破棄"""
        self.stop_logcat()
        if hasattr(self, 'log_text'):
            self.log_text.destroy() 