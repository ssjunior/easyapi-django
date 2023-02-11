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

### Count

By default in list calls, the api does not return the total of objects due to slow count in innodb tables used in MySql,
but, it is very easy to get count objects simple add

```
?count=true
```

at your request. The api will return the total count of objects and will consider whatever filter or search applied

```
{
    count: 90
}
```

### Search

To search you can use any field defined above in search_fields.
The search will be applied in all fields defined using OR.

```
?search=value
```

### Filter

To filter just use querystrings. The filter will only be applied in defined fields above in filter_fields.

```
?field_name=value
?field_name__lte=value
?field_name__startswith=value
```

you can filter using the following modifiers

```
__isnull|__gte|__lte|__lt|__gt|__startswith
```

You can combine filters, search and count in the same get. You can search and filter in related models/fields too.

### Pagination

You have a free pagination system using easyapi. The default number of results is 25 and the default order uses id. You can change this values per Resource.

```
class ResourceName(BaseResource):
    model = YOUR_DJANGO_MODEL

    limit = 25
    order_by = 'id'

```

If you set you limit to 0, all records will be returned.

To paginate just add to your call

```
?page=value
```

you can chage the default values dinamically too:

```
?page=value&limit=value&order_by=(field_name|-field_name)
```

## Waittttt, there is more FREE Bonus

You can add relative endpoints very easy, just add a new route and the funcion that you want to call with the allowed methods.
In the examples below we are creating 2 endpoints routes: accept and refuse that will call 2 functions (accept and refuse) that should return a response.

```
class ResourceName(BaseResource):
    model = YOUR_DJANGO_MODEL

    routes = [
            {
                'path': r'(\d*)/accept$',
                'func': 'accept',
                'allowed_methods': ['patch']
            },
            {
                'path': r'(\d*)/refuse$',
                'func': 'refuse',
                'allowed_methods': ['delete']
            },
    ]
```
