"""
Document -> HTML converter.

Converts .docx (and plain .txt/.html) into clean HTML with images
embedded as base64 data-URIs, so the whole article can be injected
into the VC.ru editor in one shot, preserving formatting and pictures.

Works on raw bytes: the file is read by the page itself (FileReader) and
handed over as base64, so no native file dialog is involved.
"""
import base64
import html
import io
import os


def convert_to_html(path: str) -> dict:
    """Convert a file on disk. Kept for local runs and tests."""
    with open(path, "rb") as f:
        data = f.read()
    return convert_bytes(os.path.basename(path), data)


def convert_bytes(name: str, data: bytes) -> dict:
    """
    Return {'title': str, 'html': str, 'images': int}.
    Raises ValueError for unsupported types.
    """
    ext = os.path.splitext(name)[1].lower()
    if ext == ".docx":
        return _convert_docx(io.BytesIO(data), name)
    if ext in (".htm", ".html"):
        return _convert_html(data, name)
    if ext in (".txt", ".md"):
        return _convert_text(data, name)
    raise ValueError(
        f"неподдерживаемый тип файла: {ext}. Нужен .docx, .html или .txt")


def _convert_docx(stream, name: str) -> dict:
    import mammoth

    image_count = {"n": 0}

    def _img_handler(image):
        image_count["n"] += 1
        with image.open() as f:
            data = f.read()
        b64 = base64.b64encode(data).decode("ascii")
        ctype = image.content_type or "image/png"
        return {"src": f"data:{ctype};base64,{b64}"}

    style_map = """
        p[style-name='Title'] => h1:fresh
        p[style-name='Heading 1'] => h1:fresh
        p[style-name='Heading 2'] => h2:fresh
        p[style-name='Heading 3'] => h3:fresh
        p[style-name='Quote'] => blockquote:fresh
    """
    result = mammoth.convert_to_html(
        stream,
        style_map=style_map,
        convert_image=mammoth.images.img_element(_img_handler),
    )
    body = result.value
    title = _guess_title(body) or _basename_title(name)
    return {"title": title, "html": body, "images": image_count["n"]}


def _convert_html(data: bytes, name: str) -> dict:
    body = data.decode("utf-8", errors="replace")
    title = _guess_title(body) or _basename_title(name)
    return {"title": title, "html": body, "images": body.count("<img")}


def _convert_text(data: bytes, name: str) -> dict:
    raw = data.decode("utf-8", errors="replace")
    paras = [p.strip() for p in raw.split("\n\n") if p.strip()]
    body = "\n".join(f"<p>{html.escape(p)}</p>" for p in paras)
    return {"title": _basename_title(name), "html": body, "images": 0}


def _guess_title(body: str) -> str:
    """Pull first <h1> text as the title, if present."""
    low = body.lower()
    i = low.find("<h1")
    if i == -1:
        return ""
    start = body.find(">", i)
    end = low.find("</h1>", start)
    if start == -1 or end == -1:
        return ""
    inner = body[start + 1:end]
    # strip any nested tags
    text = ""
    skip = False
    for ch in inner:
        if ch == "<":
            skip = True
        elif ch == ">":
            skip = False
        elif not skip:
            text += ch
    return html.unescape(text).strip()


def _basename_title(name: str) -> str:
    base = os.path.splitext(os.path.basename(name))[0]
    return base.strip() or "Новая статья"
