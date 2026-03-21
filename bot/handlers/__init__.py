from aiogram import Router

from handlers import common

root_router = Router()
root_router.include_router(common.router)
