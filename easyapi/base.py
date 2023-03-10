# from typing import Any

import decimal
import importlib
import json
import os
import re
from functools import reduce
from urllib import parse

from asgiref.sync import sync_to_async
from django.db import connections
from django.db.models import Q
from django.forms.models import model_to_dict
from django.http import JsonResponse
from django.views import View
import operator
from redis import asyncio as aioredis

from .filters import Filter as OrmFilter
from .exception import HTTPException

from settings.env import REDIS_PREFIX

re_id = re.compile(r'(.*)\/(\d+)(\/.)?$')
search_regex = re.compile(r'__isnull|__gte|__lte|__lt|__gt|__startswith')


async def fake_tenant(*args, **kwargs):
    return 'default'


tenant = importlib.find_loader('tenant')
if tenant:
    tenant = importlib.import_module('tenant')
    set_tenant = tenant.set_tenant
else:
    set_tenant = fake_tenant


async def method_not_allowed(self, **kwargs):
    raise HTTPException(405, 'Method not allowed')


def decoder(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)


class BaseResource(View):
    authenticated = False
    allowed_methods = ['delete', 'get', 'patch', 'post']
    routes = []

    limit = 25
    page = 1
    order_by = 'id'
    count_results = False

    model = None
    queryset = None

    app_label = None
    model_name = None
    contextId = None

    fields = []
    all_fields = []
    fk_fields = []
    m2m_fields = []

    related_models = None
    list_related_fields = None
    many_to_many_models = {}

    filter_fields = []
    search_fields = []
    order_fields = []
    list_fields = []
    edit_fields = []
    edit_related_fields = {}
    edit_exclude_fields = ['_state']
    update_fields = []

    default_filter = None
    search_operator = 'icontains'

    obj = None
    obj_id = None
    data = None

    normalize_list = False

    def __init__(self):

        if self.model:
            fields = []
            for field in self.model._meta.get_fields():
                if not field.is_relation:
                    fields.append(field.name)
                    continue

                if field.concrete and field.many_to_many:
                    self.m2m_fields.append(field.name)
                    continue

                if field.concrete and field.many_to_one:
                    self.fk_fields.append(field.name)
                    continue

                if not field.concrete and field.one_to_many:
                    #     self.related_fields.append(field.name)
                    continue

            all_fields = [
                field.name for field in self.model._meta.local_fields]
            self.all_fields = all_fields + self.m2m_fields

            self.fields = fields
            self.list_fields = self.list_fields or fields

            if not self.edit_fields:
                self.edit_fields = fields  # + m2m_fields

            self.queryset = self.model.objects

    def get_method(self, request, args, kwargs):
        self.request = request
        for route in self.routes:
            match = re.search(route['path'], request.path)
            if match:
                allowed_methods = route.get('allowed_methods')
                return getattr(self, route['func']), match, allowed_methods

        return None, None, None

    async def dispatch(self, request, *args, **kwargs) -> None:

        REDIS_SERVER = os.environ['REDIS_SERVER']
        REDIS_DB = 1
        redis = await aioredis.Redis(
            host=REDIS_SERVER, db=REDIS_DB, decode_responses=True
        ).client()
        session_key = request.COOKIES.get('sid')

        prefix = f'{REDIS_PREFIX}:' if REDIS_PREFIX else ''
        session_key = f'{prefix}sessions:{session_key}'
        session = await redis.get(session_key)
        await redis.close()

        if self.authenticated and not session:
            raise HTTPException(401, 'Not authorized')

        session = json.loads(session)
        self.user = session['user']
        account = session.get('account')
        self.account_db = await set_tenant(account)

        method = "get" if request.method == "HEAD" else request.method.lower()

        # func é o método que será executado, caso exista rota personalizada
        func, match, allowed_methods = self.get_method(request, args, kwargs)

        if func:
            self.allowed_methods = allowed_methods or self.allowed_methods

        if self.authenticated and not self.user:
            raise HTTPException(401, 'Not authorized')

        if method not in self.allowed_methods:
            raise HTTPException(405, f'{method} not allowed')

        if not func:
            handler = getattr(self, method, method_not_allowed)

        self.build_filters(request)
        self.paginate(request)
        self.ordenate(request)

        if method in ['post', 'patch']:
            try:
                body = json.loads(request.body.decode('utf-8'))
            except Exception:
                # Patch/post sem body
                body = {}

            body = self.hydrate(body)
            request.json = body
        else:
            body = None

        if func:
            if method in ['post', 'patch']:
                response = await func(request, match=match.groups(), body=body)
            else:
                response = await func(request, match=match.groups())
        else:
            response = await handler(request)

        if type(response) == dict:
            response = self.serialize(response)

        return response

    def build_filters(self, request):
        if not self.queryset:
            return

        if hasattr(self, 'model_filter'):
            self.queryset = self.queryset.filter(**self.model_filter)

        if request.GET.get('search') and self.search_fields:
            filters = reduce(
                operator.or_, [
                    Q((f"{field}__{self.search_operator}",
                      request.GET.get('search')))
                    for field in self.search_fields
                ]
            )
            self.queryset = self.queryset.filter(filters)

        params = dict(request.GET)
        if self.filter_fields:
            filter = {}
            for key in params:
                if search_regex.search(key):
                    keys = key.split('__')
                    if len(keys) == 3:
                        field = f'{keys[0]}__{keys[1]}'
                    else:
                        field = keys[0]

                else:
                    field = key

                if field in self.filter_fields:
                    param = params[key][0]
                    if param.lower() == 'false':
                        param = False
                    elif param.lower() == 'true':
                        param = True

                    filter[key] = param

            self.queryset = self.queryset.filter(**filter)

        if (
            self.model and f'{self.model._meta.app_label}_{self.model._meta.model_name}' == 'core_tag'
        ):
            context = request.GET.get('context')
            if context:
                self.queryset = self.queryset.filter(context=context)

        tags = request.GET.get('tags')
        if tags and hasattr(self.model, 'tags'):
            tags_operator = request.GET.get('tags_operator', 'OR')
            tags_ids = tags.split(',')
            if tags_operator == 'OR':
                self.queryset = self.queryset.filter(tags__id__in=tags_ids)

            # try:
            #     tags = self.Meta.related_tag_model['model'].objects.filter(
            #         tag_id__in=tag_values
            #     ).values(self.Meta.related_tag_model['field']).annotate(count=Count('tag_id'))
            # except Exception:
            #     orm_filters['pk__in'] = []
            #     return orm_filters

            # if filters.get('tags_operator', 'AND').upper() == ConditionOperator.AND:
            #     total_tags = len(tag_values)
            #     tags = tags.filter(count=total_tags)

            # orm_filters['pk__in'] = [obj[self.Meta.related_tag_model['field']] for obj in tags]

    def ordenate(self, request):
        order_by = request.GET.get('order_by')
        if order_by and order_by.split('-')[-1] in self.order_fields:
            self.order_by = order_by

    def paginate(self, request):
        page = request.GET.get('page')
        if page:
            try:
                self.page = int(page)
            except Exception:
                pass

        limit = request.GET.get('limit')
        if limit:
            try:
                self.limit = int(limit)
            except Exception:
                pass

    #########################################################
    # Funçoes dentro do Resource
    #########################################################
    def serialize(self, result, **kwargs):
        response = kwargs.get('response')
        if type(result) == JsonResponse:
            return result

        if response:
            return response

        if isinstance(result, list):
            for row in result:
                self.dehydrate(row)
        else:
            result = self.dehydrate(result)

        return JsonResponse(result)

    def filter_objs(self):
        pass

    async def add_m2m(self, result):
        return await result

    async def alter_detail(self, result):
        return result

    async def alter_list(self, results):
        return results

    def hydrate(self, body):
        return body

    def dehydrate(self, response):
        return response

    #########################################################
    # GET
    #########################################################

    # count só se aplica a listagens
    @sync_to_async
    def count(self):
        count = 0
        self.count_results = 10
        if not hasattr(self.queryset, 'query'):
            self.queryset = self.queryset.all()

        query, params = self.queryset.query.sql_with_params()
        table = self.model._meta.db_table
        query = re.sub(
            r'^SELECT .*? FROM',
            f'SELECT count(DISTINCT {table}.id) FROM',
            query,
        )
        connection = connections[self.account_db]
        cursor = connection.cursor()
        cursor.execute(query, params)
        count = cursor.fetchone()[0]

        self.count_results = {'count': count}

    # filtro por segmento/filter só se aplica a listagens
    def get_filters(self, request):
        filter_ = request.GET.get('filter')

        if filter_ is None:
            return

        elif filter_:
            conditions = json.loads(filter_)

        if not conditions:
            return

        if OrmFilter:
            queryset = OrmFilter(
                self.model,
                self.user.timezone if self.user else 'UTC'
            )
            queryset = queryset.filter_by(conditions)
            self.queryset = queryset.distinct()

    async def return_results(self, results):
        if self.count_results:
            return self.count_results

        results = await self.alter_list(results)

        if self.normalize_list:
            normalized = {}
            for result in results:
                normalized[result['id']] = result
            return normalized

        result = {}
        if self.limit:
            params = {**self.request.GET} if self.request.GET else {}
            params['page'] = self.page + 1
            next_page = self.request.path + '?' + parse.urlencode(params)

            result['meta'] = {
                'page': self.page,
                'limit': self.limit,
                'next': next_page,
            }

            if self.page > 1:
                params['page'] = self.page - 1
                previous_page = self.request.path + \
                    '?' + parse.urlencode(params)
                result['meta']['previous'] = previous_page

        result['objects'] = results
        return result

    async def get_objs(self, request):
        self.get_filters(request)
        self.filter_objs()

        if request.GET.get('count'):
            return await self.count()

        if self.page > 0:
            start = (self.page - 1) * self.limit
        else:
            start = 0

        if self.list_related_fields:
            self.queryset = self.queryset.select_related(*self.list_related_fields.keys())
            for key, value in self.list_related_fields.items():
                self.list_fields.append(f'{key}__id')
                for field in value:
                    self.list_fields.append(f'{key}__{field}')

        self.queryset = self.queryset.order_by(
            self.order_by
        )

        if self.limit:
            self.queryset = self.queryset[start:start + self.limit]

        results = []
        async for result in self.queryset.values(*self.list_fields):
            if self.list_related_fields:
                for key, value in self.list_related_fields.items():
                    result[key] = {}
                    result[key]['id'] = result[f'{key}__id']
                    del result[f'{key}__id']
                    for field in value:
                        # if result.get(f'{key}__{field}'):
                        try:
                            result[key][field] = result[f'{key}__{field}']
                            del result[f'{key}__{field}']
                        except Exception as err:
                            print('ERRO', err)

            results.append(result)

        return results

    async def return_result(self, result):
        # if type(result) != dict:
        #     result = await self.add_m2m(result)

        for key in list(result):
            if self.edit_fields and key not in self.edit_fields and key != '_result':
                if result.get(key):
                    del result[key]

            if self.edit_exclude_fields and key in self.edit_exclude_fields:
                if result.get(key):
                    del result[key]

            if key not in self.edit_fields and key in self.fk_fields and key in result:
                result[key + '_id'] = {'id': result.pop(key)}

        result = await self.alter_detail(result)

        return result

    async def get_obj(self, id):
        related_models = list(self.edit_related_fields.keys())
        if related_models:
            self.queryset = self.queryset.select_related(*related_models)

        # para uso dentro dos resources
        self.obj = await self.queryset.filter(pk=id).afirst()

        if not self.obj:
            raise HTTPException(404, 'Object does not exist')

        results = {}
        for field in self.edit_fields:
            results[field] = getattr(self.obj, field, None)

        for model in related_models:
            obj = getattr(self.obj, model, None)
            if not obj:
                results[model] = None
                continue

            results[model] = {}
            for field in self.edit_related_fields[model]:
                results[model][field] = getattr(obj, field, None)

        return results

    async def _get_objs(self, request):
        data = await self.get_objs(request)
        return await self.return_results(data)

    async def get(self, request):
        match = re_id.match(request.path)
        if match:
            id = match[2]
            data = await self.get_obj(id)
            return self.serialize(data)
        else:
            data = await self._get_objs(request)
            return self.serialize(data)

    #########################################################
    # DELETE
    #########################################################
    async def delete_obj(self, id):
        try:
            await self.queryset.filter(pk=id).adelete()
        except Exception as err:
            raise HTTPException(400, err.__class__.__name__ + ': ' + err.__str__())

        return {'success': True, 'id': id, 'message': 'Deleted'}

    async def delete(self, request):
        match = re_id.match(request.path_info)
        if match:
            id = match[2]
            results = await self.delete_obj(id)
            return self.serialize(results)
        else:
            raise HTTPException(404, "Item not found")

    #########################################################
    # PATCH
    #########################################################

    def save_related_tags(self, tags):
        core_tag_model = self.model.tags.field.related_model
        tag_model = self.obj.tags.through
        tag_field = self.model.tags.field._m2m_name_cache + '_id'

        tags_ids = []
        # Crio as tags no contexto
        for tag in tags:
            tag, created = core_tag_model.objects.get_or_create(
                context=self.contextId,
                name=tag
            )
            tags_ids.append(tag.id)

        # Pegando os tags existentes e comparando com os tags enviados, para poder apagar somente
        # os tags que não foram enviados
        existing_tags = [
            tag for tag in
            tag_model.objects.filter(
                **{tag_field: self.obj.id}
            ).values_list('tag_id', flat=True)
        ]

        # Removendo tags
        tag_model.objects.filter(
            **{tag_field: self.obj.id, "tag_id__in": set(existing_tags) - set(tags_ids)}
        ).delete()

        # Inserindo tags
        insert_tags = set(tags_ids) - set(existing_tags)
        if insert_tags:
            tag_list = [
                tag_model(
                    **{"tag_id": tag_id, tag_field: self.obj.id}
                ) for tag_id in insert_tags
            ]
            tag_model.objects.bulk_create(tag_list)

    async def update_obj(self, id, body):
        keys = list(body.keys())
        allowed = False
        if self.update_fields:
            allowed = all(elem in self.update_fields for elem in keys)

        if not allowed:
            raise HTTPException(403, "Changes on this field is not allowed")

        try:
            self.obj = await self.queryset.aget(pk=id)
        except Exception:
            raise HTTPException(404, "Item not found")

        to_update = {}
        for key, value in body.items():
            if key == 'tags':
                self.save_related_tags(value)

            elif key == 'custom_attributes':
                for key, value in body['custom_attributes'].items():
                    self.obj.custom_attributes[key] = value

            else:
                field = getattr(self.model, key)
                if field.field.primary_key:
                    key += '_id'
                    value = int(value)
                to_update[key] = value
                setattr(self.obj, key, value)

        await self.model.objects.filter(pk=id).aupdate(**to_update)

        return await self.get_obj(id)

    async def _update_obj(self, id, body):
        self.obj_id = id
        result = await self.update_obj(id, body)
        return await self.return_result(result)

    async def patch(self, request):
        try:
            body = request.json
        except Exception:
            return HTTPException(
                400, 'Invalid body'
            )
        match = re_id.match(request.path_info)
        if match:
            results = await self._update_obj(match[2], body)
            return self.serialize(results)
        else:
            return HTTPException(404, "Item not found")

    #########################################################
    # POST
    #########################################################
    async def create_obj(self, request, body):
        to_save = {}
        user = self.user

        if user:
            if 'created_by' in self.all_fields:
                to_save['created_by_id'] = user.id
            if 'owner' in self.all_fields:
                to_save['owner_id'] = user.id

        for field in self.model._meta.local_fields:
            if field.primary_key:
                continue

            field_key = field.name
            if field.many_to_one:
                field_key = field.name + '_id'

            if body.get(field_key):
                to_save[field_key] = body[field_key]

        # try:
        obj = await self.model.objects.acreate(**to_save)
        # except Exception as err:
        #     error = err.__str__()
        #     return HTTPException(
        #         status=400, detail=error
        #     )

        self.obj = obj
        self.obj_id = obj.id
        result = await self.get_obj(obj.id)
        return await self.return_result(result)

    async def post(self, request):
        match = re_id.match(request.path_info)
        if match:
            return HTTPException(status=403, detail="Not allowed")

        body = request.json
        # try:
        result = await self.create_obj(request, body)
        # except Exception as err:
        #     error = err.__str__()
        #     return HTTPException(
        #         status=400, detail=error
        #     )

        return self.serialize(result)


class BaseTagsResource(BaseResource):

    async def add_m2m(self, result):
        super().add_m2m(result)

        if self.obj:
            result['tags'] = [tag.name async for tag in self.obj.tags.all()]

        return result


class BaseCustomResource(BaseResource):

    async def add_m2m(self, result):
        super().add_m2m(result)

        if not self.obj_id:
            return result

        fieldsets = {'default': {'name': 'Default',
                                 'order': 100000, 'fields': []}}
        cas_model = self.obj.custom_attributes.model
        cas = cas_model.objects.select_related(
            'fieldset'
        ).order_by('fieldset__order')

        has_type = False
        if hasattr(self.obj, 'card_type') and self.obj.card_type:
            has_type = True
            cas = cas.filter(
                card_type_id=self.obj.card_type.id).order_by('order')

        # definição dos custom fields
        fields = {}
        tmp = {}
        fieldsetId = 'default'
        cas = [ca async for ca in cas]
        for ca in cas:
            if has_type:
                if ca.presentation_id == 11:
                    fieldsetId = ca.presentation_name
                    fieldsets[fieldsetId] = {
                        'name': ca.presentation_name,
                        'order': ca.order,
                        'hide_if_empty': False,
                        'fields': []
                    }
                    continue

            else:
                if ca.fieldset:
                    fieldsetId = ca.fieldset.name
                    if fieldsetId not in fieldsets:
                        fieldsets[fieldsetId] = {
                            'name': ca.fieldset.name,
                            'order': ca.fieldset.order,
                            'hide_if_empty': ca.fieldset.hide_if_empty,
                            'fields': []
                        }
                else:
                    fieldsetId = 'default'

            fields[str(ca.id)] = model_to_dict(ca)
            tmp[ca.id] = fieldsetId

        filter = {}
        filter[
            self.obj.custom_attributes.source_field_name
        ] = self.obj.custom_attributes.instance

        # valores dos customs fields
        cas = [
            ca async for ca in self.obj.custom_attributes.through.objects.select_related(
                'custom_attribute', 'custom_attribute__fieldset'
            ).order_by('custom_attribute__fieldset__order').filter(**filter).all()
        ]
        for ca in cas:
            fields[str(ca.custom_attribute_id)]['value'] = ca.value
            result['ca__' + ca.custom_attribute.name] = ca.value

        fieldsetId = 'default'

        for _, field in fields.items():
            fieldId = field['id']
            fieldsetId = tmp[fieldId]
            fieldsets[fieldsetId]['fields'].append(field)

        fieldsets['default'] = fieldsets.pop('default')
        result['custom_attributes'] = fieldsets

        return result
