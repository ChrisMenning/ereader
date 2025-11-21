import tkinter as tk
import tkinter.font as tkfont
from ebooklib import epub
from bs4 import BeautifulSoup, NavigableString, Tag
import time

WINDOW_WIDTH, WINDOW_HEIGHT = 800, 480
FONT_SIZE_DEFAULT = 14
FONT_FAMILY_DEFAULT = "LiberationSerif"
PAGE_MARGIN = 16  # padding around text edges

BLOCK_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre", "div")
INLINE_BOLD = ("strong", "b")
INLINE_ITALIC = ("em", "i")


class ReaderWindow(tk.Frame):    
    def __init__(self, master, epub_path):
        super().__init__(master, bg="white", width=WINDOW_WIDTH, height=WINDOW_HEIGHT)
        self.epub_path = epub_path

        # Layout: vertical stack (text area above, footer below)
        self.main_frame = tk.Frame(self, bg="white")
        self.main_frame.pack(fill="both", expand=True)

        # Footer frame (always visible at bottom)
        self.footer_frame = tk.Frame(self.main_frame, bg="white")
        self.footer_frame.place(relx=0, rely=1.0, relwidth=1.0, anchor="sw")

        # Chapter footer label
        self.page_label = tk.Label(self.footer_frame, text="", bg="white", fg="gray",
                                   font=(FONT_FAMILY_DEFAULT, 10), anchor="w")
        self.page_label.pack(side="left", padx=(PAGE_MARGIN, 0), pady=(0, 8))

        # Page number label (footer)
        self.page_number_footer = tk.Label(self.footer_frame, text="", bg="white", fg="#999999",
                                          font=(FONT_FAMILY_DEFAULT, 10), anchor="e")
        self.page_number_footer.pack(side="right", padx=(0, PAGE_MARGIN), pady=(0, 8))

        # Visible text area
        self.text_canvas = tk.Text(
            self.main_frame,
            wrap="word",
            bg="white",
            bd=0,
            padx=PAGE_MARGIN,
            pady=PAGE_MARGIN,
            spacing1=4,
            spacing3=6,
        )
        # Set height after window is mapped
        self.after(100, self._resize_text_canvas)

    def _resize_text_canvas(self):
        self.update_idletasks()
        footer_height = self.footer_frame.winfo_height() or 40
        total_height = self.main_frame.winfo_height() or WINDOW_HEIGHT
        text_height = max(100, total_height - footer_height)
        self.text_canvas.place(x=0, y=0, width=self.main_frame.winfo_width() or WINDOW_WIDTH, height=text_height)

        # Footer frame (always visible at bottom)
        self.footer_frame = tk.Frame(self.main_frame, bg="white")
        self.footer_frame.pack(side="bottom", fill="x")

        # Chapter footer label
        self.page_label = tk.Label(self.footer_frame, text="", bg="white", fg="gray",
                                   font=(FONT_FAMILY_DEFAULT, 10), anchor="w")
        self.page_label.pack(side="left", padx=(PAGE_MARGIN, 0), pady=(0, 8))

        # Page number label (footer)
        self.page_number_footer = tk.Label(self.footer_frame, text="", bg="white", fg="#999999",
                                          font=(FONT_FAMILY_DEFAULT, 10), anchor="e")
        self.page_number_footer.pack(side="right", padx=(0, PAGE_MARGIN), pady=(0, 8))

        # Persistent hidden buffer for measuring layout
        self._buffer = tk.Text(self, wrap="word", bg="white")
        self._buffer.configure(padx=PAGE_MARGIN, pady=PAGE_MARGIN)
        self.define_tags(on_widget=self._buffer)
        self.define_tags(on_widget=self.text_canvas)
        self._buffer.place(x=-10000, y=-10000, width=WINDOW_WIDTH - 2 * PAGE_MARGIN)

        # Load EPUB
        self.book = epub.read_epub(self.epub_path)
        self.spine_items = [item for item in self.book.get_items() if isinstance(item, epub.EpubHtml)]
        if not self.spine_items:
            self.spine_items = [item for item in self.book.get_items()]

        # State
        self.current_chapter = 0
        self.pages = []
        self.current_page = 0

        # Load first chapter
        self.after(0, lambda: self.load_chapter(self.current_chapter))

        # Keyboard fallback
        self.bind_all("<Right>", lambda e: self.next_page())
        self.bind_all("<Left>", lambda e: self.prev_page())
        self.text_canvas.focus_set()

        self.text_canvas.configure(font=(FONT_FAMILY_DEFAULT, FONT_SIZE_DEFAULT))
        self._buffer.configure(font=(FONT_FAMILY_DEFAULT, FONT_SIZE_DEFAULT))


    # ---------- Tag setup ----------
    def define_tags(self, on_widget=None):
        w = on_widget or self.text_canvas
        w.tag_configure("bold", font=(FONT_FAMILY_DEFAULT, FONT_SIZE_DEFAULT, "bold"))
        w.tag_configure("italic", font=(FONT_FAMILY_DEFAULT, max(8, FONT_SIZE_DEFAULT - 4), "italic"))
        w.tag_configure("bold_italic", font=(FONT_FAMILY_DEFAULT, FONT_SIZE_DEFAULT, "bold italic"))
        w.tag_configure("h1", font=(FONT_FAMILY_DEFAULT, 20, "bold"), spacing1=8, spacing3=8)
        w.tag_configure("h2", font=(FONT_FAMILY_DEFAULT, 18, "bold"), spacing1=6, spacing3=6)
        w.tag_configure("h3", font=(FONT_FAMILY_DEFAULT, 16, "bold"), spacing1=4, spacing3=4)
        w.tag_configure("base", font=(FONT_FAMILY_DEFAULT, FONT_SIZE_DEFAULT))

        if not hasattr(self, "_fonts"):
            self._fonts = {}
        self._fonts["base"] = tkfont.Font(family=FONT_FAMILY_DEFAULT, size=FONT_SIZE_DEFAULT)
        self._fonts["h1"] = tkfont.Font(family=FONT_FAMILY_DEFAULT, size=20, weight="bold")
        self._fonts["h2"] = tkfont.Font(family=FONT_FAMILY_DEFAULT, size=18, weight="bold")
        self._fonts["h3"] = tkfont.Font(family=FONT_FAMILY_DEFAULT, size=16, weight="bold")
        self._fonts["bold"] = tkfont.Font(family=FONT_FAMILY_DEFAULT, size=FONT_SIZE_DEFAULT, weight="bold")
        self._fonts["italic"] = tkfont.Font(family=FONT_FAMILY_DEFAULT, size=max(8, FONT_SIZE_DEFAULT - 4), slant="italic")

    # ---------- Chapter load ----------
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

        # Reset buffer
        if self._buffer.winfo_exists():
            self._buffer.config(state="normal")
            self._buffer.delete("1.0", tk.END)
        self.insert_html_into_buffer(html)
        if self._buffer.winfo_exists():
            self._buffer.config(state="disabled")

        self.update_idletasks()
        if self.text_canvas.winfo_height() < 10:
            self.after(50, lambda: self._finish_paging(index))
        else:
            self._finish_paging(index)

    def _finish_paging(self, index):
        # Ensure buffer has same width and height as the visible text area while we measure
        visible_w = self.text_canvas.winfo_width() or (WINDOW_WIDTH - 2 * PAGE_MARGIN)
        visible_h = self.text_canvas.winfo_height() or (WINDOW_HEIGHT - 2 * PAGE_MARGIN)

        # Temporarily place the buffer in the same space as the canvas so wrapping/count is accurate.
        # We'll hide it again after paging.
        self._buffer.place_configure(x=self.text_canvas.winfo_x(),
                                    y=self.text_canvas.winfo_y(),
                                    width=visible_w,
                                    height=visible_h)
        # Force geometry/layout to be computed
        self.update_idletasks()
        try:
            self._buffer.update_idletasks()
        except Exception:
            pass

        # Now build pages reliably
        self.pages = self._build_pages()

        # Hide buffer again (move off-screen to keep it out of view)
        self._buffer.place_configure(x=-10000, y=-10000)

        self.current_chapter = index
        self.current_page = 0
        self.display_page()


    # ---------- Pagination ----------
    def _build_pages(self):
        self.update_idletasks()
        try:
            self._buffer.update_idletasks()
            self._buffer.update()
        except Exception:
            pass

        # Reserve space for footer
        footer_space = self.footer_frame.winfo_height() or 40
        canvas_height = self.main_frame.winfo_height() or WINDOW_HEIGHT
        visible_height = max(1, canvas_height - 2 * PAGE_MARGIN - footer_space)

        # --- NEW: subtract 2 lines as a fudge factor ---
        fudge_lines = 2
        font_obj = self._fonts["base"]
        line_height = int(font_obj.metrics("linespace")) if font_obj else FONT_SIZE_DEFAULT + 4
        visible_height -= fudge_lines * line_height

        bottom_margin = 4  # extra safety

        pages = []
        buf_end = self._buffer.index("end-1c")
        start_index = "1.0"

        if self._buffer.compare(start_index, ">=", buf_end):
            return [("1.0", "end")]

        def pick_font_for_index(idx):
            tags = self._buffer.tag_names(idx)
            if "h1" in tags:
                return self._fonts.get("h1", self._fonts["base"]), 8, 8
            if "h2" in tags:
                return self._fonts.get("h2", self._fonts["base"]), 6, 6
            if "h3" in tags:
                return self._fonts.get("h3", self._fonts["base"]), 4, 4
            return self._fonts["base"], 0, 0

        paragraph_spacing = 6

        while self._buffer.compare(start_index, "<", buf_end):
            page_start = start_index
            used_pixels = 0
            idx = start_index

            while True:
                chunk_end = self._buffer.index(f"{idx} +50 chars")
                if self._buffer.compare(chunk_end, ">", buf_end):
                    chunk_end = buf_end

                display_lines = self._buffer.count(idx, chunk_end, "displaylines")[0] or 1
                font_obj, spacing1, spacing3 = pick_font_for_index(idx)
                try:
                    line_space = int(font_obj.metrics("linespace"))
                except Exception:
                    line_space = FONT_SIZE_DEFAULT + 4

                added_height = display_lines * line_space + spacing1 + spacing3
                next_char = self._buffer.get(chunk_end, f"{chunk_end} +1c")
                if next_char == "\n":
                    added_height += paragraph_spacing

                if used_pixels + added_height > visible_height - bottom_margin:
                    if self._buffer.compare(idx, "==", page_start):
                        idx = chunk_end
                    break

                used_pixels += added_height
                idx = chunk_end
                if self._buffer.compare(idx, ">=", buf_end):
                    break

            pages.append((page_start, idx))
            start_index = idx
            if self._buffer.compare(start_index, ">=", buf_end):
                break

        if not pages:
            pages = [("1.0", "end")]
        return pages

    # ---------- Page display ----------
    def display_page(self):
        if not self.pages or not self._buffer.winfo_exists():
            return

        self.current_page = max(0, min(self.current_page, len(self.pages) - 1))
        start, end = self.pages[self.current_page]

        page_text = self._buffer.get(start, end)
        self.text_canvas.config(state="normal")
        self.text_canvas.delete("1.0", tk.END)
        self.text_canvas.insert("1.0", page_text)

        # Copy formatting
        for tag in self._buffer.tag_names():
            if tag.startswith("sel"):
                continue
            ranges = self._buffer.tag_ranges(tag)
            for i in range(0, len(ranges), 2):
                rstart, rend = ranges[i], ranges[i + 1]
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
        # Remove overlay page number, update footer
        self.page_number_footer.config(text=f"{self.current_page + 1} / {len(self.pages)}")
        self.page_label.config(text=f"Chapter {self.current_chapter + 1} of {len(self.spine_items)}")

    # ---------- Navigation ----------
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

    # ---------- HTML parsing ----------
    def insert_html_into_buffer(self, html_content):
        soup = BeautifulSoup(html_content, "html.parser")

        # --- TOC detection ---
        toc_nav = soup.find(lambda tag: (tag.name == "nav" and tag.get("epub:type") == "toc") or (tag.name == "div" and "toc" in tag.get("class", [])))
        if toc_nav:
            # If <nav epub:type="toc"> is inside a <div class="toc">, use the parent for heading
            toc_container = toc_nav.find_parent("div", class_="toc") or toc_nav
            self._insert_toc_block(toc_container)
            return

        # --- Normal block parsing ---
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

    def _insert_toc_block(self, toc_container):
        """Render the entire Table of Contents as a single block, with heading and all items on one page."""
        # Find heading (e.g., h1, .toc-title, etc.)
        heading = None
        if toc_container:
            heading = toc_container.find("h1") or toc_container.find("div", class_="toc-title")
        if heading:
            self._insert_text_with_tags(heading.get_text(strip=True), ["h1"], self._buffer)
            self._buffer.insert("end", "\n\n")

        # Find the <nav> or <ol>/<ul> containing the ToC entries
        nav = toc_container.find("nav") if toc_container else None
        ol = nav.find("ol") if nav and nav.find("ol") else (toc_container.find("ol") if toc_container else None)
        ul = nav.find("ul") if nav and nav.find("ul") else (toc_container.find("ul") if toc_container else None)
        list_tag = ol or ul
        if list_tag:
            self._insert_toc_list(list_tag, indent=0)
        else:
            # fallback: just print all links in container
            links = toc_container.find_all("a") if toc_container else []
            for a in links:
                self._insert_text_with_tags(a.get_text(strip=True), [], self._buffer)
                self._buffer.insert("end", "\n")

    def _insert_toc_list(self, list_tag, indent=0):
        """Recursively render a <ol> or <ul> as a single block, with indentation for sublists."""
        for li in list_tag.find_all("li", recursive=False):
            # Find the link and text
            link = li.find("a")
            text = link.get_text(strip=True) if link else li.get_text(strip=True)
            self._insert_text_with_tags(" " * (indent * 4) + text, [], self._buffer)
            self._buffer.insert("end", "\n")
            # Handle nested lists
            sub_ol = li.find("ol", recursive=False)
            sub_ul = li.find("ul", recursive=False)
            if sub_ol:
                self._insert_toc_list(sub_ol, indent=indent + 1)
            elif sub_ul:
                self._insert_toc_list(sub_ul, indent=indent + 1)

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
            try:
                into.tag_add(tag, start, end)
            except Exception:
                pass
