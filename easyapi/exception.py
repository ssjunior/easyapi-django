from django.http import JsonResponse


class HTTPException(Exception):

    def render(self, exception):
        (status, detail) = exception.args
        return JsonResponse({'success': False, 'status': status, 'detail': detail}, status=status)
