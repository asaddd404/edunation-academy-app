"""Lesson video links: only a YouTube video id survives into storage."""

import pytest

from app.core.youtube import normalize_youtube_url, youtube_video_id
from app.models.category import Category, teacher_categories
from app.models.lesson import Lesson
from app.models.section import Section
from app.models.user import RoleEnum

VID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VID}",
        f"https://youtube.com/watch?v={VID}&t=42s&list=PL123",
        f"https://m.youtube.com/watch?v={VID}",
        f"https://youtu.be/{VID}?si=abc",
        f"https://www.youtube.com/embed/{VID}",
        f"https://www.youtube-nocookie.com/embed/{VID}",
        f"https://www.youtube.com/shorts/{VID}",
        f"youtube.com/watch?v={VID}",
        f"  https://youtu.be/{VID}  ",
    ],
)
def test_recognised_links(url):
    assert youtube_video_id(url) == VID
    assert normalize_youtube_url(url) == f"https://www.youtube.com/watch?v={VID}"


@pytest.mark.parametrize(
    "url",
    [
        "https://vimeo.com/123456",
        f"https://evil.example/watch?v={VID}",
        f"https://youtube.com.evil.example/watch?v={VID}",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ%22onload%3D",
        'javascript:alert(1)//youtube.com/watch?v=dQw4w9WgXcQ',
        "https://www.youtube.com/channel/UC123",
    ],
)
def test_everything_else_is_refused(url):
    assert youtube_video_id(url) is None
    with pytest.raises(ValueError):
        normalize_youtube_url(url)


def test_blank_means_remove_and_none_means_unchanged():
    assert normalize_youtube_url("") == ""
    assert normalize_youtube_url("   ") == ""
    assert normalize_youtube_url(None) is None


async def _lesson(db_session, teacher):
    category = Category(name="yt", slug="yt", is_active=True)
    db_session.add(category)
    await db_session.flush()
    await db_session.execute(teacher_categories.insert().values(teacher_id=teacher.id, category_id=category.id))
    section = Section(category_id=category.id, title="Раздел", order_index=0)
    db_session.add(section)
    await db_session.commit()
    return section


async def test_teacher_sets_changes_and_removes_a_video(client, db_session, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    section = await _lesson(db_session, teacher)
    login_as(teacher)

    created = await client.post(
        f"/api/v1/teacher/sections/{section.id}/lessons", json={"title": "Урок", "video_url": f"https://youtu.be/{VID}"}
    )
    assert created.status_code == 201
    assert created.json()["video_url"] == f"https://www.youtube.com/watch?v={VID}"
    lesson_id = created.json()["id"]

    bad = await client.patch(f"/api/v1/teacher/lessons/{lesson_id}", json={"video_url": "https://vimeo.com/1"})
    assert bad.status_code == 422

    untouched = await client.patch(f"/api/v1/teacher/lessons/{lesson_id}", json={"title": "Урок 1"})
    assert untouched.json()["video_url"] == f"https://www.youtube.com/watch?v={VID}"

    removed = await client.patch(f"/api/v1/teacher/lessons/{lesson_id}", json={"video_url": ""})
    assert removed.status_code == 200 and removed.json()["video_url"] is None
    assert (await db_session.get(Lesson, lesson_id)) is not None
