from jinja2 import Environment, PackageLoader, ChoiceLoader
from jinja2.defaults import DEFAULT_NAMESPACE
from django.templatetags.static import static
from django.urls import reverse

def environment(**options):
    # Get the existing loader from options
    existing_loader = options.get('loader')

    # Create a choice loader that checks nhsuk_frontend_jinja templates first, then app templates
    loaders = [PackageLoader('nhsuk_frontend_jinja', 'templates')]
    if existing_loader:
        loaders.append(existing_loader)

    options['loader'] = ChoiceLoader(loaders)

    env = Environment(**options)

    env.globals.update({
        'static': static,
        'url': reverse,
        # Provide empty search object to avoid NHS template errors
        'search': {},
    })
    return env
