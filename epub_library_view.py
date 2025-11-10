import tkinter as tk
from tkinter import ttk
from ebooklib import epub
from pathlib import Path
from PIL import Image, ImageTk
import io
from formatted_reader_view import ReaderWindow
from rotary_encoder import RotaryEncoder
import time

# ---------- CONFIG ----------
EBOOKS_DIR = Path("ebooks")
COVERS_DIR = Path("covers")
WINDOW_WIDTH, WINDOW_HEIGHT = 480, 800
PAGE_MARGIN = 16

# ---------- UTILITIES ----------
def get_epub_metadata(epub_path):
    book = epub.read_epub(epub_path)
    metadata = {
        "title": "Untitled",
        "author": "Unknown",
        "language": "",
        "cover_image": None,
    }

    title = book.get_metadata("DC", "title")
    author = book.get_metadata("DC", "creator")
    lang = book.get_metadata("DC", "language")

    if title:
        metadata["title"] = title[0][0]
    if author:
        metadata["author"] = author[0][0]
    if lang:
        metadata["language"] = lang[0][0]

    for item in book.get_items():
        if hasattr(item, "media_type") and item.media_type.startswith("image/"):
            if "cover" in item.get_name().lower():
                try:
                    metadata["cover_image"] = Image.open(io.BytesIO(item.get_content()))
                except Exception:
                    pass
                break

    return metadata


def load_library():
    COVERS_DIR.mkdir(exist_ok=True)
    library = []
    for epub_file in sorted(EBOOKS_DIR.glob("*.epub")):
        try:
            data = get_epub_metadata(epub_file)
            library.append((epub_file, data))
        except Exception as e:
            print(f"Error reading {epub_file}: {e}")
    return library


# ---------- GUI ----------
class LibraryApp(tk.Tk):
    def __init__(self):
        self._last_action_time = 0
        self._debounce_delay = 0.3
        super().__init__()
        self.title("E-Book Library")
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.configure(bg="white")

        self.container = tk.Frame(self, bg="white")
        self.container.pack(fill="both", expand=True)

        self._thumb_refs = []
        self.library_items = []
        self.selected_index = 0
        self.current_view = "library"

        style = ttk.Style()
        style.configure("Selected.TFrame", background="#d0ebff")

        # Initialize encoder
        self.encoder = RotaryEncoder(clk_board=11, dt_board=16, sw_board=18)
        self.encoder.start()

        self.encoder.on_rotate = self._library_rotate
        self.encoder.on_button = self._library_button

        self.show_library()

    # ---------- Container helpers ----------
    def clear_container(self):
        for w in self.container.winfo_children():
            w.destroy()
        self._thumb_refs.clear()

    # ---------- Library ----------
    def show_library(self):
        self.current_view = "library"
        self.clear_container()

        # Reset encoder callbacks
        self.encoder.on_rotate = self._library_rotate
        self.encoder.on_button = self._library_button

        canvas = tk.Canvas(self.container, bg="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.library_items = load_library()
        for epub_file, meta in self.library_items:
            frame = ttk.Frame(scrollable_frame, padding=8, style="TFrame")
            frame.pack(fill="x", pady=4)

            if meta["cover_image"]:
                img = meta["cover_image"].copy()
                img.thumbnail((60, 90))
                tk_img = ImageTk.PhotoImage(img)
            else:
                img = Image.new("RGB", (60, 90), "gray")
                tk_img = ImageTk.PhotoImage(img)
            self._thumb_refs.append(tk_img)

            label_img = tk.Label(frame, image=tk_img, bg="white")
            label_img.image = tk_img
            label_img.pack(side="left", padx=(0, 10))

            info_text = f"{meta['title']}\nby {meta['author']}\n({meta['language']})"
            label_text = tk.Label(frame, text=info_text, justify="left", bg="white", anchor="w")
            label_text.pack(side="left", fill="x", expand=True)

        self.selected_index = 0
        self._highlight_selected()

    def _highlight_selected(self):
        if not self.library_items:
            return
        try:
            canvas = self.container.winfo_children()[0]
            frames = canvas.winfo_children()[0].winfo_children()
            for i, f in enumerate(frames):
                f.configure(style="TFrame")
            frames[self.selected_index].configure(style="Selected.TFrame")
        except Exception:
            pass

    def _library_rotate(self, direction):
        if direction == "CLOCKWISE":
            self._move_selection(1)
        else:
            self._move_selection(-1)

    def _move_selection(self, delta):
        if not self.library_items:
            return
        self.selected_index = (self.selected_index + delta) % len(self.library_items)
        self._highlight_selected()

    def _library_button(self):
        if not self.library_items:
            return
        epub_path, _ = self.library_items[self.selected_index]
        print(f"[DEBUG] Opening reader for: {epub_path}")
        self.show_reader(epub_path)

    # ---------- Reader ----------
       # ---------- Reader ----------
    def show_reader(self, epub_path):
        self.current_view = "reader"
        self.clear_container()

        topbar = ttk.Frame(self.container)
        topbar.pack(fill="x", padx=6, pady=6)
        back_btn = ttk.Button(topbar, text="← Back to Library", command=self.show_library)
        back_btn.pack(side="left")

        try:
            book = epub.read_epub(epub_path)
            title_md = book.get_metadata("DC", "title")
            title_text = title_md[0][0] if title_md else epub_path.stem
        except Exception:
            title_text = epub_path.stem

        title_label = ttk.Label(topbar, text=title_text)
        title_label.pack(side="left", padx=8)

        reader_frame = ReaderWindow(self.container, epub_path)
        reader_frame.pack(fill="both", expand=True)

        # ---------- FIX: Rotary encoder callbacks with proper debounce ----------
        self.encoder.on_rotate = lambda d: self.after(
            0, reader_frame.next_page if d == "CLOCKWISE" else reader_frame.prev_page
        )

        def reader_back_button():
            now = time.time()
            if now - self._last_action_time < self._debounce_delay:
                return
            self._last_action_time = now
            self.show_library()

        self.encoder.on_button = reader_back_button
        # Prevent immediate bounce
        self._last_action_time = time.time() + self._debounce_delay


if __name__ == "__main__":
    if not EBOOKS_DIR.exists():
        print(f"⚠️  Folder '{EBOOKS_DIR}' not found. Create it and add EPUB files.")
    else:
        app = LibraryApp()
        app.mainloop()
