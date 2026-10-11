from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_smorest import Api


db = SQLAlchemy()
jwt = JWTManager()
api = Api()
