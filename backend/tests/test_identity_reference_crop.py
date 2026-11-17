from pathlib import Path

from app.services.identity_reference.face_backend import (
    UnavailableFaceBackend,
    expanded_face_crop,
    select_primary_face,
)
from app.services.identity_reference.types import DetectedFace, PixelBox


def test_expanded_face_crop_stays_square_and_inside_image():
    crop = expanded_face_crop(
        image_width=1024,
        image_height=1024,
        face=PixelBox(x=390, y=260, width=240, height=300),
    )
    assert crop.width == crop.height
    assert 0 <= crop.x < crop.x + crop.width <= 1024
    assert 0 <= crop.y < crop.y + crop.height <= 1024
    assert crop.y <= 260


def test_expanded_face_crop_shifts_inside_near_edge():
    crop = expanded_face_crop(
        image_width=640,
        image_height=480,
        face=PixelBox(x=8, y=12, width=170, height=210),
    )
    assert crop.x == 0
    assert crop.y == 0
    assert crop.width == crop.height
    assert crop.x + crop.width <= 640
    assert crop.y + crop.height <= 480


def test_primary_face_prefers_area_then_center():
    faces = [
        DetectedFace(box=PixelBox(x=450, y=30, width=100, height=100)),
        DetectedFace(box=PixelBox(x=180, y=100, width=180, height=180)),
        DetectedFace(box=PixelBox(x=5, y=5, width=180, height=180)),
    ]
    selected = select_primary_face(faces, image_width=640, image_height=480)
    assert selected.box == PixelBox(x=180, y=100, width=180, height=180)


def test_unavailable_backend_reports_without_throwing(tmp_path: Path):
    backend = UnavailableFaceBackend("opencv_not_installed")
    assert backend.readiness().ready is False
    assert backend.detect(tmp_path / "portrait.png").status == "unavailable"
