from django.urls import path, re_path
from django.http import HttpResponse

from .calc_resource import Metrics


def get_route(route, view):
    if hasattr(view, 'as_view'):
        view = view.as_view()
        return re_path(rf'{route}', view)

    return path(route, view)


def get_routes(endpoints):

    def docs(request, *args, **kwargs):
        for route, view in endpoints.items():
            print(route, view)
            print(view.model)
            print(view.__dict__)
            methods = view.allowed_methods
            edit_fields = view.edit_fields
            list_fields = view.edit_fields
            update_fields = view.update_fields
            print(methods, edit_fields, list_fields, update_fields)

            model = view.model
            if model:
                print(model.__dict__)
                print(view.fields)

        return HttpResponse('Docs')

    return [
        get_route(key, value) for key, value in endpoints.items()
    ] + [
        path('docs', docs),
        path('metrics', Metrics.as_view())
    ]
