# DisplayLayer.py
# Full TkDisplay implementation compatible with LibraryApp

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from PIL import Image, ImageTk

WINDOW_WIDTH, WINDOW_HEIGHT = 800, 480
FONT_SIZE_DEFAULT = 14
FONT_FAMILY_DEFAULT = "LiberationSerif"
PAGE_MARGIN = 16

class DisplayInterface:
    def clear(self):
        raise NotImplementedError

    def draw_text(self, text, apply_tags_fn):
        raise NotImplementedError

    def update_footer(self, chapter_text, page_number_text):
        raise NotImplementedError

    def focus(self):
        pass

class DisplayBase:
    """Abstract display interface for library and reader views."""
    def clear_container(self):
        raise NotImplementedError

    def show_library(self, library_items):
        raise NotImplementedError

    def move_selection(self, delta):
        raise NotImplementedError

    def get_selected_item(self):
        raise NotImplementedError

    def open_selected(self):
        raise NotImplementedError

    def show_reader(self, book_path):
        raise NotImplementedError

    def next_page(self):
        raise NotImplementedError

    def prev_page(self):
        raise NotImplementedError

    def load_chapter(self, chap):
        raise NotImplementedError

    def display_page(self):
        raise NotImplementedError

    # Modal-related
    def open_modal(self, options, selected_index):
        raise NotImplementedError

    def update_modal_selection(self, selected_index):
        raise NotImplementedError

    def close_modal(self):
        raise NotImplementedError


class TkDisplay(DisplayInterface, DisplayBase):
    def __init__(self, root, text_widget=None, page_label_widget=None, page_number_widget=None):
        self.root = root
        self.current_reader = None
        self.library_items = []
        self.selected_index = 0
        self._thumb_refs = []
        self.library_frame = None
        self.modal = None
        self.modal_var = None
        self.modal_buttons = []
        self.reader_text = None
        self.chapter_label = None
        self.page_label = None

        # For text display (reader view)
        self.text = text_widget
        self.page_label_widget = page_label_widget
        self.page_number_widget = page_number_widget

    # -----------------------------
    # Container
    # -----------------------------
    def clear_container(self):
        for w in self.root.winfo_children():
            w.destroy()
        self._thumb_refs.clear()
        self.library_frame = None
        self.reader_text = None
        self.chapter_label = None
        self.page_label = None
        self.modal = None
        self.modal_var = None
        self.modal_buttons = []
        self.current_reader = None

    # -----------------------------
    # Library
    # -----------------------------
    def show_library(self, library_items):
        self.clear_container()
        self.library_items = library_items
        self.selected_index = 0
        self._thumb_refs = []

        self.library_frame = tk.Frame(self.root)
        self.library_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(self.library_frame, bg="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.library_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        for epub_file, meta in self.library_items:
            frame = ttk.Frame(scrollable_frame, padding=8, style="TFrame")
            frame.pack(fill="x", pady=4)

            # Cover thumbnail
            if meta.get("cover_image"):
                try:
                    img = meta["cover_image"].copy()
                    img = img.convert("L").resize((60, 90))
                    img = img.convert("1")
                except Exception:
                    img = Image.new("1", (60, 90), 1)
            else:
                img = Image.new("1", (60, 90), 1)
            tk_img = ImageTk.PhotoImage(img)
            self._thumb_refs.append(tk_img)

            label_img = tk.Label(frame, image=tk_img, bg="white")
            label_img.pack(side="left", padx=(0, 10))
            label_img.image = tk_img

            info_text = f"{meta.get('title','Untitled')}\nby {meta.get('author','')}\n({meta.get('language','')})"
            label_text = tk.Label(frame, text=info_text, justify="left", bg="white", anchor="w")
            label_text.pack(side="left", fill="x", expand=True)

        self._highlight_selected()

    def _highlight_selected(self):
        if not self.library_items or not self.library_frame:
            return
        try:
            canvas = self.library_frame.winfo_children()[0]
            frames = canvas.winfo_children()[0].winfo_children()
            for i, f in enumerate(frames):
                f.configure(style="TFrame")
            frames[self.selected_index].configure(style="Selected.TFrame")
        except Exception:
            pass

    def move_selection(self, delta):
        if not self.library_items:
            return
        self.selected_index = (self.selected_index + delta) % len(self.library_items)
        self._highlight_selected()

    def get_selected_item(self):
        if not self.library_items:
            return None
        return self.library_items[self.selected_index]

    def open_selected(self):
        sel = self.get_selected_item()
        if sel:
            book_path, _ = sel
            return self.show_reader(book_path)
        return None

    # -----------------------------
    # Reader
    # -----------------------------
    def show_reader(self, book_path):
        self.clear_container()
        ext = str(book_path).lower()
        is_cbz = ext.endswith(".cbz")
        is_epub = ext.endswith(".epub")

        from cbz_reader_view import CBZReaderWindow
        from formatted_reader_view import ReaderWindow
        from ebooklib import epub

        if is_cbz:
            title_text = book_path.stem
            reader_frame = CBZReaderWindow(self.root, book_path)
            reader_frame.pack(fill="both", expand=True)
            self.current_reader = reader_frame
            return title_text

        try:
            book = epub.read_epub(book_path)
            title_md = book.get_metadata("DC", "title")
            title_text = title_md[0][0] if title_md else book_path.stem
        except Exception:
            title_text = book_path.stem

        reader_frame = ReaderWindow(self.root, book_path)
        reader_frame.pack(fill="both", expand=True)
        self.current_reader = reader_frame
        return title_text

    def next_page(self):
        if self.current_reader and hasattr(self.current_reader, "next_page"):
            self.current_reader.next_page()

    def prev_page(self):
        if self.current_reader and hasattr(self.current_reader, "prev_page"):
            self.current_reader.prev_page()

    def load_chapter(self, chap):
        if self.current_reader and hasattr(self.current_reader, "load_chapter"):
            self.current_reader.load_chapter(chap)

    def display_page(self):
        if self.current_reader and hasattr(self.current_reader, "display_page"):
            self.current_reader.display_page()

    # -----------------------------
    # Modal
    # -----------------------------
    def open_modal(self, options, selected_index):
        self.close_modal()
        self.modal = tk.Toplevel(self.root)
        self.modal.title("Options")
        self.modal_var = tk.IntVar(value=selected_index)

        self.modal_buttons = []
        for i, opt in enumerate(options):
            rb = tk.Radiobutton(self.modal, text=opt, variable=self.modal_var, value=i)
            rb.pack(anchor="w")
            self.modal_buttons.append(rb)

        btn = tk.Button(self.modal, text="Select", command=self.close_modal)
        btn.pack(pady=5)

    def update_modal_selection(self, selected_index):
        if self.modal_var:
            self.modal_var.set(selected_index)

    def close_modal(self):
        if self.modal:
            self.modal.destroy()
        self.modal = None
        self.modal_var = None
        self.modal_buttons = []

    # -----------------------------
    # Text display methods (for reader view)
    # -----------------------------
    def clear(self):
        try:
            self.text.config(state="normal")
            self.text.delete("1.0", tk.END)
        except Exception:
            pass

    def draw_text(self, text, apply_tags_fn):
        try:
            self.text.config(state="normal")
            self.text.delete("1.0", tk.END)
            self.text.insert("1.0", text)
            try:
                apply_tags_fn(self.text)
            except Exception:
                pass
            self.text.config(state="disabled")
        except Exception:
            pass

    def update_footer(self, chapter_text, page_number_text):
        try:
            if self.page_label_widget:
                self.page_label_widget.config(text=chapter_text)
            if self.page_number_widget:
                self.page_number_widget.config(text=page_number_text)
        except Exception:
            pass

    def focus(self):
        try:
            self.text.focus_set()
        except Exception:
            pass
