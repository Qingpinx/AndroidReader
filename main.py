import os
import json
import chardet
import threading
from docx import Document
from PyPDF2 import PdfReader
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.slider import Slider
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.checkbox import CheckBox
from kivy.core.window import Window
from kivy.clock import Clock
from plyer import tts, filechooser

# ========== 修复字体问题：改用系统必装字体+异常捕获 ==========
try:
    from kivy.core.text import LabelBase, DEFAULT_FONT

    # 方案1：使用Windows必装的宋体（simsun.ttf，几乎所有Windows都有）
    # 先尝试注册宋体，失败则跳过（不影响APP启动）
    LabelBase.register(DEFAULT_FONT, "simsun.ttf")
except:
    # 字体注册失败时不报错，优先保证APP能启动（仅桌面端乱码，安卓不受影响）
    pass

# 适配安卓窗口大小
Window.size = (400, 700)

# 全局常量
MAX_RECENT = 10


class ReaderLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.padding = 10
        self.spacing = 10

        # 全局变量
        self.current_file = ""
        self.content = ""
        self.is_speaking = False
        self.stop_flag = False
        self.recent_files = []
        self.last_pos = 0
        self.speak_rate = 0
        self.voice_type = "female"  # 默认女声

        # 修复：App实例化后初始化路径
        self.CONFIG_PATH = os.path.join(App.get_running_app().user_data_dir, ".dark_reader_android.json")

        # 1. 顶部标题栏（兼容字体配置）
        title = Label(
            text="专业暗黑离线朗读器",
            font_size=20,
            bold=True,
            color=(0.9, 0.9, 0.9, 1)
        )
        self.add_widget(title)

        # 2. 最近打开按钮
        self.recent_btn = Button(
            text="最近打开",
            size_hint=(1, 0.1),
            background_color=(0.18, 0.18, 0.18, 1),
            color=(0.9, 0.9, 0.9, 1)
        )
        self.recent_btn.bind(on_release=self.show_recent_popup)
        self.add_widget(self.recent_btn)

        # 3. 功能按钮栏
        btn_layout = BoxLayout(orientation="horizontal", size_hint=(1, 0.1), spacing=5)
        # 打开文件按钮
        self.open_btn = Button(
            text="打开文件",
            background_color=(0.25, 0.25, 0.25, 1),
            color=(0.9, 0.9, 0.9, 1)
        )
        self.open_btn.bind(on_release=self.open_file)
        # 重新加载按钮
        self.reload_btn = Button(
            text="重新加载",
            background_color=(0.25, 0.25, 0.25, 1),
            color=(0.9, 0.9, 0.9, 1)
        )
        self.reload_btn.bind(on_release=self.reload_file)
        # 关闭文件按钮
        self.close_btn = Button(
            text="关闭文件",
            background_color=(0.25, 0.25, 0.25, 1),
            color=(0.9, 0.9, 0.9, 1)
        )
        self.close_btn.bind(on_release=self.close_file)
        btn_layout.add_widget(self.open_btn)
        btn_layout.add_widget(self.reload_btn)
        btn_layout.add_widget(self.close_btn)
        self.add_widget(btn_layout)

        # 4. 朗读控制栏
        speak_layout = BoxLayout(orientation="horizontal", size_hint=(1, 0.1), spacing=5)
        # 从头朗读
        self.speak_all_btn = Button(
            text="从头朗读",
            background_color=(0.25, 0.25, 0.25, 1),
            color=(0.9, 0.9, 0.9, 1)
        )
        self.speak_all_btn.bind(on_release=self.speak_all)
        # 从光标读
        self.speak_cursor_btn = Button(
            text="从光标读",
            background_color=(0.25, 0.25, 0.25, 1),
            color=(0.9, 0.9, 0.9, 1)
        )
        self.speak_cursor_btn.bind(on_release=self.speak_from_cursor)
        # 停止朗读
        self.stop_btn = Button(
            text="停止朗读",
            background_color=(0.25, 0.25, 0.25, 1),
            color=(0.9, 0.9, 0.9, 1)
        )
        self.stop_btn.bind(on_release=self.stop_speak)
        speak_layout.add_widget(self.speak_all_btn)
        speak_layout.add_widget(self.speak_cursor_btn)
        speak_layout.add_widget(self.stop_btn)
        self.add_widget(speak_layout)

        # 5. 字号/语速/语音设置栏
        setting_layout = BoxLayout(orientation="horizontal", size_hint=(1, 0.15), spacing=5)
        # 字号标签
        setting_layout.add_widget(Label(
            text="字号",
            color=(0.9, 0.9, 0.9, 1)
        ))
        self.font_slider = Slider(min=12, max=28, value=16)
        self.font_slider.bind(value=self.update_font)
        setting_layout.add_widget(self.font_slider)
        # 语速标签
        setting_layout.add_widget(Label(
            text="语速",
            color=(0.9, 0.9, 0.9, 1)
        ))
        self.rate_slider = Slider(min=-10, max=10, value=0)
        self.rate_slider.bind(value=self.update_rate)
        setting_layout.add_widget(self.rate_slider)
        # 语音类型（CheckBox单选）
        voice_layout = BoxLayout(orientation="vertical")
        self.female_cb = CheckBox(active=True, group="voice")
        self.female_cb.bind(active=self.set_voice_female)
        female_layout = BoxLayout(orientation="horizontal")
        female_layout.add_widget(self.female_cb)
        female_layout.add_widget(Label(
            text="女声",
            color=(0.9, 0.9, 0.9, 1)
        ))
        voice_layout.add_widget(female_layout)
        self.male_cb = CheckBox(active=False, group="voice")
        self.male_cb.bind(active=self.set_voice_male)
        male_layout = BoxLayout(orientation="horizontal")
        male_layout.add_widget(self.male_cb)
        male_layout.add_widget(Label(
            text="男声",
            color=(0.9, 0.9, 0.9, 1)
        ))
        voice_layout.add_widget(male_layout)
        setting_layout.add_widget(voice_layout)
        self.add_widget(setting_layout)

        # 6. 文本显示区域
        self.text_input = TextInput(
            text="请打开文件开始阅读",
            font_size=16,
            size_hint=(1, 0.5),
            background_color=(0.12, 0.12, 0.12, 1),
            foreground_color=(0.9, 0.9, 0.9, 1),
            readonly=False,
            multiline=True
        )
        self.add_widget(self.text_input)

        # 初始化加载最近文件
        self.load_recent()

    # ========== 基础功能：语音类型/字号/语速 ==========
    def set_voice_female(self, instance, value):
        if value:
            self.voice_type = "female"
            self.male_cb.active = False

    def set_voice_male(self, instance, value):
        if value:
            self.voice_type = "male"
            self.female_cb.active = False

    def update_font(self, instance, value):
        self.text_input.font_size = value

    def update_rate(self, instance, value):
        self.speak_rate = value

    # ========== 核心功能：朗读控制 ==========
    def speak_all(self, instance):
        if not self.content:
            self.show_popup("提示", "请先打开文件")
            return
        self.start_speak(self.content, 0)

    def speak_from_cursor(self, instance):
        if not self.content:
            self.show_popup("提示", "请先打开文件")
            return
        pos = self.text_input.cursor_index()
        self.start_speak(self.content, pos)

    def start_speak(self, text, start_pos):
        self.stop_speak()
        self.stop_flag = False
        self.is_speaking = True
        threading.Thread(
            target=self.speak_worker,
            args=(text, start_pos),
            daemon=True
        ).start()

    def speak_worker(self, text, start_pos):
        lines = text.splitlines()
        current_pos = 0
        for line in lines:
            if self.stop_flag:
                break
            line_len = len(line) + 1
            if current_pos >= start_pos:
                if line.strip():
                    Clock.schedule_once(
                        lambda dt, s=current_pos, e=current_pos + line_len - 1: self.highlight_line(s, e))
                    try:
                        tts.speak(
                            text=line,
                            lang="zh_CN",
                            rate=self.speak_rate,
                            voice=self.voice_type
                        )
                    except:
                        pass
            current_pos += line_len
        self.is_speaking = False
        Clock.schedule_once(lambda dt: self.clear_highlight())

    def stop_speak(self, instance=None):
        self.stop_flag = True
        self.is_speaking = False
        try:
            tts.stop()
        except:
            pass
        Clock.schedule_once(lambda dt: self.clear_highlight(), 0.1)

    # ========== UI辅助：高亮/弹窗 ==========
    def highlight_line(self, start, end):
        self.text_input.select_text(start, end)
        self.text_input.scroll_y = 1 - (start / len(self.content))

    def clear_highlight(self):
        self.text_input.cancel_selection()

    def show_popup(self, title, content):
        # 弹窗兼容处理
        content_label = Label(
            text=content,
            color=(0.9, 0.9, 0.9, 1)
        )
        popup = Popup(
            title=title,
            content=content_label,
            size_hint=(0.8, 0.3)
        )
        popup.open()

    # ========== 文件操作：打开/加载/关闭 ==========
    def open_file(self, instance):
        try:
            filechooser.open_file(
                title="选择文件",
                filters=["*.txt", "*.pdf", "*.docx"],
                on_selection=self.on_file_selected
            )
        except:
            self.show_popup("提示", "文件选择器暂不可用（仅安卓端支持）")

    def on_file_selected(self, selection):
        if selection:
            path = selection[0]
            self.load_file(path)

    def load_file(self, path):
        try:
            if path.endswith(".txt"):
                with open(path, "rb") as f:
                    enc = chardet.detect(f.read())["encoding"] or "utf-8"
                with open(path, encoding=enc, errors="ignore") as f:
                    self.content = f.read()
            elif path.endswith(".docx"):
                self.content = "\n".join(p.text for p in Document(path).paragraphs)
            elif path.endswith(".pdf"):
                self.content = "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)

            self.current_file = path
            self.text_input.text = self.content
            self.add_recent(path)
            self.last_pos = self.load_last_pos(path)

            if int(self.last_pos) > 0:
                popup = Popup(
                    title="恢复位置",
                    size_hint=(0.8, 0.3),
                    auto_dismiss=False
                )
                # 弹窗内容
                content_layout = BoxLayout(orientation="vertical")
                content_layout.add_widget(Label(
                    text="是否从上次关闭处继续阅读？",
                    color=(0.9, 0.9, 0.9, 1)
                ))
                # 按钮布局
                btn_layout = BoxLayout(orientation="horizontal")
                confirm_btn = Button(
                    text="是",
                    size_hint=(0.5, 0.2),
                    color=(0.9, 0.9, 0.9, 1)
                )
                confirm_btn.bind(on_release=lambda x: self.restore_pos(popup))
                cancel_btn = Button(
                    text="否",
                    size_hint=(0.5, 0.2),
                    color=(0.9, 0.9, 0.9, 1)
                )
                cancel_btn.bind(on_release=lambda x: popup.dismiss())
                btn_layout.add_widget(confirm_btn)
                btn_layout.add_widget(cancel_btn)
                content_layout.add_widget(btn_layout)
                popup.content = content_layout
                popup.open()
        except Exception as e:
            self.show_popup("错误", f"文件读取失败：{str(e)}")

    def restore_pos(self, popup):
        self.text_input.cursor = self.text_input.get_cursor_from_index(int(self.last_pos))
        self.text_input.scroll_y = 1 - (int(self.last_pos) / len(self.content))
        popup.dismiss()

    def reload_file(self, instance):
        if self.current_file:
            self.load_file(self.current_file)

    def close_file(self, instance):
        self.stop_speak()
        self.save_last_pos()
        self.current_file = ""
        self.content = ""
        self.text_input.text = "请打开文件开始阅读"

    # ========== 最近文件：弹窗实现 ==========
    def add_recent(self, path):
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:MAX_RECENT]
        self.save_recent()

    def save_recent(self):
        try:
            with open(self.CONFIG_PATH + ".recent", "w", encoding="utf-8") as f:
                json.dump(self.recent_files, f)
        except:
            pass

    def load_recent(self):
        try:
            if os.path.exists(self.CONFIG_PATH + ".recent"):
                with open(self.CONFIG_PATH + ".recent", encoding="utf-8") as f:
                    self.recent_files = json.load(f)
        except:
            self.recent_files = []

    def show_recent_popup(self, instance):
        if not self.recent_files:
            self.show_popup("提示", "暂无最近打开的文件")
            return

        recent_layout = BoxLayout(orientation="vertical", spacing=5, padding=10)
        recent_layout.add_widget(Label(
            text="最近打开的文件",
            color=(0.9, 0.9, 0.9, 1),
            font_size=16
        ))

        for path in self.recent_files:
            file_name = os.path.basename(path)
            file_btn = Button(
                text=file_name,
                size_hint=(1, 0.15),
                background_color=(0.25, 0.25, 0.25, 1),
                color=(0.9, 0.9, 0.9, 1)
            )
            file_btn.bind(on_release=lambda x, p=path: self.load_file(p))
            recent_layout.add_widget(file_btn)

        close_btn = Button(
            text="关闭",
            size_hint=(1, 0.15),
            background_color=(0.3, 0.3, 0.3, 1),
            color=(0.9, 0.9, 0.9, 1)
        )
        recent_layout.add_widget(close_btn)

        self.recent_popup = Popup(
            title="最近打开",
            content=recent_layout,
            size_hint=(0.9, 0.7)
        )
        close_btn.bind(on_release=self.recent_popup.dismiss)
        self.recent_popup.open()

    # ========== 位置保存/加载 ==========
    def save_last_pos(self):
        if not self.current_file:
            return
        try:
            cfg = {}
            if os.path.exists(self.CONFIG_PATH):
                with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg[f"pos_{self.current_file}"] = self.text_input.cursor_index()
            with open(self.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f)
        except:
            pass

    def load_last_pos(self, path):
        try:
            if os.path.exists(self.CONFIG_PATH):
                with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                return int(cfg.get(f"pos_{path}", 0))
            return 0
        except:
            return 0


class ReaderApp(App):
    def build(self):
        self.title = "专业暗黑离线朗读器"
        Window.clearcolor = (0.08, 0.08, 0.08, 1)
        return ReaderLayout()

    def on_stop(self):
        self.root.save_last_pos()
        self.root.stop_speak()


if __name__ == "__main__":
    ReaderApp().run()