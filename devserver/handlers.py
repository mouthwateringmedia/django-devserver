from devserver.middleware import DevServerMiddleware
from django.core.handlers.wsgi import WSGIHandler


class DevServerHandler(WSGIHandler):
    def load_middleware(self):
        super(DevServerHandler, self).load_middleware()

        i = DevServerMiddleware(self.get_response)

        if hasattr(self, '_request_middleware'):
            self._request_middleware.append(i.process_request)
        self._view_middleware.append(i.process_view)
        if hasattr(self, '_response_middleware'):
            self._response_middleware.append(i.process_response)
        self._exception_middleware.append(i.process_exception)
