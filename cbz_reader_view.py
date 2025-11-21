import tkinter as tk
from PIL import Image, ImageTk
import zipfile
import io
from pathlib import Path
import threading

class CBZReaderWindow(tk.Frame):
    def __init__(self, master, cbz_path):
        super().__init__(master, bg="white")
        self.cbz_path = Path(cbz_path)
        self.images = []
        self.current_index = 0
        self._thumb_refs = []
        self._image_lock = threading.Lock()
        self._current_worker = None
        self._cancel_worker = threading.Event()

        self._load_images()
        self._setup_ui()

        # Bind resize to update current image
        self.bind("<Configure>", lambda e: self._schedule_image_update())
        self.after(50, self._schedule_image_update)

    def _load_images(self):
        """Load image file names from CBZ lazily."""
        with zipfile.ZipFile(self.cbz_path, 'r') as z:
            self.images = sorted([f for f in z.namelist()
                                  if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp'))])
        if not self.images:
            print("No images found in CBZ!")

    def _setup_ui(self):
        self.canvas = tk.Label(self, bg="white")
        self.canvas.pack(fill="both", expand=True)

        self.page_label = tk.Label(self, text="", bg="white", fg="gray")
        self.page_label.pack(side="bottom", pady=(0, 8))

        self.bind_all("<Right>", lambda e: self.next_page())
        self.bind_all("<Left>", lambda e: self.prev_page())

    def _schedule_image_update(self):
        """Schedule loading the current image (debounced)."""
        if hasattr(self, "_update_id") and self._update_id:
            self.after_cancel(self._update_id)
        self._update_id = self.after(50, self._load_current_image)

    def _load_current_image(self):
        """Load only the current page in a background thread."""
        if not self.images or not self.winfo_exists():
            return

        idx = self.current_index

        # Cancel any previous worker
        self._cancel_worker.set()

        def worker(load_idx, cancel_event):
            try:
                with zipfile.ZipFile(self.cbz_path, 'r') as z:
                    img_data = z.read(self.images[load_idx])
                pil_img = Image.open(io.BytesIO(img_data))

                if cancel_event.is_set() or not self.winfo_exists():
                    return

                # Resize to fit current frame
                w, h = max(self.winfo_width() - 32, 1), max(self.winfo_height() - 64, 1)
                pil_img.thumbnail((w, h))

                # Convert to 1-bit B/W for e-paper
                pil_img = pil_img.convert("1")
                tk_img = ImageTk.PhotoImage(pil_img)

                def update_ui():
                    if cancel_event.is_set() or not self.winfo_exists() or self.current_index != load_idx:
                        return
                    with self._image_lock:
                        self._thumb_refs = [tk_img]  # keep reference
                        self.canvas.config(image=tk_img, text="")
                        self.canvas.image = tk_img
                        self.page_label.config(text=f"Page {load_idx+1} / {len(self.images)}")

                self.after(0, update_ui)

            except Exception as e:
                print("Error loading CBZ image:", e)

        # Start new worker
        self._cancel_worker = threading.Event()
        t = threading.Thread(target=lambda: worker(idx, self._cancel_worker), daemon=True)
        t.start()
        self._current_worker = t

    def next_page(self):
        if self.current_index + 1 < len(self.images):
            self.current_index += 1
            self._schedule_image_update()

    def prev_page(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._schedule_image_update()
