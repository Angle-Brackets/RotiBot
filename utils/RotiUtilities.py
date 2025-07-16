import logging.config
import logging.handlers
import datetime as dt
import pathlib
import json
import atexit
from typing import Callable, override

LOG_RECORD_BUILTIN_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}

TEST_GUILD = 844707618102444113

def cog_command(cls):
    """
    This is a decorator to identify a class as a cog, if this decorator is not used, then the 
    class is considered NOT a cog and won't be loaded as one.
    """
    cls.is_cog = True
    return cls

def single_run(func : Callable):
    has_run = False
    def wrapper(*args, **kwargs):
        nonlocal has_run
        if not has_run:
            result = func(*args, **kwargs)
            has_run = True
            return result
        else:
            raise ValueError(f"Invalid re-use of Singleton Function: {func.__name__}")
    return wrapper


@single_run
def setup_logging(*, config_file : str):
    config_file = pathlib.Path(config_file)
    config = None
    with open(config_file) as f:
        config = json.load(f)
    
    logging.config.dictConfig(config)
    queue_handler : logging.handlers.QueueHandler = logging.getHandlerByName("queue_handler") # This allows for non-blocking logging.
    if queue_handler:
        queue_handler.listener.start()
        atexit.register(queue_handler.listener.stop)

# Credit to https://github.com/mCodingLLC/VideosSampleCode/blob/master/videos/135_modern_logging/mylogger.py
class LogJSONFormatter(logging.Formatter):
    def __init__(
        self,
        *,
        fmt_keys: dict[str, str] | None = None,
    ):
        super().__init__()
        self.fmt_keys = fmt_keys if fmt_keys is not None else {}

    @override
    def format(self, record: logging.LogRecord) -> str:
        message = self._prepare_log_dict(record)
        return json.dumps(message, default=str)

    def _prepare_log_dict(self, record: logging.LogRecord):
        always_fields = {
            "message": record.getMessage(),
            "timestamp": dt.datetime.fromtimestamp(
                record.created, tz=dt.timezone.utc
            ).isoformat(),
        }
        if record.exc_info is not None:
            always_fields["exc_info"] = self.formatException(record.exc_info)

        if record.stack_info is not None:
            always_fields["stack_info"] = self.formatStack(record.stack_info)

        message = {
            key: msg_val
            if (msg_val := always_fields.pop(val, None)) is not None
            else getattr(record, val)
            for key, val in self.fmt_keys.items()
        }
        message.update(always_fields)

        for key, val in record.__dict__.items():
            if key not in LOG_RECORD_BUILTIN_ATTRS:
                message[key] = val

        return message

