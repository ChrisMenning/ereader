import tkinter as tk
from tkinter import ttk
from ebooklib import epub
from pathlib import Path
from PIL import Image, ImageTk
import io
from pathlib import Path
from formatted_reader_view import ReaderWindow

# ---------- CONFIG ----------
EBOOKS_DIR = Path("ebooks")
COVERS_DIR = Path("covers")
WINDOW_WIDTH, WINDOW_HEIGHT = 480, 800

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

    # Try to extract a cover image (modern EbookLib)
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
        super().__init__()
        self.title("E-Book Library")
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.configure(bg="white")

        # top-level container that will be cleared/swapped
        self.container = tk.Frame(self, bg="white")
        self.container.pack(fill="both", expand=True)

        # hold thumbnail references to avoid GC
        self._thumb_refs = []

        # Start by showing the library list
        self.show_library()

    def clear_container(self):
        for w in self.container.winfo_children():
            w.destroy()
        self._thumb_refs.clear()

    def show_library(self):
        self.clear_container()

        canvas = tk.Canvas(self.container, bg="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        library = load_library()
        for epub_file, meta in library:
            frame = ttk.Frame(scrollable_frame, padding=8)
            frame.pack(fill="x", pady=4)

            # Cover thumbnail
            if meta["cover_image"]:
                img = meta["cover_image"].copy()
                img.thumbnail((60, 90))
                tk_img = ImageTk.PhotoImage(img)
            else:
                # Placeholder rectangle
                img = Image.new("RGB", (60, 90), "gray")
                tk_img = ImageTk.PhotoImage(img)

            # keep reference to avoid GC (so image stays visible)
            self._thumb_refs.append(tk_img)

            label_img = tk.Label(frame, image=tk_img, bg="white", cursor="hand2")
            label_img.image = tk_img  # keep reference as well
            label_img.pack(side="left", padx=(0, 10))

            # Text metadata
            info_text = f"{meta['title']}\nby {meta['author']}\n({meta['language']})"

            label_text = tk.Label(
                frame, text=info_text, justify="left", bg="white", anchor="w", cursor="hand2"
            )
            label_text.pack(side="left", fill="x", expand=True)

            # Bind click to show reader inside same window
            label_text.bind("<Button-1>", lambda e, path=epub_file: self.show_reader(path))
            label_img.bind("<Button-1>", lambda e, path=epub_file: self.show_reader(path))
            frame.bind("<Button-1>", lambda e, path=epub_file: self.show_reader(path))

    def show_reader(self, epub_path):
        """
        Clear the container and embed a ReaderWindow (Frame) that displays the book.
        A back button is added to return to the library list.
        """
        self.clear_container()

        topbar = ttk.Frame(self.container)
        topbar.pack(fill="x", padx=6, pady=6)
        back_btn = ttk.Button(topbar, text="← Back to Library", command=self.show_library)
        back_btn.pack(side="left")

        # Optional: show book title on the topbar
        try:
            book = epub.read_epub(epub_path)
            title_md = book.get_metadata("DC", "title")
            title_text = title_md[0][0] if title_md else epub_path.stem
        except Exception:
            title_text = epub_path.stem

        title_label = ttk.Label(topbar, text=title_text)
        title_label.pack(side="left", padx=8)

        # Reader frame (from formatted_reader_view.ReaderWindow which now subclasses Frame)
        reader_frame = ReaderWindow(self.container, epub_path)
        reader_frame.pack(fill="both", expand=True)

if __name__ == "__main__":
    if not EBOOKS_DIR.exists():
        print(f"⚠️  Folder '{EBOOKS_DIR}' not found. Create it and add EPUB files.")
    else:
        app = LibraryApp()
        app.mainloop()
