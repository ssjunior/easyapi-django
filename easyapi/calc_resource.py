import pytz

from .base import BaseResource
from .calc import get_results


class Metrics(BaseResource):
    allowed_methods = ['post']

    async def post(self, request):
        body = request.json
        timezone = pytz.timezone(self.user.get('timezone') or 'UTC')
        results = await get_results(timezone, body)
        return results
