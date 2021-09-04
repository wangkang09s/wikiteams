import sys
import logging
import logging.config
from termcolor import colored

DISABLE__STD = False

logging.config.fileConfig('logging.conf')
logger = logging.getLogger(__name__)

intelliTag_verbose = True


def log(s):
    if intelliTag_verbose:
        logger.info(str(s))


def say(s):
    if intelliTag_verbose:
        print str(s)


def cout(s):
    if intelliTag_verbose:
        print str(s)


def ssay(s):
    if intelliTag_verbose:
        print colored(str(s),'green')
        logger.info(str(s))


def log_error(s, cmd):
    if intelliTag_verbose:
        if cmd:
            print colored(str(s),'red')
        logger.error(s)


def log_warning(s, cmd):
    if intelliTag_verbose:
        if cmd:
            print colored(str(s),'yellow')
        logger.warning(s)


def log_debug(s, cmd):
    if intelliTag_verbose:
        if cmd:
            print colored(str(s),'blue')
        logger.debug(s)


def std_write(s):
    if (intelliTag_verbose) and (not DISABLE__STD):
        sys.stdout.write(s)
        sys.stdout.flush()
