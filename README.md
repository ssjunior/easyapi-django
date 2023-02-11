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

# Add to your routes url

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
