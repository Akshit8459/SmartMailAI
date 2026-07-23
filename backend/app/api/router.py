from fastapi import APIRouter
from app.api.auth_routes import router as auth_router
from app.api.email_routes import router as email_router
from app.api.ai_routes import router as ai_router
from app.api.sync_routes import router as sync_router
from app.api.eval_routes import router as eval_router
from app.api.webhook_routes import router as webhook_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(email_router)
api_router.include_router(ai_router)
api_router.include_router(sync_router)
api_router.include_router(eval_router)
api_router.include_router(webhook_router)
