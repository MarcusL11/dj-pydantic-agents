from unittest_parametrize import param
from unittest_parametrize import parametrize

from dj_pydantic_agents.contrib.datastar.templatetags.djpa import djpa_documents
from dj_pydantic_agents.contrib.datastar.templatetags.djpa import djpa_file_badge
from dj_pydantic_agents.contrib.datastar.templatetags.djpa import djpa_images
from tests.builders import an_attachment
from tests.testcases import SimpleTestCase


class TestFileBadge(SimpleTestCase):
    @parametrize(
        ("media_type", "badge"),
        [
            param("application/pdf", "PDF", id="pdf"),
            param(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "DOCX",
                id="docx",
            ),
            param("application/vnd.ms-excel", "XLS", id="xls"),
            param("image/jpeg", "JPG", id="jpeg"),
            param("text/plain", "FILE", id="unknown"),
        ],
    )
    def test_gives_the_short_type(self, media_type, badge):
        assert djpa_file_badge(media_type) == badge


class TestFileGroups(SimpleTestCase):
    def test_splits_the_images_from_the_documents_in_their_order(self):
        first_image = an_attachment(attachment_id="att_1", is_image=True)
        document = an_attachment(attachment_id="att_2")
        second_image = an_attachment(attachment_id="att_3", is_image=True)
        files = (first_image, document, second_image)

        assert djpa_images(files) == [first_image, second_image]
        assert djpa_documents(files) == [document]
