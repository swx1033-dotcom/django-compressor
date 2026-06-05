# flake8: noqa
import os
import sys
import concurrent.futures
from threading import Lock

from collections import OrderedDict, defaultdict
from fnmatch import fnmatch
from importlib import import_module

from django.core.management.base import BaseCommand, CommandError
from django.template import Context
from django.utils.encoding import smart_str
from django.template.loader import (
    get_template,
)  # noqa Leave this in to preload template locations
from django.template import engines

from compressor.cache import get_offline_hexdigest, write_offline_manifest
from compressor.conf import settings
from compressor.exceptions import (
    OfflineGenerationError,
    TemplateSyntaxError,
    TemplateDoesNotExist,
)
from compressor.utils import get_mod_func

render_locks_lock = Lock()
render_locks = defaultdict(Lock)


class LogBuffer:
    def __init__(self):
        self.messages = []

    def write(self, message):
        self.messages.append(message)

    def flush(self):
        pass

    def getvalue(self):
        return "".join(self.messages)


class Command(BaseCommand):
    help = "Compress content outside of the request/response cycle"

    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument(
            "--extension",
            "-e",
            action="append",
            dest="extensions",
            help='The file extension(s) to examine (default: ".html", '
            "separate multiple extensions with commas, or use -e "
            "multiple times)",
        )
        parser.add_argument(
            "-f",
            "--force",
            default=False,
            action="store_true",
            help="Force the generation of compressed content even if the "
            "COMPRESS_ENABLED setting is not True.",
            dest="force",
        )
        parser.add_argument(
            "--follow-links",
            default=False,
            action="store_true",
            help="Follow symlinks when traversing the COMPRESS_ROOT "
            "(which defaults to STATIC_ROOT). Be aware that using this "
            "can lead to infinite recursion if a link points to a parent "
            "directory of itself.",
            dest="follow_links",
        )
        parser.add_argument(
            "--engine",
            default=[],
            action="append",
            help="Specifies the templating engine. jinja2 and django are "
            "supported. It may be a specified more than once for "
            "multiple engines. If not specified, django engine is used.",
            dest="engines",
        )
        parser.add_argument(
            "--parallel",
            default=False,
            action="store_true",
            help="Process templates in parallel using a thread pool. "
            "Worker count comes from COMPRESS_PARALLEL_WORKERS.",
            dest="parallel",
        )

    def get_loaders(self):
        template_source_loaders = []
        for e in engines.all():
            if hasattr(e, "engine"):
                template_source_loaders.extend(
                    e.engine.get_template_loaders(e.engine.loaders)
                )
        loaders = []
        # If template loader is CachedTemplateLoader, return the loaders
        # that it wraps around. So if we have
        # TEMPLATE_LOADERS = (
        #    ('django.template.loaders.cached.Loader', (
        #        'django.template.loaders.filesystem.Loader',
        #        'django.template.loaders.app_directories.Loader',
        #    )),
        # )
        # The loaders will return django.template.loaders.filesystem.Loader
        # and django.template.loaders.app_directories.Loader
        # The cached Loader and similar ones include a 'loaders' attribute
        # so we look for that.
        for loader in template_source_loaders:
            if hasattr(loader, "loaders"):
                loaders.extend(loader.loaders)
            else:
                loaders.append(loader)
        return loaders

    def __get_parser(self, engine):
        charset = (
            settings.FILE_CHARSET if settings.is_overridden("FILE_CHARSET") else "utf-8"
        )
        if engine == "jinja2":
            from compressor.offline.jinja2 import Jinja2Parser

            env = settings.COMPRESS_JINJA2_GET_ENVIRONMENT()
            parser = Jinja2Parser(charset=charset, env=env)
        elif engine == "django":
            from compressor.offline.django import DjangoParser

            parser = DjangoParser(charset=charset)
        else:
            raise OfflineGenerationError("Invalid templating engine specified.")

        return parser

    def _get_parallel_workers(self):
        return max(1, settings.COMPRESS_PARALLEL_WORKERS)

    def _compress_templates(
        self,
        contexts,
        fine_templates,
        parser,
        verbosity,
        log,
        parallel=False,
        parallel_workers=1,
    ):
        contexts_count = 0
        nodes_count = 0
        offline_manifest = OrderedDict()
        manifest_lock = Lock()

        for context_dict in contexts:
            compressor_nodes = OrderedDict()
            for template in fine_templates:
                context = Context(parser.get_init_context(context_dict))

                try:
                    nodes = list(parser.walk_nodes(template, context=context))
                except (TemplateDoesNotExist, TemplateSyntaxError) as e:
                    if verbosity >= 1:
                        log.write(
                            "Error parsing template %s: %s\n"
                            % (template.template_name, smart_str(e))
                        )
                    continue

                if nodes:
                    template_nodes = compressor_nodes.setdefault(
                        template, OrderedDict()
                    )
                    for node in nodes:
                        nodes_count += 1
                        template_nodes.setdefault(node, []).append(context)

            should_parallelize = (
                parallel
                and parallel_workers > 1
                and len(compressor_nodes) > 1
            )
            if should_parallelize:
                self._compress_templates_parallel(
                    offline_manifest,
                    manifest_lock,
                    compressor_nodes,
                    parser,
                    verbosity,
                    log,
                    parallel_workers,
                )
            else:
                self._compress_templates_serial(
                    offline_manifest,
                    manifest_lock,
                    compressor_nodes,
                    parser,
                    verbosity,
                    log,
                )
            contexts_count += 1

        return offline_manifest, nodes_count, contexts_count

    def _compress_templates_parallel(
        self,
        offline_manifest,
        manifest_lock,
        compressor_nodes,
        parser,
        verbosity,
        log,
        parallel_workers,
    ):
        jobs = []
        max_workers = min(parallel_workers, len(compressor_nodes))

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            for template, nodes in compressor_nodes.items():
                template_log = LogBuffer()
                template._log = template_log
                template._log_verbosity = verbosity
                future = pool.submit(
                    self._compress_template,
                    offline_manifest,
                    nodes,
                    parser,
                    template,
                    manifest_lock=manifest_lock,
                )
                jobs.append((future, template_log))

            for future, _ in jobs:
                future.result()

        for _, template_log in jobs:
            buffered_output = template_log.getvalue()
            if buffered_output:
                log.write(buffered_output)

    def _compress_templates_serial(
        self,
        offline_manifest,
        manifest_lock,
        compressor_nodes,
        parser,
        verbosity,
        log,
    ):
        for template, nodes in compressor_nodes.items():
            template._log = log
            template._log_verbosity = verbosity
            self._compress_template(
                offline_manifest,
                nodes,
                parser,
                template,
                manifest_lock=manifest_lock,
            )

    def compress(
        self,
        engine,
        extensions,
        verbosity,
        follow_links,
        log,
        parallel=False,
    ):
        """
        Searches templates containing 'compress' nodes and compresses them
        "offline" -- outside of the request/response cycle.

        The result is cached with a cache-key derived from the content of the
        compress nodes (not the content of the possibly linked files!).
        """

        if not self.get_loaders():
            raise OfflineGenerationError(
                "No template loaders defined. You "
                "must set TEMPLATE_LOADERS in your "
                "settings or set 'loaders' in your "
                "TEMPLATES dictionary."
            )
        templates = set()
        if engine == "django":
            paths = set()
            for loader in self.get_loaders():
                try:
                    module = import_module(loader.__module__)
                    get_template_sources = getattr(module, "get_template_sources", None)
                    if get_template_sources is None:
                        get_template_sources = loader.get_template_sources
                    paths.update(
                        smart_str(origin) for origin in get_template_sources("")
                    )
                except (ImportError, AttributeError, TypeError):
                    pass

            if not paths:
                raise OfflineGenerationError(
                    "No template paths found. None of "
                    "the configured template loaders "
                    "provided template paths. See "
                    "https://docs.djangoproject.com/en/2.1/topics/templates/ "
                    "for more information on template "
                    "loaders."
                )
            if verbosity >= 2:
                log.write("Considering paths:\n\t" + "\n\t".join(paths) + "\n")

            for path in paths:
                for root, _dirs, files in os.walk(path, followlinks=follow_links):
                    templates.update(
                        os.path.relpath(os.path.join(root, name), path)
                        for name in files
                        if not name.startswith(".")
                        and any(fnmatch(name, "*%s" % glob) for glob in extensions)
                    )
        elif engine == "jinja2":
            env = settings.COMPRESS_JINJA2_GET_ENVIRONMENT()
            if env and hasattr(env, "list_templates"):
                templates |= set(
                    [
                        env.loader.get_source(env, template)[1]
                        for template in env.list_templates(
                            filter_func=lambda _path: os.path.splitext(_path)[-1]
                            in extensions
                        )
                    ]
                )

        if not templates:
            raise OfflineGenerationError(
                "No templates found. Make sure your "
                "TEMPLATE_LOADERS and TEMPLATE_DIRS "
                "settings are correct."
            )
        if verbosity >= 2:
            log.write("Found templates:\n\t" + "\n\t".join(templates) + "\n")

        contexts = settings.COMPRESS_OFFLINE_CONTEXT
        if isinstance(contexts, str):
            try:
                module, function = get_mod_func(contexts)
                contexts = getattr(import_module(module), function)()
            except (AttributeError, ImportError, TypeError) as e:
                raise ImportError(
                    "Couldn't import offline context function %s: %s"
                    % (settings.COMPRESS_OFFLINE_CONTEXT, e)
                )

        if isinstance(contexts, (list, tuple)):
            contexts = list(contexts)
        elif hasattr(contexts, "__next__"):
            contexts = list(contexts)
        else:
            contexts = [contexts]

        parser = self.__get_parser(engine)
        fine_templates = []

        if verbosity >= 1:
            log.write("Compressing... ")

        for template_name in templates:
            try:
                template = parser.parse(template_name)
                template.template_name = template_name
                fine_templates.append(template)
            except IOError:
                if verbosity >= 1:
                    log.write("Unreadable template at: %s\n" % template_name)
                continue
            except TemplateSyntaxError as e:
                if verbosity >= 1:
                    log.write(
                        "Invalid template %s: %s\n" % (template_name, smart_str(e))
                    )
                continue
            except TemplateDoesNotExist:
                if verbosity >= 1:
                    log.write("Non-existent template at: %s\n" % template_name)
                continue
            except UnicodeDecodeError:
                if verbosity >= 1:
                    log.write(
                        "UnicodeDecodeError while trying to read "
                        "template %s\n" % template_name
                    )
                continue

        parallel_workers = self._get_parallel_workers()
        try:
            offline_manifest, nodes_count, contexts_count = self._compress_templates(
                contexts,
                fine_templates,
                parser,
                verbosity,
                log,
                parallel=parallel,
                parallel_workers=parallel_workers,
            )
        except Exception as exc:
            if not parallel:
                raise
            if verbosity >= 1:
                log.write(
                    "Parallel compression failed, retrying serially: %s\n"
                    % smart_str(exc)
                )
            offline_manifest, nodes_count, contexts_count = self._compress_templates(
                contexts,
                fine_templates,
                parser,
                verbosity,
                log,
                parallel=False,
                parallel_workers=1,
            )

        if not nodes_count:
            raise OfflineGenerationError(
                "No 'compress' template tags found in templates."
                "Try running compress command with --follow-links and/or"
                "--extension=EXTENSIONS"
            )

        if verbosity >= 1:
            log.write(
                "done\nCompressed %d block(s) from %d template(s) for %d context(s).\n"
                % (len(offline_manifest), nodes_count, contexts_count)
            )
        return offline_manifest, len(offline_manifest), offline_manifest.values()

    @staticmethod
    def _compress_template(
        offline_manifest,
        nodes,
        parser,
        template,
        errors=None,
        manifest_lock=None,
    ):
        manifest_lock = manifest_lock or Lock()

        for node, node_contexts in nodes.items():
            for context in node_contexts:
                context.push()
                try:
                    if not parser.process_template(template, context):
                        continue

                    parser.process_node(template, context, node)
                    rendered = parser.render_nodelist(template, context, node)
                    key = get_offline_hexdigest(rendered)

                    with manifest_lock:
                        if key in offline_manifest:
                            continue

                        offline_manifest[key] = None

                    with render_locks_lock:
                        render_lock = render_locks[key]

                    try:
                        with render_lock:
                            result = parser.render_node(template, context, node)
                    except Exception as e:
                        with manifest_lock:
                            offline_manifest.pop(key, None)
                        error = CommandError(
                            "An error occurred during rendering %s: "
                            "%s" % (template.template_name, smart_str(e))
                        )
                        if errors is not None:
                            errors.append(error)
                            return
                        raise error
                    finally:
                        with render_locks_lock:
                            render_locks.pop(key, None)

                    result = result.replace(
                        str(settings.COMPRESS_URL),
                        settings.COMPRESS_URL_PLACEHOLDER,
                    )
                    with manifest_lock:
                        offline_manifest[key] = result
                finally:
                    context.pop()

    def handle_extensions(self, extensions=("html",)):
        """
        organizes multiple extensions that are separated with commas or
        passed by using --extension/-e multiple times.

        for example: running 'django-admin compress -e js,txt -e xhtml -a'
        would result in an extension list: ['.js', '.txt', '.xhtml']

        >>> handle_extensions(['.html', 'html,js,py,py,py,.py', 'py,.py'])
        ['.html', '.js']
        >>> handle_extensions(['.html, txt,.tpl'])
        ['.html', '.tpl', '.txt']
        """
        ext_list = []
        for ext in extensions:
            ext_list.extend(ext.replace(" ", "").split(","))
        for i, ext in enumerate(ext_list):
            if not ext.startswith("."):
                ext_list[i] = ".%s" % ext_list[i]
        return set(ext_list)

    def handle(self, **options):
        self.handle_inner(**options)

    def handle_inner(self, **options):
        if not settings.COMPRESS_ENABLED and not options.get("force"):
            raise CommandError(
                "Compressor is disabled. Set the COMPRESS_ENABLED "
                "setting or use --force to override."
            )
        if not settings.COMPRESS_OFFLINE:
            if not options.get("force"):
                raise CommandError(
                    "Offline compression is disabled. Set "
                    "COMPRESS_OFFLINE or use the --force to override."
                )

        log = options.get("log", sys.stdout)
        verbosity = options.get("verbosity", 1)
        follow_links = options.get("follow_links", False)
        extensions = self.handle_extensions(options.get("extensions") or ["html"])
        engines = [e.strip() for e in options.get("engines", [])] or ["django"]
        parallel = options.get("parallel", False)

        final_offline_manifest = {}
        final_block_count = 0
        final_results = []
        for engine in engines:
            offline_manifest, block_count, results = self.compress(
                engine,
                extensions,
                verbosity,
                follow_links,
                log,
                parallel=parallel,
            )
            final_results.extend(results)
            final_block_count += block_count
            final_offline_manifest.update(offline_manifest)
        write_offline_manifest(final_offline_manifest)
        return final_block_count, final_results
