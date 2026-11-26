"""Stored image_url → bare image filename, for every shape the column has held."""
import pytest

from app.graphql.resolver_helpers import image_filename_from_url


@pytest.mark.parametrize("url, expected", [
    (None, None),
    ("", None),
    ("images/sv_12_ab12cd34.jpg", "sv_12_ab12cd34.jpg"),                 # current shape
    ("/app/data/images/sv_12.jpg", "sv_12.jpg"),                         # old absolute path
    ("backend/data/images/sub/sv_12.jpg", "sub/sv_12.jpg"),
    ("https://example.invalid/streetview/sv_12.jpg", "sv_12.jpg"),      # not yet downloaded
    ("some/other/dir/sv_12.jpg", "sv_12.jpg"),
    ("sv_12.jpg", "sv_12.jpg"),
])
def test_image_filename_from_url(url, expected):
    assert image_filename_from_url(url) == expected
