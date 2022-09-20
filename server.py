import json

import aiohttp
from aiohttp import web
from pydantic import BaseModel
from pydantic.error_wrappers import ValidationError
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from dotenv import dotenv_values
from typing import Optional
import bcrypt

env = dotenv_values(".env")
app = web.Application()
Base = declarative_base()
PG_DSN = f'postgresql+asyncpg://{env["DB_USER"]}:{env["DB_PASSWORD"]}@{env["DB_HOST"]}:{env["DB_PORT"]}/{env["DB_NAME"]}'
engine = create_async_engine(PG_DSN, echo=True)
Session = sessionmaker(bind=engine)


class HTTPError(web.HTTPException):
    def __init__(self, *, headers=None, reason=None, body=None, message=None):
        json_response = json.dumps({"error": message})
        super().__init__(
            headers=headers,
            reason=reason,
            body=body,
            text=json_response,
            content_type="application/json",
        )


class BadRequest(HTTPError):
    status_code = 400


class NotFound(HTTPError):
    status_code = 404


class CreateUserSchema(BaseModel):
    username: str
    email: str
    password: str


class PatchUserSchema(BaseModel):
    username: Optional[str]
    email: Optional[str]
    password: Optional[str]

    class Config:
        arbitrary_types_allowed = True


class CreateAdvertisementSchema(BaseModel):
    header: str
    description: str
    owner: int


class PatchAdvertisementSchema(BaseModel):
    header: Optional[str]
    description: Optional[str]
    owner: Optional[str]
    registration_time: Optional[str]




class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(60), nullable=False, unique=True)
    email = Column(String(100), nullable=False, unique=True)
    password = Column(String(100))


class Advertisement(Base):
    __tablename__ = 'advertisements'
    id = Column(Integer, primary_key=True)
    header = Column(String(64), nullable=False)
    description = Column(String, nullable=False)
    registration_time = Column(DateTime, server_default=func.now())
    owner = Column(ForeignKey(User.id))


async def init_orm(app: web.Application):
    print("Приложение стартовало")
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        async_session_maker = sessionmaker(
            engine, expire_on_commit=False, class_=AsyncSession
        )
        app.async_session_maker = async_session_maker
        yield
    print("Приложение завершило работу")


async def get_item(session, item_id, cls):
    response = await session.get(cls, item_id)
    if response is None:
        raise NotFound(message=f'{cls.__name__} does not exist')
    return response


class AdvView(web.View):

    async def get(self):
        adv_id = int(self.request.match_info["adv_id"])
        async with app.async_session_maker() as session:
            adv = await get_item(session, adv_id, Advertisement)
            return web.json_response(
                {
                    'header': adv.header,
                    'registration_time': adv.registration_time.isoformat(),
                    'description': adv.description,
                    'owner': adv.owner,
                }
            )

    async def post(self):
        adv_data = await self.request.json()
        try:
            json_data_validated = CreateAdvertisementSchema(**adv_data).dict()
        except ValidationError as err:
            raise BadRequest(message=err.errors())
        new_adv = Advertisement(**json_data_validated)
        async with app.async_session_maker() as session:
            try:
                session.add(new_adv)
                await session.commit()
                return web.json_response({"id": new_adv.id})
            except IntegrityError as er:
                raise BadRequest(message="Advertisement already exists")

    async def patch(self):
        adv_id = int(self.request.match_info["adv_id"])
        adv_data = await self.request.json()
        try:
            json_data_validated = PatchAdvertisementSchema(**adv_data).dict()
        except ValidationError as err:
            raise BadRequest(message=err.errors())
        async with app.async_session_maker() as session:
            adv = await get_item(session, adv_id, Advertisement)
            for column, value in json_data_validated.items():
                if value:
                    setattr(adv, column, value)
            session.add(adv)
            await session.commit()
            return web.json_response({"status": "success"})

    async def delete(self):
        adv_id = int(self.request.match_info["adv_id"])
        async with app.async_session_maker() as session:
            adv = await get_item(session, adv_id, Advertisement)
            await session.delete(adv)
            await session.commit()
            return web.json_response({"status": "success"})


class UserView(web.View):

    async def get(self):
        user_id = int(self.request.match_info["user_id"])
        async with app.async_session_maker() as session:
            user = await get_item(session, user_id, User)
            return web.json_response(
                {
                    "username": user.username,
                    "email": user.email
                }
            )

    async def post(self):
        user_data = await self.request.json()
        try:
            json_data_validated = CreateUserSchema(**user_data).dict()
        except ValidationError as err:
            raise BadRequest(message=err.errors())
        json_data_validated['password'] = (bcrypt.hashpw(

            json_data_validated['password'].encode(),
            salt=bcrypt.gensalt())).decode()
        new_user = User(**json_data_validated)
        async with app.async_session_maker() as session:
            try:
                session.add(new_user)
                await session.commit()
                return web.json_response({"id": new_user.id})
            except IntegrityError as er:
                raise BadRequest(message="user already exists")

    async def patch(self):
        user_id = int(self.request.match_info["user_id"])
        user_data = await self.request.json()
        try:
            json_data_validated = PatchUserSchema(**user_data).dict()
        except ValidationError as err:
            raise BadRequest(message=err.errors())
        async with app.async_session_maker() as session:
            user = await get_item(session, user_id, User)
            for column, value in json_data_validated.items():
                if value:
                    setattr(user, column, value)
            session.add(user)
            await session.commit()
            return web.json_response({"status": "success"})


    async def delete(self):
        user_id = int(self.request.match_info["user_id"])
        async with app.async_session_maker() as session:
            user = await get_item(session, user_id, User)
            await session.delete(user)
            await session.commit()
            return web.json_response({"status": "success"})


app.add_routes([web.get("/advertisement/{adv_id:\d+}", AdvView)])
app.add_routes([web.patch("/advertisement/{adv_id:\d+}", AdvView)])
app.add_routes([web.delete("/advertisement/{adv_id:\d+}", AdvView)])
app.add_routes([web.post("/advertisement", AdvView)])

app.add_routes([web.get("/user/{user_id:\d+}", UserView)])
app.add_routes([web.patch("/user/{user_id:\d+}", UserView)])
app.add_routes([web.delete("/user/{user_id:\d+}", UserView)])
app.add_routes([web.post("/user", UserView)])
app.cleanup_ctx.append(init_orm)
web.run_app(app)
