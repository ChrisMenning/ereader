import tkinter as tk
from PIL import Image, ImageTk
import zipfile
import io
from pathlib import Path

class CBZReaderWindow(tk.Frame):
    def __init__(self, master, cbz_path):
        super().__init__(master, bg="white")
        self.cbz_path = Path(cbz_path)
        self.images = []
        self.current_index = 0
        self._thumb_refs = []
        self._load_images()
        self._setup_ui()
        self._show_image()

    def _load_images(self):
        # Open the zip and collect image file names (sorted)
        with zipfile.ZipFile(self.cbz_path, 'r') as z:
            image_files = sorted([f for f in z.namelist() if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp'))])
            self.images = image_files
            self._zipfile = z  # Keep open? No, reopen on demand for memory

    def _setup_ui(self):
        self.canvas = tk.Label(self, bg="white")
        self.canvas.pack(fill="both", expand=True)
        self.page_label = tk.Label(self, text="", bg="white", fg="gray")
        self.page_label.pack(side="bottom", pady=(0, 8))
        self.bind_all("<Right>", lambda e: self.next_page())
        self.bind_all("<Left>", lambda e: self.prev_page())

    def _show_image(self):
        if not self.images:
            self.canvas.config(text="No images found in CBZ.")
            return
        idx = self.current_index
        with zipfile.ZipFile(self.cbz_path, 'r') as z:
            img_data = z.read(self.images[idx])
            pil_img = Image.open(io.BytesIO(img_data))
            # Resize to fit frame
            w, h = self.winfo_width() or 480, self.winfo_height() or 800
            pil_img.thumbnail((w-32, h-64))
            tk_img = ImageTk.PhotoImage(pil_img)
            self._thumb_refs = [tk_img]  # Keep reference
            self.canvas.config(image=tk_img, text="")
            self.canvas.image = tk_img
        self.page_label.config(text=f"Page {idx+1} / {len(self.images)}")

    def next_page(self):
        if self.current_index + 1 < len(self.images):
            self.current_index += 1
            self._show_image()

    def prev_page(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._show_image()
