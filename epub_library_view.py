# epub_library_view.py (refactored — full integration with DisplayLayer)
import tkinter as tk
from tkinter import ttk
from ebooklib import epub
from pathlib import Path
from PIL import Image
import io
from formatted_reader_view import ReaderWindow
from cbz_reader_view import CBZReaderWindow
from rotary_encoder import RotaryEncoder
import time
from config import IS_DEBUG
import zipfile

# Import the display layer (TkDisplay implements full UI including modal)
from DisplayLayer import TkDisplay

# ---------- CONFIG ----------
EBOOKS_DIR = Path("ebooks")
COVERS_DIR = Path("covers")
WINDOW_WIDTH, WINDOW_HEIGHT = 480, 800
PAGE_MARGIN = 16

# ---------- UTILITIES ----------
def get_epub_metadata(epub_path):
    try:
        book = epub.read_epub(epub_path)
    except Exception:
        return {"title": epub_path.stem, "author": "", "language": "", "cover_image": None}

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
                        img = img.convert("L").convert("1")
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


# ---------- Application (controller only) ----------
class LibraryApp(tk.Tk):
    def clear_container(self):
        for w in self.container.winfo_children():
            w.destroy()
        self._thumb_refs = []

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

        # Create display (full UI lives in DisplayLayer/TkDisplay)
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
        self.current_book_path = book_path
        self.current_reader = self.display.current_reader

        # ---------- Encoder callbacks for reader + modal ----------
        def on_rotate(direction):
            if self.modal_active:
                if direction == "CLOCKWISE":
                    self.modal_index = (self.modal_index + 1) % len(self.modal_options)
                else:
                    self.modal_index = (self.modal_index - 1) % len(self.modal_options)
                # tell display to update its modal highlight
                try:
                    self.display.update_modal_selection(self.modal_index)
                except Exception:
                    pass
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
                # open modal via display
                self.modal_active = True
                self.modal_index = 0
                try:
                    self.display.open_modal(self.modal_options, self.modal_index)
                except Exception:
                    pass

        self.encoder.on_rotate = on_rotate
        self.encoder.on_button = on_button
        self._last_action_time = time.time() + self._debounce_delay

    # ---------- Modal helpers (controller actions; UI handled by display) ----------
    def _select_modal_option(self):
        option = self.modal_options[self.modal_index]
        # close modal UI
        try:
            self.display.close_modal()
        except Exception:
            pass
        self.modal_active = False

        if option == "Back to Library":
            self.show_library()
        elif option == "Drop Bookmark":
            # Save current chapter/page
            chap = getattr(self.display.current_reader, "current_chapter", None)
            page = getattr(self.display.current_reader, "current_page", None)
            self.bookmarks[self.current_book_path] = (chap, page)
            print(f"[DEBUG] Bookmark saved at chapter {chap}, page {page}")
        elif option == "Go to Bookmark":
            bm = self.bookmarks.get(self.current_book_path)
            if bm:
                chap, page = bm
                try:
                    self.display.load_chapter(chap)
                    if hasattr(self.display.current_reader, "current_page"):
                        self.display.current_reader.current_page = page
                    self.display.display_page()
                    print(f"[DEBUG] Jumped to bookmark at chapter {chap}, page {page}")
                except Exception as e:
                    print(f"[DEBUG] Error jumping to bookmark: {e}")
            else:
                print("[DEBUG] No bookmark found for this book")
        # Cancel does nothing


if __name__ == "__main__":
    if not EBOOKS_DIR.exists():
        print(f"⚠️  Folder '{EBOOKS_DIR}' not found. Create it and add EPUB/CBZ files.")
    else:
        app = LibraryApp()
        app.mainloop()
