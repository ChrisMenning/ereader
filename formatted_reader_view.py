import tkinter as tk
from ebooklib import epub
from bs4 import BeautifulSoup, NavigableString, Tag

WINDOW_WIDTH, WINDOW_HEIGHT = 800, 480
FONT_SIZE_DEFAULT = 14
FONT_FAMILY_DEFAULT = "DejaVuSans"

BLOCK_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre", "div")
INLINE_BOLD = ("strong", "b")
INLINE_ITALIC = ("em", "i")


class ReaderWindow(tk.Frame):
    """
    Previously was a Toplevel. Now a Frame so it can be embedded into another window.
    Usage: reader = ReaderWindow(parent_frame, epub_path); reader.pack(fill='both', expand=True)
    """

    def __init__(self, master, epub_path):
        # Initialize as a Frame so caller controls packing
        super().__init__(master, bg="white", width=WINDOW_WIDTH, height=WINDOW_HEIGHT)

        # Scrollable Text widget
        self.text_canvas = tk.Text(self, wrap="word", bg="white")
        self.scrollbar = tk.Scrollbar(self, command=self.text_canvas.yview)
        self.text_canvas.config(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.text_canvas.pack(side="left", fill="both", expand=True)

        # Define tags
        self.define_tags()

        # Load EPUB
        # Allow epub_path to be either Path or string
        self.book = epub.read_epub(epub_path)
        # safest: include EpubHtml items (works across versions)
        self.spine_items = [item for item in self.book.get_items() if isinstance(item, epub.EpubHtml)]
        if not self.spine_items:
            self.spine_items = [item for item in self.book.get_items()]

        # debug: list chapter names in console
        # print(f"Loaded {len(self.spine_items)} chapters:")
        # for i, item in enumerate(self.spine_items):
        #     print(i, item.get_name())

        self.current_chapter = 0
        self.load_chapter(self.current_chapter)

        # bind navigation to the text widget (so frame doesn't need to be focused)
        self.text_canvas.bind("<Right>", lambda e: self.next_chapter())
        self.text_canvas.bind("<Left>", lambda e: self.prev_chapter())
        # give text widget focus so arrow keys work
        self.text_canvas.focus_set()

    def define_tags(self):
        self.text_canvas.tag_configure("bold", font=(FONT_FAMILY_DEFAULT, FONT_SIZE_DEFAULT, "bold"))
        self.text_canvas.tag_configure("italic", font=(FONT_FAMILY_DEFAULT, FONT_SIZE_DEFAULT, "italic"))
        self.text_canvas.tag_configure("bold_italic", font=(FONT_FAMILY_DEFAULT, FONT_SIZE_DEFAULT, "bold italic"))
        self.text_canvas.tag_configure("h1", font=(FONT_FAMILY_DEFAULT, 20, "bold"))
        self.text_canvas.tag_configure("h2", font=(FONT_FAMILY_DEFAULT, 18, "bold"))
        self.text_canvas.tag_configure("h3", font=(FONT_FAMILY_DEFAULT, 16, "bold"))
        # ensures there's a baseline font tag you can reuse
        self.text_canvas.tag_configure("base", font=(FONT_FAMILY_DEFAULT, FONT_SIZE_DEFAULT))

    def load_chapter(self, index):
        self.text_canvas.delete("1.0", tk.END)
        if 0 <= index < len(self.spine_items):
            item = self.spine_items[index]
            try:
                # Some ebooklib versions return bytes, some str
                content = item.get_content()
                if isinstance(content, bytes):
                    html = content.decode("utf-8", errors="ignore")
                else:
                    html = str(content)
            except Exception as e:
                print(f"Error reading item {getattr(item, 'get_name', lambda: 'unknown')()}: {e}")
                html = "<p>[Could not load content]</p>"

            self.insert_html(html)
            self.current_chapter = index

            title = self.book.get_metadata('DC', 'title')
            # If caller wants title, they can query self.book; don't set window title here.

    # ---------- HTML -> Text insertion ----------
    def insert_html(self, html_content):
        soup = BeautifulSoup(html_content, "html.parser")
        # Find all block tags in document order
        blocks = soup.find_all(BLOCK_TAGS)

        # Filter out block elements that have a block ancestor (we only want lowest-level blocks)
        filtered = []
        for b in blocks:
            if any((ancestor.name in BLOCK_TAGS) for ancestor in b.parents if isinstance(ancestor, Tag)):
                parent = b.find_parent(BLOCK_TAGS)
                if parent is not None and parent is not b and parent.name != "body":
                    continue
            filtered.append(b)

        # If filtered ended up empty (some EPUBs structure differently), fallback to top-level body children
        if not filtered:
            body = soup.body or soup
            for child in body.children:
                if isinstance(child, Tag):
                    filtered.append(child)

        # Insert each block
        for blk in filtered:
            # Determine a readable text for debug and check emptiness
            block_text = blk.get_text(separator=" ", strip=True)
            if not block_text:
                continue

            # Insert inline content respecting inline styles
            self.insert_inline(blk)

            # Ensure a blank line after block
            self.text_canvas.insert("end", "\n")

    def insert_inline(self, node, active_tags=None):
        """
        Recursively insert text from node (Tag or NavigableString) into the Text widget,
        applying tags for bold/italic/inline fonts.
        """
        if active_tags is None:
            active_tags = []

        # If it's just a string, insert with current tags
        if isinstance(node, NavigableString):
            s = str(node)
            if not s.strip():
                return
            self._insert_text_with_tags(s, active_tags)
            return

        # If it's a Tag, update active_tags based on this tag
        new_tags = list(active_tags)

        # Bold/italic detection
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

        # Inline style: font-family
        style = node.get("style", "") if isinstance(node, Tag) else ""
        if "font-family" in style:
            try:
                font_name = style.split("font-family:")[1].split(";")[0].strip().strip('"').strip("'")
                tag_name = f"font_{font_name}"
                if tag_name not in self.text_canvas.tag_names():
                    # create a tag for this font fallback to default size
                    self.text_canvas.tag_configure(tag_name, font=(font_name, FONT_SIZE_DEFAULT))
                new_tags.append(tag_name)
            except Exception:
                pass

        # If this node itself is a block-level heading, add its tag (h1/h2/h3)
        if tagname in ("h1", "h2", "h3"):
            new_tags.append(tagname)

        # Recurse children in order
        for child in node.children:
            if isinstance(child, (Tag, NavigableString)):
                self.insert_inline(child, new_tags)

    def _insert_text_with_tags(self, text, tags):
        # Clean text and replace excessive whitespace
        txt = text.replace("\r", "").replace("\n", " ")
        # If it's just spaces, don't insert
        if not txt.strip():
            return
        start = self.text_canvas.index("end-1c")
        self.text_canvas.insert("end", txt)
        end = self.text_canvas.index("end-1c")
        # Apply all tags
        for tag in tags:
            # normalize combined bold_italic if exists
            if tag == "bold_italic" and "bold_italic" not in self.text_canvas.tag_names():
                # try to fallback by applying both bold and italic
                if "bold" in self.text_canvas.tag_names():
                    self.text_canvas.tag_add("bold", start, end)
                if "italic" in self.text_canvas.tag_names():
                    self.text_canvas.tag_add("italic", start, end)
                continue
            self.text_canvas.tag_add(tag, start, end)

    def next_chapter(self):
        if self.current_chapter + 1 < len(self.spine_items):
            self.load_chapter(self.current_chapter + 1)

    def prev_chapter(self):
        if self.current_chapter - 1 >= 0:
            self.load_chapter(self.current_chapter - 1)


# If you need a quick standalone test, run a tiny snippet in a separate file that creates a root,
# packs this frame and calls ReaderWindow(root, "path/to/book.epub").pack(fill='both', expand=True)
