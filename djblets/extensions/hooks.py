#
# hooks.py -- Common extension hook points.
#
# Copyright (c) 2010-2011  Beanbag, Inc.
# Copyright (c) 2008-2010  Christian Hammond
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from __future__ import unicode_literals

import uuid

from django.template.loader import render_to_string

from djblets.util.compat import six


class ExtensionHook(object):
    """The base class for a hook into some part of the project.

    ExtensionHooks are classes that can hook into an
    :py:class:`ExtensionHookPoint` to provide some level of functionality
    in a project. A project should provide a subclass of ExtensionHook that
    will provide functions for getting data or anything else that's needed,
    and then extensions will subclass that specific ExtensionHook.

    A base ExtensionHook subclass must use :py:class:`ExtensionHookPoint`
    as a metaclass. For example::

        from djblets.util.compat import six

        @six.add_metaclass(ExtensionHookPoint)
        class NavigationHook(ExtensionHook):
    """
    def __init__(self, extension):
        self.extension = extension
        self.extension.hooks.add(self)
        self.__class__.add_hook(self)
        self.initialized = True

    def shutdown(self):
        assert self.initialized

        self.__class__.remove_hook(self)
        self.initialized = False


class ExtensionHookPoint(type):
    """A metaclass used for base Extension Hooks.

    Base :py:class:`ExtensionHook` classes use :py:class:`ExtensionHookPoint`
    as a metaclass. This metaclass stores the list of registered hooks that
    an :py:class:`ExtensionHook` will automatically register with.
    """
    def __init__(cls, name, bases, attrs):
        super(ExtensionHookPoint, cls).__init__(name, bases, attrs)

        if not hasattr(cls, "hooks"):
            cls.hooks = []

    def add_hook(cls, hook):
        """Adds an ExtensionHook to the list of active hooks.

        This is called automatically by :py:class:`ExtensionHook`.
        """
        cls.hooks.append(hook)

    def remove_hook(cls, hook):
        """Removes an ExtensionHook from the list of active hooks.

        This is called automatically by :py:class:`ExtensionHook`.
        """
        cls.hooks.remove(hook)


class AppliesToURLMixin(object):
    """A mixin for hooks to allow restricting to certain URLs.

    This provides an applies_to() function for the hook that can be used
    by consumers to determine if the hook should apply to the current page.
    """
    def __init__(self, extension, apply_to=[], *args, **kwargs):
        super(AppliesToURLMixin, self).__init__(extension)
        self.apply_to = apply_to

    def applies_to(self, request):
        """Returns whether or not this hook applies to the page.

        This will determine whether any of the URL names provided in
        ``apply_to`` matches the current requested page.
        """
        return (not self.apply_to or
                request.resolver_match.url_name in self.apply_to)


@six.add_metaclass(ExtensionHookPoint)
class DataGridColumnsHook(ExtensionHook):
    """Adds columns to a datagrid.

    This hook allows an extension to register new columns to any datagrid.
    These columns can be added by the user, rearranged, and sorted, like
    any other column.

    Each column must have an id already set, and it must be unique.
    """
    def __init__(self, extension, datagrid_cls, columns):
        super(DataGridColumnsHook, self).__init__(extension)
        self.datagrid_cls = datagrid_cls
        self.columns = columns

        for column in columns:
            self.datagrid_cls.add_column(column)

    def shutdown(self):
        super(DataGridColumnsHook, self).shutdown()

        for column in self.columns:
            self.datagrid_cls.remove_column(column)


@six.add_metaclass(ExtensionHookPoint)
class URLHook(ExtensionHook):
    """Custom URL hook.

    A hook that installs custom URLs. These URLs reside in a project-specified
    parent URL.
    """
    def __init__(self, extension, patterns):
        super(URLHook, self).__init__(extension)
        self.patterns = patterns
        self.dynamic_urls = self.extension.extension_manager.dynamic_urls
        self.dynamic_urls.add_patterns(patterns)

    def shutdown(self):
        super(URLHook, self).shutdown()

        self.dynamic_urls.remove_patterns(self.patterns)


@six.add_metaclass(ExtensionHookPoint)
class SignalHook(ExtensionHook):
    """Connects to a Django signal.

    This will handle connecting to a signal, calling the specified callback
    when fired. It will disconnect from the signal when the extension is
    disabled.
    """
    def __init__(self, extension, signal, callback, sender=None):
        super(SignalHook, self).__init__(extension)

        self.signal = signal
        self.callback = callback
        self.dispatch_uid = uuid.uuid1()

        signal.connect(callback, sender=sender, weak=False,
                       dispatch_uid=self.dispatch_uid)

    def shutdown(self):
        super(SignalHook, self).shutdown()

        self.signal.disconnect(dispatch_uid=self.dispatch_uid)


@six.add_metaclass(ExtensionHookPoint)
class TemplateHook(AppliesToURLMixin, ExtensionHook):
    """Custom templates hook.

    A hook that renders a template at hook points defined in another template.
    """
    _by_name = {}

    def __init__(self, extension, name, template_name=None, apply_to=[]):
        super(TemplateHook, self).__init__(extension, apply_to=apply_to)
        self.name = name
        self.template_name = template_name

        if not name in self.__class__._by_name:
            self.__class__._by_name[name] = [self]
        else:
            self.__class__._by_name[name].append(self)

    def shutdown(self):
        super(TemplateHook, self).shutdown()

        self.__class__._by_name[self.name].remove(self)

    def render_to_string(self, request, context):
        """Renders the content for the hook.

        By default, this renders the provided template name to a string
        and returns it.
        """
        context.push()
        context['extension'] = self.extension

        try:
            return render_to_string(self.template_name, context)
        finally:
            context.pop()

    @classmethod
    def by_name(cls, name):
        return cls._by_name.get(name, [])
