# epub_library_view.py
import tkinter as tk
from tkinter import ttk
from ebooklib import epub
from pathlib import Path
from PIL import Image, ImageTk
import io
from formatted_reader_view import ReaderWindow
from cbz_reader_view import CBZReaderWindow
from rotary_encoder import RotaryEncoder
import time
from config import IS_DEBUG
from abc import ABC, abstractmethod
import zipfile

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
    # EPUBs
    for epub_file in sorted(EBOOKS_DIR.glob("*.epub")):
        try:
            data = get_epub_metadata(epub_file)
            data["type"] = "epub"
            library.append((epub_file, data))
        except Exception as e:
            print(f"Error reading {epub_file}: {e}")
    # CBZs
    for cbz_file in sorted(EBOOKS_DIR.glob("*.cbz")):
        try:
            with zipfile.ZipFile(cbz_file, 'r') as z:
                image_files = sorted([f for f in z.namelist() if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp"))])
                cover_image = None
                if image_files:
                    img_data = z.read(image_files[0])
                    try:
                        img = Image.open(io.BytesIO(img_data))
                        img = img.convert("L").convert("1")   # 1-bit for e-paper
                        cover_image = img
                    except Exception:
                        cover_image = None

                meta = {
                    "title": cbz_file.stem,
                    "author": "",
                    "language": "",
                    "cover_image": cover_image,
                    "type": "cbz",
                    "page_count": len(image_files),
                }
                library.append((cbz_file, meta))
        except Exception as e:
            print(f"Error reading {cbz_file}: {e}")
    return library

# ---------- Display Abstraction ----------
class DisplayBase(ABC):
    """
    Abstract display API. Implementations should manage rendering the library
    and reader UI and expose the currently-open reader object (if any).
    """

    def __init__(self, container):
        self.container = container
        self.current_reader = None

    @abstractmethod
    def clear_container(self):
        """Clear the container from any display-specific widgets."""
        pass

    @abstractmethod
    def show_library(self, library_items):
        """
        Render the library view given the list of (path, metadata) tuples.
        Implementations must track selection and expose:
          - move_selection(delta)
          - get_selected_item()
          - open_selected()
        """
        pass

    @abstractmethod
    def move_selection(self, delta):
        """Move the library selection by delta (positive or negative)."""
        pass

    @abstractmethod
    def get_selected_item(self):
        """Return the currently selected library item (path, meta)."""
        pass

    @abstractmethod
    def open_selected(self):
        """Open the currently selected item (simulate pressing the 'open' button)."""
        pass

    @abstractmethod
    def show_reader(self, book_path):
        """
        Create and display a reader for `book_path`. Should set self.current_reader
        to the ReaderWindow / CBZReaderWindow instance and return a title_text.
        """
        pass

    # Convenience wrappers that simply call into the reader object if available:
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

# ---------- Tkinter Display Implementation ----------
class TkDisplay(DisplayBase):
    def __init__(self, container):
        super().__init__(container)
        # Library state:
        self.library_items = []
        self._thumb_refs = []
        self.selected_index = 0

    # --- Helpers ---
    def clear_container(self):
        for w in self.container.winfo_children():
            w.destroy()
        self._thumb_refs.clear()

    # --- Library UI (moved from LibraryApp.show_library) ---
    def show_library(self, library_items):
        self.clear_container()
        self.library_items = library_items

        canvas = tk.Canvas(self.container, bg="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for epub_file, meta in self.library_items:
            frame = ttk.Frame(scrollable_frame, padding=8, style="TFrame")
            frame.pack(fill="x", pady=4)

            # Convert cover to 1-bit e-paper friendly thumbnail
            if meta.get("cover_image"):
                try:
                    img = meta["cover_image"].copy()
                    img = img.convert("L")  # grayscale first
                    img = img.resize((60, 90), Image.LANCZOS)
                    img = img.convert("1")  # pure black/white
                except Exception:
                    img = Image.new("1", (60, 90), 1)
            else:
                img = Image.new("1", (60, 90), 1)  # white placeholder

            tk_img = ImageTk.PhotoImage(img)
            self._thumb_refs.append(tk_img)

            label_img = tk.Label(frame, image=tk_img, bg="white")
            label_img.image = tk_img
            label_img.pack(side="left", padx=(0, 10))

            info_text = f"{meta.get('title','Untitled')}\nby {meta.get('author','')}\n({meta.get('language','')})"
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

    # --- Reader UI (moved from LibraryApp.show_reader) ---
    def show_reader(self, book_path):
        self.clear_container()

        ext = str(book_path).lower()
        is_cbz = ext.endswith(".cbz")
        is_epub = ext.endswith(".epub")

        if is_cbz:
            title_text = book_path.stem
            reader_frame = CBZReaderWindow(self.container, book_path)
            reader_frame.pack(fill="both", expand=True)
            title_label = ttk.Label(self.container, text=title_text, font=("TkDefaultFont", 14))
            title_label.pack(side="top", pady=(4, 0))
            self.current_reader = reader_frame
            return title_text

        # EPUB fallback
        try:
            book = epub.read_epub(book_path)
            title_md = book.get_metadata("DC", "title")
            title_text = title_md[0][0] if title_md else book_path.stem
        except Exception:
            title_text = book_path.stem

        reader_frame = ReaderWindow(self.container, book_path)
        reader_frame.pack(fill="both", expand=True)

        title_label = ttk.Label(self.container, text=title_text, font=("TkDefaultFont", 14))
        title_label.pack(side="top", pady=(4, 0))

        self.current_reader = reader_frame
        return title_text

# ---------- Application ----------
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

        style = ttk.Style()
        style.configure("Selected.TFrame", background="#d0ebff")
        style.configure("Modal.TFrame", background="#eeeeee")
        style.configure("ModalSelected.TFrame", background="#d0ebff")

        # Initialize encoder
        self.encoder = RotaryEncoder(isDebugMode=IS_DEBUG)
        self.encoder.start()

        # ---------- Bookmarks ----------
        self.bookmarks = {}  # book path → (chapter_index, page_index)

        # Choose display based on debug flag (for now: TkDisplay when IS_DEBUG True)
        # You can swap this to an EPaperDisplay when you implement it.
        self.display = TkDisplay(self.container)

        # Wire encoder defaults to library actions until show_library replaces them
        self.encoder.on_rotate = lambda direction: self.display.move_selection(1 if direction == "CLOCKWISE" else -1)
        self.encoder.on_button = lambda: self._open_selection_from_encoder()

        # Show initial library
        self.show_library()

    # ---------- Container helpers ----------
    def clear_container(self):
        self.display.clear_container()

    # ---------- Library ----------
    def show_library(self):
        self.current_view = "library"
        self.clear_container()

        # Reset encoder callbacks to operate the library selection
        self.encoder.on_rotate = lambda direction: self.display.move_selection(1 if direction == "CLOCKWISE" else -1)
        self.encoder.on_button = lambda: self._open_selection_from_encoder()

        self.library_items = load_library()
        self.display.show_library(self.library_items)
        # ensure selected index is local-copy aligned (display holds index)
        # (LibraryApp no longer needs to manipulate selection directly.)

    def _open_selection_from_encoder(self):
        if not getattr(self, "library_items", None):
            return
        sel = self.display.get_selected_item()
        if not sel:
            return
        epub_path, _ = sel
        print(f"[DEBUG] Opening reader for: {epub_path}")
        self.show_reader(epub_path)

    # ---------- Reader ----------
    def show_reader(self, book_path):
        self.current_view = "reader"
        self.clear_container()

        title_text = self.display.show_reader(book_path)
        # display.show_reader sets display.current_reader

        # ---------- Modal state ----------
        self.modal_active = False
        self.modal_index = 0
        self.modal_options = ["Drop Bookmark", "Go to Bookmark", "Back to Library", "Cancel"]
        self.modal_frame = None
        self.modal_buttons = []
        self.current_book_path = book_path
        self.current_reader = self.display.current_reader

        # ---------- Encoder callbacks for reader + modal ----------
        def on_rotate(direction):
            if self.modal_active:
                if direction == "CLOCKWISE":
                    self.modal_index = (self.modal_index + 1) % len(self.modal_options)
                else:
                    self.modal_index = (self.modal_index - 1) % len(self.modal_options)
                self._update_modal_selection()
            else:
                if direction == "CLOCKWISE":
                    self.display.next_page()
                else:
                    self.display.prev_page()

        def on_button():
            now = time.time()
            if now - self._last_action_time < self._debounce_delay:
                return
            self._last_action_time = now

            if self.modal_active:
                self._select_modal_option()
            else:
                self._open_modal()

        self.encoder.on_rotate = on_rotate
        self.encoder.on_button = on_button
        self._last_action_time = time.time() + self._debounce_delay

    # ---------- Modal helpers ----------
    def _open_modal(self):
        if self.modal_active:
            return
        self.modal_active = True
        self.modal_index = 0

        self.modal_frame = ttk.Frame(self.container, style="Modal.TFrame", padding=10)
        self.modal_frame.place(relx=0.5, rely=0.5, anchor="center")

        self.modal_buttons = []
        for i, opt in enumerate(self.modal_options):
            b = ttk.Label(self.modal_frame, text=opt, padding=6, anchor="center")
            b.pack(fill="x", pady=2)
            self.modal_buttons.append(b)

        self._update_modal_selection()

    def _update_modal_selection(self):
        for i, lbl in enumerate(self.modal_buttons):
            if i == self.modal_index:
                lbl.configure(background="#d0ebff")
            else:
                lbl.configure(background="#eeeeee")

    def _select_modal_option(self):
        option = self.modal_options[self.modal_index]
        if self.modal_frame:
            self.modal_frame.destroy()
        self.modal_active = False

        if option == "Back to Library":
            self.show_library()
        elif option == "Drop Bookmark":
            # Save current chapter/page
            chap = getattr(self.current_reader, "current_chapter", None)
            page = getattr(self.current_reader, "current_page", None)
            self.bookmarks[self.current_book_path] = (chap, page)
            print(f"[DEBUG] Bookmark saved at chapter {chap}, page {page}")
        elif option == "Go to Bookmark":
            # Jump to saved bookmark if exists
            bm = self.bookmarks.get(self.current_book_path)
            if bm:
                chap, page = bm
                self.display.load_chapter(chap)
                # note: some ReaderWindow implementations expect current_page to be set
                if hasattr(self.display.current_reader, "current_page"):
                    self.display.current_reader.current_page = page
                self.display.display_page()
                print(f"[DEBUG] Jumped to bookmark at chapter {chap}, page {page}")
            else:
                print("[DEBUG] No bookmark found for this book")
        # Cancel does nothing

if __name__ == "__main__":
    if not EBOOKS_DIR.exists():
        print(f"⚠️  Folder '{EBOOKS_DIR}' not found. Create it and add EPUB/CBZ files.")
    else:
        app = LibraryApp()
        app.mainloop()
