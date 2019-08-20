import functools
import gc
import tracemalloc
from datetime import datetime

from devserver.modules import DevServerModule
from devserver.settings import DEVSERVER_AUTO_PROFILE
from devserver.utils.time import ms_from_timedelta
from past.utils import old_div


class ProfileSummaryModule(DevServerModule):
    """
    Outputs a summary of cache events once a response is ready.
    """

    logger_name = 'profile'

    def process_init(self, request):
        self.start = datetime.now()

    def process_complete(self, request):
        duration = datetime.now() - self.start

        self.logger.info('Total time to render was %.2fs', old_div(ms_from_timedelta(duration), 1000))


class LeftOversModule(DevServerModule):
    """
    Outputs a summary of events the garbage collector couldn't handle.
    """
    # TODO: Not even sure this is correct, but the its a general idea

    logger_name = 'profile'

    def process_init(self, request):
        gc.enable()
        gc.set_debug(gc.DEBUG_SAVEALL)

    def process_complete(self, request):
        gc.collect()
        self.logger.info('%s objects left in garbage', len(gc.garbage))


class MemoryUseModule(DevServerModule):
    """
    Outputs a summary of memory usage of the course of a request.
    """
    logger_name = 'memory'

    def __init__(self, request):
        super(MemoryUseModule, self).__init__(request)
        # self.old_summary = self.get_summary()
        tracemalloc.start()

    def process_complete(self, request):
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')
        self.logger.info("[Top 10 Memory Use]")
        for stat in top_stats[:10]:
            self.logger.info(stat)


try:
    from line_profiler import LineProfiler
except ImportError:
    import warnings

    class LineProfilerModule(DevServerModule):

        def __new__(cls, *args, **kwargs):
            warnings.warn('LineProfilerModule requires line_profiler to be installed.')
            warnings.warn('run: ')
            warnings.warn('$ cd ../')
            warnings.warn('$ git clone https://github.com/rkern/line_profiler.git')
            warnings.warn('$ find line_profiler -name "*.pyx" -exec cython {} \\;')
            warnings.warn('$ cd line_profiler && pip install')
            return super(LineProfilerModule, cls).__new__(cls)

        class devserver_profile(object):
            def __init__(self, follow=[]):
                pass

            def __call__(self, func):
                return func
else:
    class LineProfilerModule(DevServerModule):
        """
        Outputs a Line by Line profile of any @devserver_profile'd functions that were run
        """
        logger_name = 'profile'

        def process_view(self, request, view_func, view_args, view_kwargs):
            request.devserver_profiler = LineProfiler()
            request.devserver_profiler_run = False
            if (DEVSERVER_AUTO_PROFILE):
                _unwrap_closure_and_profile(request.devserver_profiler, view_func)
                request.devserver_profiler.enable_by_count()

        def process_complete(self, request):
            if hasattr(request, 'devserver_profiler_run') and (DEVSERVER_AUTO_PROFILE or request.devserver_profiler_run):
                from io import StringIO
                out = StringIO()
                if (DEVSERVER_AUTO_PROFILE):
                    request.devserver_profiler.disable_by_count()
                request.devserver_profiler.print_stats(stream=out)
                self.logger.info(out.getvalue())

    def _unwrap_closure_and_profile(profiler, func):
        if not hasattr(func, 'func_code'):
            return
        profiler.add_function(func)
        if func.__closure__:
            for cell in func.__closure__:
                if hasattr(cell.cell_contents, 'func_code'):
                    _unwrap_closure_and_profile(profiler, cell.cell_contents)

    class devserver_profile(object):
        def __init__(self, follow=[]):
            self.follow = follow

        def __call__(self, func):
            def profiled_func(*args, **kwargs):
                request = args[0]
                if hasattr(request, 'request'):
                    # We're decorating a Django class-based-view and the first argument is actually self:
                    request = args[1]

                try:
                    request.devserver_profiler.add_function(func)
                    request.devserver_profiler_run = True
                    for f in self.follow:
                        request.devserver_profiler.add_function(f)
                    request.devserver_profiler.enable_by_count()
                    return func(*args, **kwargs)
                finally:
                    request.devserver_profiler.disable_by_count()

            return functools.wraps(func)(profiled_func)
