from fastapi import APIRouter

from app.api.v1 import (
    admin,
    applications,
    auth,
    categories,
    content,
    ent,
    ent_teacher,
    homework,
    notifications,
    profile,
    teacher_content,
    tests,
    video,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(categories.router)
api_router.include_router(applications.router)
api_router.include_router(admin.router)
api_router.include_router(teacher_content.router)
api_router.include_router(content.router)
api_router.include_router(tests.router)
api_router.include_router(homework.router)
api_router.include_router(ent_teacher.router)
api_router.include_router(ent.public_router)
api_router.include_router(ent.router)
api_router.include_router(video.router)
api_router.include_router(notifications.router)
api_router.include_router(profile.router)
