# -*- coding: utf-8 -*-
from Acquisition import aq_inner
from Acquisition import aq_parent
from z3c.form import field
from z3c.form import button

from zope import schema
from zope.component import getAdapter
from zope.component import getMultiAdapter
from zope.component import getUtility
from zope.interface import implements
from zope.i18n import MessageFactory

from plone.app.collection.interfaces import ICollection
from plone.app.portlets.browser import z3cformhelper
from plone.app.portlets.portlets import base
from plone.app.querystring.querybuilder import QueryBuilder
from plone.formwidget.querystring.widget import QueryStringFieldWidget
from plone.i18n.normalizer.interfaces import IIDNormalizer
from plone.portlets.interfaces import IPortletDataProvider
from Products.CMFCore.utils import getToolByName
from plone.directives import form

from genweb.smartportlet.renderers.interfaces import IPortletContainerRenderer
from genweb.smartportlet.renderers.interfaces import IPortletItemRenderer

from Products.statusmessages.interfaces import IStatusMessage

import random
import sys

DOMAIN = u'genweb.smartportlet'
_ = MessageFactory(DOMAIN)


class ISmartPortlet(IPortletDataProvider):
    """A portlet which renders the results of a collection object.
    """

    header = schema.TextLine(
        title=_(u"Portlet header"),
        description=_(u"Title of the rendered portlet"),
        required=True)

    show_header = schema.Bool(
        title=_(u'label_show_header', default=u'Show header'),
        description=_(u'Renders the header'),
        required=False,
        default=True
    )

    description = schema.TextLine(
        title=_(u"Portlet description"),
        description=_(u"Description of the portlet"),
        required=False)

    container_view = schema.Choice(
        title=_(u'label_container_view', default=u'Portlet view to use'),
        description=_(u"""Portlet view to use"""),
        vocabulary="genweb.smartportlet.AvailablePortletContainerRenderers",
        required=True
    )

    query = schema.List(
        title=_(u'label_query', default=u'Search terms'),
        description=_(u"""Define the search terms for the items you want to
            list by choosing what to match on.
            The list of results will be dynamically updated"""),
        value_type=schema.Dict(value_type=schema.Field(),
                               key_type=schema.TextLine()),
        required=False
    )

    form.mode(sort_on='hidden')
    sort_on = schema.TextLine(
        title=_(u'label_sort_on', default=u'Sort on'),
        description=_(u"Sort the collection on this index"),
        required=False,
    )

    form.mode(sort_order='hidden')
    sort_order = schema.Bool(
        title=_(u'label_sort_reversed', default=u'Reversed order'),
        description=_(u'Sort the results in reversed order'),
        required=False,
    )

    sort_folderorder = schema.Bool(
        title=_(u'label_sort_folderorder', default=u'Order as in folder'),
        description=_(u'Override query sort order using folder order'),
        required=False,
    )

    limit = schema.Int(
        title=_(u"Limit"),
        description=_(u"Specify the maximum number of items to show in the "
                      u"portlet. Leave this blank to show all items."),
        required=False)

    random = schema.Bool(
        title=_(u"Select random items"),
        description=_(u"If enabled, items will be selected randomly from the "
                      u"collection, rather than based on its sort order."),
        required=True,
        default=False)

    more_link = schema.TextLine(
        title=_(u"Show more link"),
        description=_(u"Link to display in the footer, leave empty to hide it"),
        required=False)

    more_text = schema.TextLine(
        title=_(u"Show more link text"),
        description=_(u"Label the 'Show more link' defined avobe"),
        default=u'+',
        required=False)


class Assignment(base.Assignment):
    """
    Portlet assignment.
    This is what is actually managed through the portlets UI and associated
    with columns.
    """

    implements(ISmartPortlet)

    header = u""
    query = None
    limit = None
    random = False

    def __init__(self, header=u"", show_header=True, sort_folderorder=False, sort_on="effective", sort_order=False, description='', query=None, limit=None, random=False, more_link=u"", more_text=u"+", container_view="li_container_render"):
        self.header = header
        self.description = description
        self.sort_on = sort_on
        self.sort_order = sort_order
        self.sort_folderorder = sort_folderorder
        self.limit = limit
        self.query = query
        self.random = random
        self.container_view = container_view
        self.more_link = more_link
        self.more_text = more_text
        self.show_header = show_header

    @property
    def title(self):
        """This property is used to give the title of the portlet in the
        "manage portlets" screen. Here, we use the title that the user gave.
        """
        return self.header


class Renderer(base.Renderer):

    def __init__(self, *args):
        base.Renderer.__init__(self, *args)
        self.plone_view = getMultiAdapter((self.context, self.request), name='plone')
        self.ptypes = getToolByName(self.context, 'portal_types')

    def render(self):
        renderer = getAdapter(self, IPortletContainerRenderer, name=self.data.container_view)
        return renderer()

    @property
    def available(self):
        return True
        return len(self.results())

    def css_class(self):
        header = self.data.header
        normalizer = getUtility(IIDNormalizer)
        return "portlet-smart-%s" % normalizer.normalize(header)

    def results(self):
        if self.data.random:
            return self._random_results()
        else:
            return self._standard_results()

    def getItemRenderer(self, item):
        args = dict(
            item=item,
            toLocalizedTime=self.plone_view.toLocalizedTime,
            cropText=self.plone_view.cropText)
        fti = self.ptypes.getTypeInfo(item.PortalType())
        module = fti.klass[:fti.klass.rfind('.')]
        klass = fti.klass[fti.klass.rfind('.') + 1:]
        dummy = getattr(sys.modules[module], klass)
        renderer = getAdapter(dummy(object), IPortletItemRenderer)
        return renderer(self, **args)

    def queryCatalog(self, limit):
        """
        """
        querybuilder = QueryBuilder(self, self.request)
        if not hasattr(self.data, 'sort_on'):
            self.data.sort_on = 'effective'
        if not hasattr(self.data, 'sort_order'):
            self.data.sort_order = False
        if not hasattr(self.data, 'sort_folderorder'):
            self.data.sort_folderorder = False

        sort_order = 'descending' if self.data.sort_order else 'ascending'
        sort_on = self.data.sort_on

        if self.data.sort_folderorder:
            sort_on = 'getObjPositionInParent'

        query = list(self.data.query)

        if ICollection.providedBy(self.context):
            query += self.context.query and self.context.query or []
            parent = aq_parent(aq_inner(self.context))
            if ICollection.providedBy(parent):
                query += parent.query and parent.query or []
        return querybuilder(query=query,
                            sort_on=sort_on,
                            sort_order=sort_order,
                            limit=limit)

    def _standard_results(self):
        results = []
        limit = self.data.limit
        if self.data.query:
            results = self.queryCatalog(limit=limit)
            if limit and limit > 0:
                results = results[:limit]
        return results

    def _random_results(self):
        # intentionally non-memoized
        results = []
        if self.data.query:
            results = self.queryCatalog()
            results = random.sample(results, self.data.limit)
        return results


class AddForm(z3cformhelper.AddForm):

    fields = field.Fields(ISmartPortlet)
    fields['query'].widgetFactory = QueryStringFieldWidget
    fields['sort_on'].mode = 'hidden'
    fields['sort_order'].mode = 'hidden'

    label = _(u"Add Query Portlet")
    description = _(u"This portlet displays a listing of items from a "
                    u"Collection.")

    def create(self, data):
        return Assignment(**data)


class EditForm(z3cformhelper.EditForm):

    fields = field.Fields(ISmartPortlet)
    fields['query'].widgetFactory = QueryStringFieldWidget
    fields['sort_on'].mode = 'hidden'
    fields['sort_order'].mode = 'hidden'

    label = _(u"Edit Collection Portlet")
    description = _(u"This portlet displays a listing of items from a "
                    u"Collection.")

    def extractData(self):
        data, errors = super(EditForm, self).extractData()
        data['sort_on'] = self.request.form.get('sort_on')
        data['sort_order'] = False if self.request.form.get('sort_order') is None else True
        return data, errors
