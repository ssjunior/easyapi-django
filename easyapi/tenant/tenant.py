from contextvars import ContextVar
import json
import os

from django.apps import apps
from django.contrib.auth.hashers import check_password
from django.db import connections
from redis import asyncio as aioredis

from ..exception import HTTPException


class AccountStatus():
    """Situações possíveis do banco de dados no sistema.

    Attributes:
        NORMAL (int): Conta ativa com todos os recursos do sistema liberados.
        CREATING_DATABASE (int): A conta se encontra em processo de criação.
        DATABASE_CREATION_ERROR (int): Ocorreu um erro na criação da conta.
        UPDATING_DATABASE (int): O database está em processo de migração
        DELETED (int): Conta removida e que não permite mais acesso ao sistema.
        WAITING_DELETION (int): Conta marcada para remoção futura, pelo script.
        OPTIONS (dict): Dicionário com os status e seus respectivos nomes.
        CHOICES (tuple): Tupla com status e nomes, para relação com os models.

    """
    NORMAL = 1
    DISABLED = 2
    FREE = 3
    DELETED = 4
    PAUSED = 5
    CREATING_DATABASE = 6
    DATABASE_CREATION_ERROR = 7

    OPTIONS = {
        NORMAL: 'Normal',
        DISABLED: 'Disabled',
        FREE: 'Waiting allocation',
        DELETED: 'Deleted',
        PAUSED: 'Paused',
        CREATING_DATABASE: 'Creating database',
        DATABASE_CREATION_ERROR: 'Database creation error',
    }
    CHOICES = tuple(OPTIONS.items())


try:
    from settings import TENANT_ACCOUNT_MODEL, TENANT_USER_MODEL, TENANT_DB_PREFIX
    tenant_model = apps.get_model(TENANT_USER_MODEL)
    account_model = apps.get_model(TENANT_ACCOUNT_MODEL)
except Exception:
    TENANT_USER_MODEL = None
    TENANT_DB_PREFIX = None
    TENANT_ACCOUNT_MODEL = None
    tenant_model = None
    account_model = None

db_state = ContextVar("db_state", default='default')


async def save_connection(account):
    account_db = f'{TENANT_DB_PREFIX}_{account.id}'
    db_state.set(account_db)

    if account_db in connections.databases:
        return connections.databases[account_db]

    connection = {
        'ATOMIC_REQUESTS': False,
        'ENGINE': 'django.db.backends.mysql',
        'NAME': account_db,
        'HOST': account.db.host,
        'USER': account.db.user,
        'PASSWORD': account.db.password,
        'CONN_MAX_AGE': 0,
        'CONN_HEALTH_CHECKS': False,
        'TIME_ZONE': None,
        'PORT': '',
        'AUTOCOMMIT': True,
        'OPTIONS': {
            'use_unicode': True,
            'charset': 'utf8mb4',
            'connect_timeout': 120,
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES', innodb_strict_mode=1"
        },
    }
    connections.databases[account_db] = connection

    REDIS_SERVER = os.environ['REDIS_SERVER']
    REDIS_DB = 1
    redis = await aioredis.Redis(
        host=REDIS_SERVER, db=REDIS_DB, decode_responses=True
    ).client()
    await redis.set(f'{TENANT_DB_PREFIX}:connections:{account.id}', json.dumps(connection))
    await redis.close()

    return account_db, connection


async def set_tenant(id):
    if id:
        account_db = f'{TENANT_DB_PREFIX}_{id}'
    else:
        account_db = 'default'

    if account_db not in connections.databases:
        account = await account_model.objects.filter(
            id=id,
        ).select_related('db').afirst()
        await save_connection(account)

    db_state.set(account_db)
    return account_db


async def get_master_user(email, password):
    user = await tenant_model.objects.using(
        'default'
    ).filter(
        email=email.lower().strip(),
    ).select_related(
        'account', 'account__db'
    ).filter(
        account__status_id__in=[
            AccountStatus.NORMAL,
        ]
    ).afirst()

    if user and check_password(password, user.password):
        if not user.account:
            raise HTTPException(400, 'Missing account')

        await save_connection(user.account)

        return user

    return None
