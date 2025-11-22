import tkinter as tk
import tkinter.font as tkfont
from ebooklib import epub
from bs4 import BeautifulSoup, NavigableString, Tag
import time
from config import IS_DEBUG

# Import display layer classes
from DisplayLayer import DisplayInterface, TkDisplay

WINDOW_WIDTH, WINDOW_HEIGHT = 800, 480
FONT_SIZE_DEFAULT = 14
FONT_FAMILY_DEFAULT = "LiberationSerif"
PAGE_MARGIN = 16  # padding around text edges

BLOCK_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre", "div")
INLINE_BOLD = ("strong", "b")
INLINE_ITALIC = ("em", "i")


# -----------------------
# ReaderWindow (refactored to use DisplayInterface)
# -----------------------
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
        self.text_canvas.place(x=0, y=0, width=WINDOW_WIDTH, height=WINDOW_HEIGHT-50)

        # Persistent hidden buffer for measuring layout
        self._buffer = tk.Text(self, wrap="word", bg="white")
        self._buffer.configure(padx=PAGE_MARGIN, pady=PAGE_MARGIN)
        self.define_tags(on_widget=self._buffer)
        self._buffer.place(x=-10000, y=-10000, width=WINDOW_WIDTH - 2 * PAGE_MARGIN, height=WINDOW_HEIGHT)
        self._buffer.config(state="normal")  # Keep editable for pagination

        # Display backend (will be set after widgets are laid out)
        self.display = TkDisplay(self.text_canvas, self.page_label, self.page_number_footer)

        # Load EPUB
        try:
            self.book = epub.read_epub(self.epub_path)
        except Exception as e:
            print(f"Error opening EPUB {self.epub_path}: {e}")
            self.book = None

        if self.book:
            self.spine_items = [item for item in self.book.get_items() if isinstance(item, epub.EpubHtml)]
            if not self.spine_items:
                self.spine_items = [item for item in self.book.get_items()]
        else:
            self.spine_items = []

        # State
        self.current_chapter = 0
        self.pages = []
        self.current_page = 0

        # Load first chapter safely
        self.after(100, lambda: self._safe_load_chapter(self.current_chapter))

        # Keyboard fallback
        self.bind_all("<Right>", lambda e: self.next_page())
        self.bind_all("<Left>", lambda e: self.prev_page())

        self.text_canvas.configure(font=(FONT_FAMILY_DEFAULT, FONT_SIZE_DEFAULT))
        self._buffer.configure(font=(FONT_FAMILY_DEFAULT, FONT_SIZE_DEFAULT))

    # ---------- Safe chapter load ----------
    def _safe_load_chapter(self, index):
        if not hasattr(self, "_buffer") or not self._buffer.winfo_exists():
            return
        self.load_chapter(index)

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
        self._buffer.config(state="normal")
        self._buffer.delete("1.0", tk.END)
        self.insert_html_into_buffer(html)
        self._buffer.config(state="disabled")

        self.update_idletasks()
        # Finish paging once geometry is ready
        if self.text_canvas.winfo_height() < 10:
            self.after(50, lambda: self._finish_paging(index))
        else:
            self._finish_paging(index)

    # ---------- Pagination ----------
    def _finish_paging(self, index):
        visible_w = self.text_canvas.winfo_width() or (WINDOW_WIDTH - 2 * PAGE_MARGIN)
        visible_h = self.text_canvas.winfo_height() or (WINDOW_HEIGHT - 2 * PAGE_MARGIN)

        self._buffer.place_configure(x=self.text_canvas.winfo_x(),
                                    y=self.text_canvas.winfo_y(),
                                    width=visible_w,
                                    height=visible_h)
        self.update_idletasks()
        self._buffer.update_idletasks()

        self.pages = self._build_pages()

        self._buffer.place_configure(x=-10000, y=-10000)
        self.current_chapter = index
        self.current_page = 0
        self.display_page()

    # ---------- Page display ----------
    def display_page(self):
        if not self.pages or not getattr(self, "_buffer", None) or not self._buffer.winfo_exists():
            return

        self.current_page = max(0, min(self.current_page, len(self.pages) - 1))
        start, end = self.pages[self.current_page]
        page_text = self._buffer.get(start, end)

        def apply_tags(widget):
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
                        widget.tag_add(tag, vis_start, vis_end)
                    except Exception:
                        pass

        try:
            self.display.draw_text(page_text, apply_tags)
        except Exception:
            self.text_canvas.config(state="normal")
            self.text_canvas.delete("1.0", tk.END)
            self.text_canvas.insert("1.0", page_text)
            self.text_canvas.config(state="disabled")

        chapter_text = f"Chapter {self.current_chapter + 1} of {len(self.spine_items)}"
        page_number_text = f"{self.current_page + 1} / {len(self.pages)}"
        try:
            self.display.update_footer(chapter_text, page_number_text)
        except Exception:
            pass

        try:
            self.display.focus()
        except Exception:
            pass

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
            toc_container = toc_nav.find_parent("div", class_="toc") or toc_nav
            self._insert_toc_block(toc_container)
            return

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
        heading = toc_container.find("h1") or toc_container.find("div", class_="toc-title")
        if heading:
            self._insert_text_with_tags(heading.get_text(strip=True), ["h1"], self._buffer)
            self._buffer.insert("end", "\n\n")

        nav = toc_container.find("nav") if toc_container else None
        ol = nav.find("ol") if nav and nav.find("ol") else (toc_container.find("ol") if toc_container else None)
        ul = nav.find("ul") if nav and nav.find("ul") else (toc_container.find("ul") if toc_container else None)
        list_tag = ol or ul
        if list_tag:
            self._insert_toc_list(list_tag, indent=0)
        else:
            links = toc_container.find_all("a") if toc_container else []
            for a in links:
                self._insert_text_with_tags(a.get_text(strip=True), [], self._buffer)
                self._buffer.insert("end", "\n")

    def _insert_toc_list(self, list_tag, indent=0):
        for li in list_tag.find_all("li", recursive=False):
            link = li.find("a")
            text = link.get_text(strip=True) if link else li.get_text(strip=True)
            self._insert_text_with_tags(" " * (indent * 4) + text, [], self._buffer)
            self._buffer.insert("end", "\n")
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
