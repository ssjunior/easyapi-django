# easyapi-django

A simple rest api generator for django based on models

API in 4 easy steps!

## Install

```
pip install easyapi-django
```

## Add middleware in Django settings

```
MIDDLEWARE = [
    ...
    'easyapi.ExceptionMiddleware',
]
```

## Create Resource based on your model

```
from easyapi import BaseResource

from your_models import YOUR_DJANGO_MODEL

class ResourceName(BaseResource):
    model = YOUR_DJANGO_MODEL
```

## Add to your routes url

```
from easyapi.routes import get_routes

from resourcefile import ResourceName

endpoints = {
    'endpointname(.\*)$': ResourceName,
}
routes = get_routes(endpoints)

urlpatterns = [
    ...
] + routes
```

Your api with GET, PUT, POST and DELETE is ready. Start using it

How easy and cool is that???

## FREE Bonus features

```
class ResourceName(BaseResource):
    model = YOUR_DJANGO_MODEL

    # return list results normalized
    normalize_list = True

    # define methods allowed
    allowed_methods = ['get', 'patch', 'post', 'delete']

    # define fields returned in list, if not define all fields are returned
    list_fields = ['field1', 'field2', 'field3']

    # return normalized fields for related models in list
    list_related_fields = {'field1': ['related_field1', 'related_field2']}

    # define fields that are allowed to be filtered
    filter_fields = [
        'field1',
        'field2'
    ]

    # define fields that are allowed to be searched
    search_fields = ['field1', 'field2', 'field3']

    # define fields that are allowed to be used in a order by
    order_fields = ['field1', 'field2']

    # define fields allowed to be updated
    update_fields = [
        'field1', 'field2'
    ]

    # define fields returned in a specific object
    edit_fields = [
        'field1', 'field2', 'field3', 'field3'
    ]
```
