class ExceptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, _, exception):
        try:
            getattr(exception, "render")
        except AttributeError:
            return None

        return exception.render(exception)
