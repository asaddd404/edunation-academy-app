from fastapi import APIRouter

from app.api.v1 import admin, applications, auth, categories, content, ent, ent_teacher, homework, teacher_content, tests

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
api_router.include_router(ent.router)
