import tkinter as tk
from ebooklib import epub
from bs4 import BeautifulSoup, NavigableString, Tag

WINDOW_WIDTH, WINDOW_HEIGHT = 800, 480
FONT_SIZE_DEFAULT = 14
FONT_FAMILY_DEFAULT = "DejaVuSans"
PAGE_MARGIN = 16  # padding around text edges

BLOCK_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre", "div")
INLINE_BOLD = ("strong", "b")
INLINE_ITALIC = ("em", "i")


class ReaderWindow(tk.Frame):
    """
    Paged reader that preserves rich-text tags.
    Renders full chapter into a hidden buffer text widget that is placed off-screen
    (so it gets real layout metrics), paginates by visible pixel height, and copies page
    ranges into the visible text while preserving tag ranges.
    """

    def __init__(self, master, epub_path):
        super().__init__(master, bg="white", width=WINDOW_WIDTH, height=WINDOW_HEIGHT)

        # Visible text area with margins so top line isn't clipped
        self.text_canvas = tk.Text(
            self,
            wrap="word",
            bg="white",
            bd=0,
            padx=PAGE_MARGIN,
            pady=PAGE_MARGIN,
            spacing1=4,
            spacing3=6,
        )
        self.text_canvas.pack(side="top", fill="both", expand=True, padx=0, pady=(0, 4))

        # Page indicator
        self.page_label = tk.Label(self, text="", bg="white", fg="gray",
                                   font=(FONT_FAMILY_DEFAULT, 10))
        self.page_label.pack(side="bottom", pady=(0, 8))

        # Hidden buffer
        self._buffer = tk.Text(self, wrap="word", bg="white")
        self._buffer.configure(padx=PAGE_MARGIN, pady=PAGE_MARGIN)
        self.define_tags(on_widget=self._buffer)
        self.define_tags(on_widget=self.text_canvas)

        # Place buffer off-screen
        self.update_idletasks()
        visible_w = self.text_canvas.winfo_width() or (WINDOW_WIDTH - 2 * PAGE_MARGIN)
        try:
            self._buffer.place(x=-10000, y=-10000, width=visible_w)
        except Exception:
            self._buffer.place(x=-10000, y=-10000)

        # Load EPUB
        self.book = epub.read_epub(epub_path)
        self.spine_items = [item for item in self.book.get_items() if isinstance(item, epub.EpubHtml)]
        if not self.spine_items:
            self.spine_items = [item for item in self.book.get_items()]

        # State
        self.current_chapter = 0
        self.pages = []
        self.current_page = 0

        # Load first chapter
        self.after(0, lambda: self.load_chapter(self.current_chapter))

        # Bind page navigation
        self.text_canvas.bind("<Right>", lambda e: self.next_page())
        self.text_canvas.bind("<Left>", lambda e: self.prev_page())
        self.bind_all("<Right>", lambda e: self.next_page())
        self.bind_all("<Left>", lambda e: self.prev_page())
        self.text_canvas.focus_set()

    def define_tags(self, on_widget=None):
        w = on_widget or self.text_canvas
        w.tag_configure("bold", font=(FONT_FAMILY_DEFAULT, FONT_SIZE_DEFAULT, "bold"))
        w.tag_configure("italic", font=(FONT_FAMILY_DEFAULT, FONT_SIZE_DEFAULT -4, "italic"))
        w.tag_configure("bold_italic", font=(FONT_FAMILY_DEFAULT, FONT_SIZE_DEFAULT, "bold italic"))
        w.tag_configure("h1", font=(FONT_FAMILY_DEFAULT, 20, "bold"), spacing1=8, spacing3=8)
        w.tag_configure("h2", font=(FONT_FAMILY_DEFAULT, 18, "bold"), spacing1=6, spacing3=6)
        w.tag_configure("h3", font=(FONT_FAMILY_DEFAULT, 16, "bold"), spacing1=4, spacing3=4)
        w.tag_configure("base", font=(FONT_FAMILY_DEFAULT, FONT_SIZE_DEFAULT))

    # ---------------- chapter load & pagination ----------------
    def load_chapter(self, index):
        if not (0 <= index < len(self.spine_items)):
            return

        item = self.spine_items[index]
        try:
            content = item.get_content()
            html = content.decode("utf-8", errors="ignore") if isinstance(content, bytes) else str(content)
        except Exception as e:
            print(f"Error reading item {getattr(item, 'get_name', lambda: 'unknown')()}: {e}")
            html = "<p>[Could not load content]</p>"

        self._buffer.config(state="normal")
        self._buffer.delete("1.0", tk.END)
        self.insert_html_into_buffer(html)
        self._buffer.config(state="disabled")

        self.update_idletasks()
        if self.text_canvas.winfo_height() < 10:
            self.after(50, lambda: self._finish_paging(index))
        else:
            self._finish_paging(index)

    def _finish_paging(self, index):
        visible_w = self.text_canvas.winfo_width() or (WINDOW_WIDTH - 2 * PAGE_MARGIN)
        try:
            self._buffer.place_configure(width=visible_w)
        except Exception:
            pass

        self.pages = self._build_pages()
        self.current_chapter = index
        self.current_page = 0
        self.display_page()

    # ---------------- pagination by actual pixel height ----------------
    def _build_pages(self):
        """
        Paginate by counting *display lines* (wrapped lines), respecting actual font heights.
        Returns list of (start_index, end_index).
        """
        self.update_idletasks()

        visible_height = max(1, self.text_canvas.winfo_height() - 2 * PAGE_MARGIN)
        pages = []

        lines_per_page_safety = 8  # stop 1 line early to avoid overshoot

        start_index = "1.0"
        end_index = self._buffer.index("end-1c")

        while self._buffer.compare(start_index, "<", end_index):
            used_height = 0
            current_index = start_index
            last_index = start_index
            lines_used = 0

            while self._buffer.compare(current_index, "<", end_index):
                next_line_index = f"{int(current_index.split('.')[0]) + 1}.0"
                display_lines = int(self._buffer.count(current_index, next_line_index, "displaylines")[0])

                dline = self._buffer.dlineinfo(current_index)
                line_height = dline[3] if dline else FONT_SIZE_DEFAULT + 4
                pixel_height = display_lines * line_height

                # Stop if adding this line exceeds visible height or lines safety
                if used_height + pixel_height > visible_height or (lines_used + display_lines) > (visible_height // line_height - lines_per_page_safety):
                    break

                used_height += pixel_height
                lines_used += display_lines
                last_index = current_index
                current_index = next_line_index

            end_index_page = f"{last_index.split('.')[0]}.end"
            pages.append((start_index, end_index_page))

            next_start_line = int(last_index.split(".")[0]) + 1
            if self._buffer.compare(f"{next_start_line}.0", ">", end_index):
                break
            start_index = f"{next_start_line}.0"

        if not pages:
            pages = [("1.0", "end")]

        return pages


    # ---------------- display page ----------------
    def display_page(self):
        if not self.pages:
            self.page_label.config(text="Page 0 of 0")
            return

        self.current_page = max(0, min(self.current_page, len(self.pages) - 1))
        start, end = self.pages[self.current_page]

        page_text = self._buffer.get(start, end)
        self.text_canvas.config(state="normal")
        self.text_canvas.delete("1.0", tk.END)
        self.text_canvas.insert("1.0", page_text)

        # Copy tags for overlapping regions
        for tag in self._buffer.tag_names():
            if tag.startswith("sel"):
                continue
            ranges = self._buffer.tag_ranges(tag)
            for i in range(0, len(ranges), 2):
                rstart = ranges[i]
                rend = ranges[i + 1]
                if self._buffer.compare(rend, "<=", start) or self._buffer.compare(rstart, ">=", end):
                    continue
                overlap_start = rstart if self._buffer.compare(rstart, ">", start) else start
                overlap_end = rend if self._buffer.compare(rend, "<", end) else end
                n_before = len(self._buffer.get(start, overlap_start))
                n_len = len(self._buffer.get(overlap_start, overlap_end))
                if n_len <= 0:
                    continue
                vis_start = f"1.0 + {n_before} chars"
                vis_end = f"1.0 + {n_before + n_len} chars"
                try:
                    self.text_canvas.tag_add(tag, vis_start, vis_end)
                except Exception:
                    pass

        self.text_canvas.config(state="disabled")
        self.page_label.config(
            text=f"Page {self.current_page + 1} of {len(self.pages)} — Chapter {self.current_chapter + 1}/{len(self.spine_items)}"
        )

    # ---------------- page navigation ----------------
    def next_page(self):
        if self.current_page + 1 < len(self.pages):
            self.current_page += 1
            self.display_page()
        elif self.current_chapter + 1 < len(self.spine_items):
            self.load_chapter(self.current_chapter + 1)

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.display_page()
        elif self.current_chapter > 0:
            self.load_chapter(self.current_chapter - 1)
            self.current_page = max(0, len(self.pages) - 1)
            self.display_page()

    # ---------------- HTML insertion ----------------
    def insert_html_into_buffer(self, html_content):
        soup = BeautifulSoup(html_content, "html.parser")
        blocks = soup.find_all(BLOCK_TAGS)
        filtered = []

        for b in blocks:
            if any((ancestor.name in BLOCK_TAGS) for ancestor in b.parents if isinstance(ancestor, Tag)):
                parent = b.find_parent(BLOCK_TAGS)
                if parent and parent is not b and parent.name != "body":
                    continue
            filtered.append(b)

        if not filtered:
            body = soup.body or soup
            for child in body.children:
                if isinstance(child, Tag):
                    filtered.append(child)

        for blk in filtered:
            block_text = blk.get_text(separator=" ", strip=True)
            if not block_text:
                continue
            self.insert_inline(blk, into=self._buffer)
            self._buffer.insert("end", "\n")

    def insert_inline(self, node, active_tags=None, into=None):
        if into is None:
            into = self._buffer
        if active_tags is None:
            active_tags = []

        if isinstance(node, NavigableString):
            s = str(node)
            if not s.strip():
                return
            self._insert_text_with_tags(s, active_tags, into)
            return

        new_tags = list(active_tags)
        tagname = node.name.lower() if isinstance(node, Tag) and node.name else None

        if tagname in INLINE_BOLD:
            if "italic" in new_tags:
                new_tags = [t for t in new_tags if t != "italic"] + ["bold_italic"]
            else:
                new_tags.append("bold")
        if tagname in INLINE_ITALIC:
            if "bold" in new_tags:
                new_tags = [t for t in new_tags if t != "bold"] + ["bold_italic"]
            else:
                new_tags.append("italic")

        style = node.get("style", "") if isinstance(node, Tag) else ""
        if "font-family" in style:
            try:
                font_name = style.split("font-family:")[1].split(";")[0].strip().strip('"').strip("'")
                tag_name = f"font_{font_name}"
                if tag_name not in into.tag_names():
                    into.tag_configure(tag_name, font=(font_name, FONT_SIZE_DEFAULT))
                new_tags.append(tag_name)
            except Exception:
                pass

        if tagname in ("h1", "h2", "h3"):
            new_tags.append(tagname)

        for child in node.children:
            if isinstance(child, (Tag, NavigableString)):
                self.insert_inline(child, new_tags, into)

    def _insert_text_with_tags(self, text, tags, into=None):
        if into is None:
            into = self._buffer
        txt = text.replace("\r", "").replace("\n", " ")
        if not txt.strip():
            return
        start = into.index("end-1c")
        into.insert("end", txt)
        end = into.index("end-1c")
        for tag in tags:
            if tag == "bold_italic" and "bold_italic" not in into.tag_names():
                if "bold" in into.tag_names():
                    into.tag_add("bold", start, end)
                if "italic" in into.tag_names():
                    into.tag_add("italic", start, end)
                continue
            try:
                into.tag_add(tag, start, end)
            except Exception:
                pass
