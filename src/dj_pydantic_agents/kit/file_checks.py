"""Find the type of an uploaded file from its name and its bytes.

Also make a large image smaller. Pillow is optional (the extra "images"). With
no Pillow, an image stays as it is.
"""

import zipfile
from importlib.util import find_spec
from io import BytesIO
from pathlib import PurePath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from PIL.Image import Image

PNG = "image/png"
JPEG = "image/jpeg"
WEBP = "image/webp"
GIF = "image/gif"
PDF = "application/pdf"
DOC = "application/msword"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLS = "application/vnd.ms-excel"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Each media type that the package can check. A project selects its types
# from these in the ATTACHMENT_TYPES setting.
SUPPORTED_MEDIA_TYPES = (PNG, JPEG, WEBP, GIF, PDF, DOC, DOCX, XLS, XLSX)

_TYPES_BY_SUFFIX: Mapping[str, str] = {
    ".png": PNG,
    ".jpg": JPEG,
    ".jpeg": JPEG,
    ".webp": WEBP,
    ".gif": GIF,
    ".pdf": PDF,
    ".doc": DOC,
    ".docx": DOCX,
    ".xls": XLS,
    ".xlsx": XLSX,
}

# The suffix of a stored file. The stored name never holds the name of the user.
SUFFIXES: Mapping[str, str] = {
    PNG: ".png",
    JPEG: ".jpg",
    WEBP: ".webp",
    GIF: ".gif",
    PDF: ".pdf",
    DOC: ".doc",
    DOCX: ".docx",
    XLS: ".xls",
    XLSX: ".xlsx",
}

_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
# The part that each Office Open XML file must have.
_ZIP_PARTS: Mapping[str, str] = {DOCX: "word/document.xml", XLSX: "xl/workbook.xml"}

# Only an image larger than this gets smaller.
IMAGE_SHRINK_BYTES = 5 * 1024 * 1024
# The longest side of a smaller image. OpenAI fits an image in 2048 px.
IMAGE_MAX_SIDE = 2048
# Pillow reads the size from the header. A larger image is refused before it
# decodes, because a small file can decode to a very large image.
IMAGE_MAX_PIXELS = 80_000_000
# Pillow can change these formats. An animated GIF loses its frames.
_SAVE_FORMATS: Mapping[str, str] = {PNG: "PNG", JPEG: "JPEG", WEBP: "WEBP"}
_LOWER_QUALITY = 70
_PNG_AS_JPEG_QUALITY = 85


_NOT_OPEN = "The image does not open."


class FileCheckError(ValueError):
    """The file is not usable. The message tells the user why."""


def media_type_of(*, name: str, data: bytes) -> str | None:
    """The media type of the name suffix, if the bytes have that type.

    None for an unknown suffix, or for bytes of another type.
    """
    media_type = _TYPES_BY_SUFFIX.get(PurePath(name).suffix.lower())
    if media_type is None or not _has_type(data=data, media_type=media_type):
        return None
    return media_type


def accept_value(media_types: tuple[str, ...]) -> str:
    """The accept attribute of a file input: each media type and its suffixes."""
    suffixes = [
        suffix
        for suffix, media_type in _TYPES_BY_SUFFIX.items()
        if media_type in media_types
    ]
    return ",".join([*media_types, *suffixes])


def shrink_image(*, data: bytes, media_type: str) -> tuple[bytes, str]:
    """Make an image over IMAGE_SHRINK_BYTES smaller. Return the bytes and the type.

    The image first gets a size of IMAGE_MAX_SIDE at most. If it is still too
    large, a PNG changes to JPEG, and a JPEG or WebP gets a lower quality.
    Raise FileCheckError when no result is small enough.
    """
    if len(data) <= IMAGE_SHRINK_BYTES or not media_type.startswith("image/"):
        return data, media_type
    if find_spec("PIL") is None:
        return data, media_type
    if media_type not in _SAVE_FORMATS:
        msg = "A GIF image over 5 MB is not supported."
        raise FileCheckError(msg)
    image = _resized(data)
    for save_format, result_type, options in _attempts(media_type):
        result = _save(image=image, save_format=save_format, options=options)
        if len(result) <= IMAGE_SHRINK_BYTES:
            return result, result_type
    msg = "The image is too large, also after a resize."
    raise FileCheckError(msg)


def _has_type(*, data: bytes, media_type: str) -> bool:  # noqa: PLR0911
    match media_type:
        case "image/png":
            return data.startswith(b"\x89PNG\r\n\x1a\n")
        case "image/jpeg":
            return data.startswith(b"\xff\xd8\xff")
        case "image/gif":
            return data.startswith((b"GIF87a", b"GIF89a"))
        case "image/webp":
            return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        case "application/pdf":
            return data.startswith(b"%PDF-")
        case "application/msword" | "application/vnd.ms-excel":
            return data.startswith(_OLE_MAGIC)
        case _:
            return _has_zip_part(data=data, part=_ZIP_PARTS[media_type])


def _has_zip_part(*, data: bytes, part: str) -> bool:
    """Read only the list of names of the archive. Extract nothing."""
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            return part in archive.namelist()
    except zipfile.BadZipFile:
        return False


def _resized(data: bytes) -> Image:
    """Open the image and fit it in IMAGE_MAX_SIDE. Check the pixels first."""
    import PIL.Image  # noqa: PLC0415 - Pillow is optional
    import PIL.ImageOps  # noqa: PLC0415

    try:
        image: Image = PIL.Image.open(BytesIO(data))
        pixels = image.width * image.height
    except Exception as error:
        raise FileCheckError(_NOT_OPEN) from error
    if pixels > IMAGE_MAX_PIXELS:
        msg = "The image has too many pixels."
        raise FileCheckError(msg)
    try:
        image = PIL.ImageOps.exif_transpose(image) or image
        image.thumbnail((IMAGE_MAX_SIDE, IMAGE_MAX_SIDE))
    except Exception as error:
        raise FileCheckError(_NOT_OPEN) from error
    return image


def _attempts(media_type: str) -> tuple[tuple[str, str, dict[str, int]], ...]:
    save_format = _SAVE_FORMATS[media_type]
    if media_type == PNG:
        return (
            (save_format, PNG, {}),
            ("JPEG", JPEG, {"quality": _PNG_AS_JPEG_QUALITY}),
        )
    return (
        (save_format, media_type, {}),
        (save_format, media_type, {"quality": _LOWER_QUALITY}),
    )


def _save(*, image: Image, save_format: str, options: dict[str, int]) -> bytes:
    out = BytesIO()
    try:
        if save_format == "JPEG":
            image = _without_alpha(image)
        image.save(out, format=save_format, **options)
    except Exception as error:
        raise FileCheckError(_NOT_OPEN) from error
    return out.getvalue()


def _without_alpha(image: Image) -> Image:
    """JPEG has no alpha channel. Put the image on white, not on black."""
    import PIL.Image  # noqa: PLC0415 - Pillow is optional

    if image.mode in {"RGB", "L"}:
        return image
    converted = image.convert("RGBA")
    background = PIL.Image.new("RGB", converted.size, (255, 255, 255))
    background.paste(converted, mask=converted.getchannel("A"))
    return background
