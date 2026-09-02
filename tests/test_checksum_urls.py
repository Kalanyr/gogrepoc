import importlib.util
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gogrepoc", ROOT / "gogrepoc.py")
gogrepoc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gogrepoc)


class Response(object):
    def __init__(self, url="", json_data=None, content=b"", headers=None, text=""):
        self.url = url
        self._json_data = json_data
        self.content = content
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._json_data


XML = (b'<file name="setup_game.exe" md5="0123456789abcdef0123456789abcdef" '
       b'chunks="1" timestamp="2026-01-01 00:00:00" total_size="4">'
       b'<chunk id="0" from="0" to="3" method="md5">0123456789abcdef0123456789abcdef</chunk>'
       b'</file>')


class ChecksumUrlTests(unittest.TestCase):
    def test_product_downloads_are_mapped_by_legacy_file_id(self):
        product = {"slug": "game", "downloads": {"installers": [{"files": [{
            "downlink": "https://api.gog.com/products/1/downlink/installer/en1installer0"
        }]}]}}
        with mock.patch.object(gogrepoc, "request", return_value=Response(json_data=product)):
            links = gogrepoc.fetch_product_download_links(object(), 1)

        self.assertEqual(
            links[("game", "en1installer0")],
            "https://api.gog.com/products/1/downlink/installer/en1installer0")
        self.assertEqual(
            gogrepoc.find_product_downlink(links, "/downloads/game/en1installer0"),
            links[("game", "en1installer0")])

    def test_expanded_dlc_downloads_use_their_slug(self):
        product = {"slug": "base", "downloads": {}, "expanded_dlcs": [{
            "slug": "dlc", "downloads": {"installers": [{"files": [{
                "downlink": "https://api.gog.com/products/2/downlink/installer/en1installer0"
            }]}]}
        }]}
        with mock.patch.object(gogrepoc, "request", return_value=Response(json_data=product)):
            links = gogrepoc.fetch_product_download_links(object(), 1)

        self.assertEqual(
            gogrepoc.find_product_downlink(links, "/downloads/dlc/en1installer0"),
            "https://api.gog.com/products/2/downlink/installer/en1installer0")

    def test_file_info_uses_api_checksum_url(self):
        resolver = "https://api.gog.com/products/1/downlink/installer/en1installer0"
        checksum = "https://cdn.example/setup_game.exe.xml?signed=xml"
        item = gogrepoc.AttrDict(
            href="https://www.gog.com/downloads/game/en1installer0", md5=None,
            name=None, size=None, updated=None, gog_data=gogrepoc.AttrDict(
                api_downlink=resolver))
        head = Response(
            url="https://cdn.example/setup_game.exe?signed=file",
            headers={"Content-Length": "4", "Last-Modified": "Wed, 01 Jan 2026 00:00:00 GMT"})

        def get(_session, url, **_kwargs):
            if url == resolver:
                return Response(json_data={"checksum": checksum})
            if url == checksum:
                return Response(content=XML, text=XML.decode("ascii"))
            raise AssertionError("unexpected URL: " + url)

        with mock.patch.object(gogrepoc, "request_head", return_value=head), \
                mock.patch.object(gogrepoc, "request", side_effect=get), \
                mock.patch.object(gogrepoc, "append_xml_extension_to_url_path",
                                  side_effect=AssertionError("legacy URL used")):
            gogrepoc.fetch_file_info(item, True, False, object())

        self.assertEqual(item.md5, "0123456789abcdef0123456789abcdef")

    def test_signed_prefix_lazily_loads_product_links_once(self):
        resolver = "https://api.gog.com/products/1/downlink/installer/en1installer0"
        checksum = "https://cdn.example/setup_game.exe.xml?signed=xml"
        product = {"slug": "game", "downloads": {"installers": [{"files": [{
            "downlink": resolver
        }]}]}}
        item = gogrepoc.AttrDict(
            href="https://www.gog.com/downloads/game/en1installer0", md5=None,
            name=None, size=None, updated=None, gog_data=gogrepoc.AttrDict(
                manualUrl="/downloads/game/en1installer0"))
        context = gogrepoc.AttrDict(product_id=1, download_links=None)
        head = Response(
            url=("https://gog-cdn.gcdn.co/secure/setup_game.exe?wsSecret=file"
                 "&wsTime=1234&prefix=/secure/setup_game.exe"),
            headers={"Content-Length": "4", "Last-Modified": "Wed, 01 Jan 2026 00:00:00 GMT"})

        def get(_session, url, **_kwargs):
            if url == "https://api.gog.com/products/1":
                return Response(json_data=product)
            if url == resolver:
                return Response(json_data={"checksum": checksum})
            if url == checksum:
                return Response(content=XML, text=XML.decode("ascii"))
            raise AssertionError("unexpected URL: " + url)

        with mock.patch.object(gogrepoc, "request", side_effect=get) as request_mock, \
                mock.patch.object(gogrepoc, "request_head", return_value=head), \
                mock.patch.object(gogrepoc, "append_xml_extension_to_url_path",
                                  side_effect=AssertionError("legacy URL used")):
            gogrepoc.fetch_file_info(item, True, False, object(), context)

        self.assertEqual(request_mock.call_count, 3)
        self.assertEqual(item.gog_data.api_downlink, resolver)
        self.assertIsNotNone(context.download_links)

    def test_fastly_path_does_not_load_product_api(self):
        item = gogrepoc.AttrDict(
            href="https://www.gog.com/downloads/game/en1installer0", md5=None,
            name=None, size=None, updated=None, gog_data=gogrepoc.AttrDict(
                manualUrl="/downloads/game/en1installer0"))
        context = gogrepoc.AttrDict(product_id=1, download_links=None)
        file_url = "https://cdn.fastly.example/setup_game.exe?signed=file"
        checksum = "https://cdn.fastly.example/setup_game.exe.xml?signed=file"
        head = Response(
            url=file_url,
            headers={"Content-Length": "4", "Last-Modified": "Wed, 01 Jan 2026 00:00:00 GMT"})

        with mock.patch.object(gogrepoc, "request_head", return_value=head), \
                mock.patch.object(gogrepoc, "request", return_value=Response(
                    content=XML, text=XML.decode("ascii"))) as request_mock:
            gogrepoc.fetch_file_info(item, True, False, object(), context)

        request_mock.assert_called_once_with(mock.ANY, checksum)
        self.assertIsNone(context.download_links)
        self.assertNotIn("api_downlink", item.gog_data)

    def test_chunk_tree_uses_api_checksum_url(self):
        resolver = "https://api.gog.com/products/1/downlink/installer/en1installer0"
        checksum = "https://cdn.example/setup_game.exe.xml?signed=xml"

        def get(_session, url, **_kwargs):
            if url == resolver:
                return Response(json_data={"checksum": checksum})
            if url == checksum:
                return Response(content=XML)
            raise AssertionError("unexpected URL: " + url)

        file_response = Response(url="https://cdn.example/setup_game.exe?signed=file")
        with mock.patch.object(gogrepoc, "request", side_effect=get), \
                mock.patch.object(gogrepoc, "append_xml_extension_to_url_path",
                                  side_effect=AssertionError("legacy URL used")):
            tree = gogrepoc.fetch_chunk_tree(file_response, object(), resolver)

        self.assertEqual(tree.attrib["chunks"], "1")
        self.assertEqual(len(list(tree)), 1)


if __name__ == "__main__":
    unittest.main()
