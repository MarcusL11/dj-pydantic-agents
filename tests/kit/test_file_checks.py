import io
import os
import zipfile
from unittest import mock

from PIL import Image
from unittest_parametrize import param
from unittest_parametrize import parametrize

from dj_pydantic_agents.kit import file_checks
from dj_pydantic_agents.kit.file_checks import DOC
from dj_pydantic_agents.kit.file_checks import DOCX
from dj_pydantic_agents.kit.file_checks import GIF
from dj_pydantic_agents.kit.file_checks import IMAGE_MAX_SIDE
from dj_pydantic_agents.kit.file_checks import IMAGE_SHRINK_BYTES
from dj_pydantic_agents.kit.file_checks import JPEG
from dj_pydantic_agents.kit.file_checks import PDF
from dj_pydantic_agents.kit.file_checks import PNG
from dj_pydantic_agents.kit.file_checks import WEBP
from dj_pydantic_agents.kit.file_checks import XLS
from dj_pydantic_agents.kit.file_checks import XLSX
from dj_pydantic_agents.kit.file_checks import FileCheckError
from dj_pydantic_agents.kit.file_checks import accept_value
from dj_pydantic_agents.kit.file_checks import media_type_of
from dj_pydantic_agents.kit.file_checks import shrink_image
from tests.testcases import SimpleTestCase

OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 8


def office_file(part: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr(part, "<xml/>")
    return out.getvalue()


def image_bytes(*, size: tuple[int, int], image_format: str, noise: bool) -> bytes:
    if noise:
        image = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3))
    else:
        image = Image.new("RGB", size, "white")
    out = io.BytesIO()
    image.save(out, format=image_format)
    return out.getvalue()


class TestMediaTypeOf(SimpleTestCase):
    @parametrize(
        ("name", "data", "expected"),
        [
            param("dial.PNG", b"\x89PNG\r\n\x1a\n...", PNG, id="png"),
            param("dial.jpeg", b"\xff\xd8\xff\xe0...", JPEG, id="jpeg"),
            param("dial.webp", b"RIFF\0\0\0\0WEBPVP8 ", WEBP, id="webp"),
            param("dial.gif", b"GIF89a...", GIF, id="gif"),
            param("invoice.pdf", b"%PDF-1.7", PDF, id="pdf"),
            param("note.doc", OLE, DOC, id="doc"),
            param("stock.xls", OLE, XLS, id="xls"),
            param("note.docx", office_file("word/document.xml"), DOCX, id="docx"),
            param("stock.xlsx", office_file("xl/workbook.xml"), XLSX, id="xlsx"),
        ],
    )
    def test_the_bytes_confirm_the_suffix(self, name, data, expected):
        assert media_type_of(name=name, data=data) == expected

    @parametrize(
        ("name", "data"),
        [
            param("invoice.pdf", b"\x89PNG\r\n\x1a\n", id="png_named_pdf"),
            param("note.docx", office_file("xl/workbook.xml"), id="xlsx_named_docx"),
            param("note.docx", b"PK\x03\x04 broken", id="broken_zip"),
            param("tool.exe", b"MZ", id="unknown_suffix"),
            param("README", b"%PDF-1.7", id="no_suffix"),
        ],
    )
    def test_other_bytes_or_an_unknown_suffix_give_none(self, name, data):
        assert media_type_of(name=name, data=data) is None


class TestShrinkImage(SimpleTestCase):
    def test_a_small_image_does_not_change(self):
        data = image_bytes(size=(10, 10), image_format="PNG", noise=False)

        assert shrink_image(data=data, media_type=PNG) == (data, PNG)

    def test_a_large_photo_as_png_becomes_a_smaller_jpeg(self):
        data = image_bytes(size=(3000, 2000), image_format="PNG", noise=True)
        assert len(data) > IMAGE_SHRINK_BYTES

        result, media_type = shrink_image(data=data, media_type=PNG)

        assert media_type == JPEG
        assert len(result) <= IMAGE_SHRINK_BYTES
        with Image.open(io.BytesIO(result)) as image:
            assert max(image.size) == IMAGE_MAX_SIDE

    def test_a_large_gif_is_refused(self):
        data = b"GIF89a" + b"\0" * (IMAGE_SHRINK_BYTES + 1)

        with self.assertRaisesRegex(FileCheckError, "GIF"):
            shrink_image(data=data, media_type=GIF)

    def test_too_many_pixels_are_refused_before_a_decode(self):
        small = io.BytesIO()
        Image.new("1", (9000, 9000)).save(small, format="PNG")
        data = small.getvalue() + b"\0" * IMAGE_SHRINK_BYTES

        with self.assertRaisesRegex(FileCheckError, "pixels"):
            shrink_image(data=data, media_type=PNG)

    def test_a_broken_image_is_refused(self):
        data = b"\x89PNG\r\n\x1a\n" + b"\0" * IMAGE_SHRINK_BYTES

        with self.assertRaisesRegex(FileCheckError, "does not open"):
            shrink_image(data=data, media_type=PNG)

    def test_with_no_pillow_a_large_image_does_not_change(self):
        data = b"\x89PNG\r\n\x1a\n" + b"\0" * IMAGE_SHRINK_BYTES

        with mock.patch.object(file_checks, "find_spec", return_value=None):
            assert shrink_image(data=data, media_type=PNG) == (data, PNG)

    def test_a_document_does_not_change(self):
        data = b"%PDF-1.7" + b"\0" * IMAGE_SHRINK_BYTES

        assert shrink_image(data=data, media_type=PDF) == (data, PDF)


class TestAcceptValue(SimpleTestCase):
    def test_has_the_types_and_their_suffixes(self):
        assert accept_value((JPEG, PDF)) == "image/jpeg,application/pdf,.jpg,.jpeg,.pdf"

    def test_no_types_give_an_empty_value(self):
        assert accept_value(()) == ""
